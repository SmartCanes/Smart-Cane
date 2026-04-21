import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func

from app import db
from app.models import Admin, AdminArchive, AdminAuditLog, Device, GuardianConcern
from app.routes.notifications import create_notification


restore_bp = Blueprint("restore", __name__, url_prefix="/api/admin/audit-logs")

RESTORABLE_ACTIONS = {
	"admin_delete",
	"concern_delete",
	"device_delete",
	"device_deleted",
}
DEVICE_DELETE_ACTIONS = {"device_delete", "device_deleted"}
CONCERN_STATUS_OPTIONS = {"unread", "read", "resolved"}


def require_super_admin():
	claims = get_jwt()
	if claims.get("role") != "super_admin":
		return jsonify({"message": "Access denied. Super admin only."}), 403
	return None


def _safe_parse_json(text_value):
	if not text_value:
		return {}
	try:
		parsed = json.loads(text_value)
		return parsed if isinstance(parsed, dict) else {}
	except Exception:
		return {}


def _default_restore_reason(payload):
	code = str((payload or {}).get("reason_code") or "restore_from_audit").strip() or "restore_from_audit"
	text = str((payload or {}).get("reason_text") or "Restored from audit log entry.").strip()
	if len(text) < 10:
		text = "Restored from audit log entry."
	return code, text


def _log_restore_action(actor_id, action_type, old_payload, new_payload, reason_code, reason_text):
	db.session.add(
		AdminAuditLog(
			actor_admin_id=actor_id,
			action_type=action_type,
			old_value_json=json.dumps(old_payload),
			new_value_json=json.dumps(new_payload),
			reason_code=reason_code,
			reason_text=reason_text,
			status="success",
			ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
			user_agent=(request.user_agent.string or "")[:255],
		)
	)


def _restore_deleted_admin(old_payload):
	deleted_admin_id = old_payload.get("deleted_admin_id")
	if not deleted_admin_id:
		return None, "Missing deleted_admin_id in audit payload.", 400

	archive = (
		AdminArchive.query.filter_by(admin_id=int(deleted_admin_id))
		.order_by(AdminArchive.archived_at.desc())
		.first()
	)
	if not archive:
		return None, "No archived admin record found for this audit entry.", 404

	existing_username = Admin.query.filter_by(username=archive.username).first()
	if existing_username:
		return None, "Cannot restore admin because username already exists.", 409

	archived_email = str(archive.email or old_payload.get("email") or "").strip()
	if not archived_email:
		return None, "Cannot restore admin because archived email is missing.", 400

	existing_email = Admin.query.filter(func.lower(Admin.email) == archived_email.lower()).first()
	if existing_email:
		return None, "Cannot restore admin because email already exists in active admins.", 409

	restored = Admin(
		admin_id=archive.admin_id,
		username=archive.username,
		email=archived_email,
		password=archive.password,
		first_name=archive.first_name,
		middle_name=archive.middle_name,
		last_name=archive.last_name,
		contact_number=archive.contact_number,
		province=archive.province,
		city=archive.city,
		barangay=archive.barangay,
		street_address=archive.street_address,
		role=archive.role if archive.role in ("admin", "super_admin") else "admin",
		is_first_login=False,
		profile_image_url=archive.profile_image_url,
		created_at=archive.original_created_at or datetime.now(timezone.utc),
		updated_at=datetime.now(timezone.utc),
	)
	db.session.add(restored)
	db.session.delete(archive)

	return {
		"restored_action_type": "admin_restore",
		"restored_admin_id": restored.admin_id,
		"restored_admin_email": restored.email,
	}, None, None


def _restore_deleted_concern(old_payload):
	concern_id = old_payload.get("concern_id")
	if not concern_id:
		return None, "Missing concern_id in audit payload.", 400

	concern = GuardianConcern.query.get(int(concern_id))

	if concern and not concern.is_deleted:
		return None, "Concern is already active.", 409

	if concern:
		concern.is_deleted = False
		concern.deleted_at = None
		concern.deleted_by_admin_id = None
		concern.deleted_reason_code = None
		concern.deleted_reason_text = None
		concern.updated_at = datetime.now(timezone.utc)
		restored_concern = concern
	else:
		status = str(old_payload.get("status") or "unread").strip().lower()
		if status not in CONCERN_STATUS_OPTIONS:
			status = "unread"

		restored_concern = GuardianConcern(
			concern_id=int(concern_id),
			name=str(old_payload.get("name") or "Unknown").strip() or "Unknown",
			email=str(old_payload.get("email") or "unknown@example.com").strip() or "unknown@example.com",
			message=str(old_payload.get("message") or "Restored concern without original message.").strip()
			or "Restored concern without original message.",
			status=status,
			process_stage="resolved" if status == "resolved" else "new",
			is_deleted=False,
		)
		db.session.add(restored_concern)

	return {
		"restored_action_type": "concern_restore",
		"restored_concern_id": restored_concern.concern_id,
	}, None, None


def _restore_deleted_device(old_payload):
	serial = str(
		old_payload.get("deleted_device_serial")
		or old_payload.get("device_serial_number")
		or ""
	).strip()
	if not serial:
		return None, "Missing deleted device serial in audit payload.", 400

	existing = Device.query.filter(func.lower(Device.device_serial_number) == serial.lower()).first()
	if existing:
		return None, "Device serial already exists in active devices and cannot be restored.", 409

	restored = Device(
		device_serial_number=serial,
		is_paired=bool(old_payload.get("is_paired", False)),
		vip_id=old_payload.get("vip_id"),
	)
	db.session.add(restored)

	return {
		"restored_action_type": "device_restore",
		"restored_device_serial": serial,
	}, None, None


def _notify_restore(actor, action_type, result_payload):
	try:
		actor_name = (
			" ".join(part for part in [actor.first_name, actor.last_name] if part).strip()
			if actor
			else "A super admin"
		) or "A super admin"
		actor_role = ((actor.role if actor and actor.role else "super_admin") or "super_admin").replace("_", " ")

		if action_type == "admin_delete":
			body = (
				f"{actor_name} ({actor_role}) restored admin account "
				f"{result_payload.get('restored_admin_email', '')}."
			)
			link_path = "/admins"
			notif_type = "admin_restored"
			title = "Admin account restored"
		elif action_type == "concern_delete":
			body = (
				f"{actor_name} ({actor_role}) restored guardian concern "
				f"#{result_payload.get('restored_concern_id', '-')}."
			)
			link_path = "/guardian-concerns"
			notif_type = "concern_restored"
			title = "Guardian concern restored"
		elif action_type in DEVICE_DELETE_ACTIONS:
			body = (
				f"{actor_name} ({actor_role}) restored device "
				f"{result_payload.get('restored_device_serial', '-')}."
			)
			link_path = "/devices"
			notif_type = "device_restored"
			title = "Device restored"

		create_notification(
			audience="all_admins",
			type=notif_type,
			title=title,
			body=body,
			link_path=link_path,
			related_admin_id=actor.admin_id if actor else None,
		)
	except Exception:
		pass


@restore_bp.route("/<int:audit_id>/restore", methods=["POST"])
@jwt_required()
def restore_from_audit(audit_id):
	err = require_super_admin()
	if err:
		return err

	audit = AdminAuditLog.query.get(audit_id)
	if not audit:
		return jsonify({"message": "Audit record not found."}), 404

	if audit.action_type not in RESTORABLE_ACTIONS:
		return jsonify({"message": "This audit action is not restorable."}), 400

	if audit.status != "success":
		return jsonify({"message": "Only successful delete actions can be restored."}), 400

	old_payload = _safe_parse_json(audit.old_value_json)
	actor_id = int(get_jwt_identity())
	actor = Admin.query.get(actor_id)
	reason_code, reason_text = _default_restore_reason(request.get_json(silent=True) or {})

	try:
		if audit.action_type == "admin_delete":
			result_payload, error_message, error_status = _restore_deleted_admin(old_payload)
		elif audit.action_type == "concern_delete":
			result_payload, error_message, error_status = _restore_deleted_concern(old_payload)
		elif audit.action_type in DEVICE_DELETE_ACTIONS:
			result_payload, error_message, error_status = _restore_deleted_device(old_payload)
		else:
			return jsonify({"message": "This audit action is not restorable."}), 400

		if error_message:
			return jsonify({"message": error_message}), error_status

		_log_restore_action(
			actor_id=actor_id,
			action_type=result_payload["restored_action_type"],
			old_payload={"source_audit_id": audit.audit_id, "source_action_type": audit.action_type},
			new_payload=result_payload,
			reason_code=reason_code,
			reason_text=reason_text,
		)

		db.session.commit()
		_notify_restore(actor, audit.action_type, result_payload)

		return jsonify(
			{
				"message": "Restore completed successfully.",
				**result_payload,
			}
		), 200
	except Exception:
		db.session.rollback()
		return jsonify({"message": "Failed to restore record."}), 500
