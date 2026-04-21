from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app import db
from app.models import Device, DeviceLog, GuardianInvitation, AdminAuditLog, Admin
from app.routes.notifications import create_notification
from datetime import datetime, timezone, timedelta
import json

device_bp = Blueprint("device", __name__)


def require_admin():
    claims = get_jwt()
    if claims.get("role") not in ("super_admin", "admin"):
        return jsonify({"message": "Access denied."}), 403
    return None


def require_super_admin():
    claims = get_jwt()
    if claims.get("role") != "super_admin":
        return jsonify({"message": "Access denied. Super admin only."}), 403
    return None


def _is_active(last_active_at):
    if not last_active_at:
        return False
    now = datetime.now(timezone.utc)
    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=timezone.utc)
    return (now - last_active_at) <= timedelta(hours=24)


def _serialize_device(d):
    vip = None
    if d.vip:
        vip = {
            "vip_id": d.vip.vip_id,
            "first_name": d.vip.first_name,
            "last_name": d.vip.last_name,
            "vip_image_url": d.vip.vip_image_url,
        }

    guardians = []
    for link in d.guardian_links:
        g = link.guardian
        guardians.append(
            {
                "guardian_id": g.guardian_id,
                "first_name": g.first_name,
                "last_name": g.last_name,
                "email": g.email,
                "role": link.role,
                "is_emergency_contact": link.is_emergency_contact,
            }
        )

    return {
        "device_id": d.device_id,
        "vip_id": d.vip_id,
        "device_serial_number": d.device_serial_number,
        "is_paired": d.is_paired,
        "status": "active" if _is_active(d.last_active_at) else "inactive",
        "paired_at": d.paired_at.isoformat() if d.paired_at else None,
        "last_active_at": d.last_active_at.isoformat() if d.last_active_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "vip": vip,
        "guardians": guardians,
    }


def _serialize_log(l):
    return {
        "log_id": l.log_id,
        "device_id": l.device_id,
        "guardian_id": l.guardian_id,
        "activity_type": l.activity_type,
        "status": l.status,
        "message": l.message,
        "metadata_json": l.metadata_json,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


def _serialize_invitation(i):
    return {
        "id": i.id,
        "token": i.token,
        "email": i.email,
        "device_id": i.device_id,
        "invited_by_guardian_id": i.invited_by_guardian_id,
        "status": i.status,
        "expires_at": i.expires_at.isoformat() if i.expires_at else None,
        "accepted_at": i.accepted_at.isoformat() if i.accepted_at else None,
    }


@device_bp.route("/", methods=["GET"])
@jwt_required()
def list_devices():
    err = require_admin()
    if err:
        return err
    devices = Device.query.order_by(Device.created_at.desc()).all()
    return jsonify([_serialize_device(d) for d in devices]), 200


@device_bp.route("/<int:device_id>", methods=["GET"])
@jwt_required()
def get_device(device_id):
    err = require_admin()
    if err:
        return err
    d = Device.query.get_or_404(device_id)
    return jsonify(_serialize_device(d)), 200


@device_bp.route("/", methods=["POST"])
@jwt_required()
def create_device():
    err = require_admin()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Request body must be JSON."}), 400

    serial = data.get("device_serial_number", "").strip()
    if not serial:
        return jsonify({"message": "device_serial_number is required."}), 400

    if Device.query.filter_by(device_serial_number=serial).first():
        return jsonify({"message": "Device serial number already exists."}), 409

    device = Device(device_serial_number=serial, vip_id=data.get("vip_id"), is_paired=False)
    db.session.add(device)
    db.session.commit()

    actor = Admin.query.get(int(get_jwt_identity()))
    actor_name = (
        f"{(actor.first_name or '').strip()} {(actor.last_name or '').strip()}".strip()
        if actor else "An admin"
    )
    actor_role = (actor.role or "admin").replace("_", " ").title() if actor else "Admin"

    create_notification(
        audience="all_admins",
        type="device_created",
        title="New device added",
        body=f"{actor_name} ({actor_role}) added device {device.device_serial_number}.",
        link_path="/devices",
        related_admin_id=actor.admin_id if actor else None,
    )

    return jsonify({"message": "Device created successfully.", "device_id": device.device_id}), 201


@device_bp.route("/<int:device_id>", methods=["PUT"])
@jwt_required()
def update_device(device_id):
    err = require_super_admin()
    if err:
        return err

    d = Device.query.get_or_404(device_id)
    data = request.get_json(silent=True) or {}

    new_serial = data.get("device_serial_number", "").strip()
    if new_serial and new_serial != d.device_serial_number:
        clash = Device.query.filter_by(device_serial_number=new_serial).first()
        if clash:
            return jsonify({"message": "Serial number already exists."}), 409
        d.device_serial_number = new_serial

    d.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"message": "Device updated successfully.", "device": _serialize_device(d)}), 200


@device_bp.route("/<int:device_id>", methods=["DELETE"])
@jwt_required()
def delete_device(device_id):
    err = require_super_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    reason_code = str(data.get("reason_code", "")).strip()
    reason_text = str(data.get("reason_text", "")).strip()

    if not reason_code:
        return jsonify({"message": "reason_code is required."}), 400
    if len(reason_text) < 10:
        return jsonify({"message": "reason_text is required and must be at least 10 characters."}), 400

    actor_id = int(get_jwt_identity())
    actor = Admin.query.get(actor_id)
    d = Device.query.get_or_404(device_id)

    if d.is_paired:
        return jsonify({"message": "Paired devices cannot be deleted."}), 400

    if d.vip_id is not None or len(d.guardian_links or []) > 0:
        return jsonify({"message": "Only unassigned devices can be deleted."}), 400

    deleted_serial = d.device_serial_number

    db.session.add(
        AdminAuditLog(
            actor_admin_id=actor_id,
            target_admin_id=None,
            action_type="device_delete",
            old_value_json=json.dumps(
                {
                    "deleted_device_id": d.device_id,
                    "deleted_device_serial": d.device_serial_number,
                    "is_paired": bool(d.is_paired),
                    "vip_id": d.vip_id,
                }
            ),
            new_value_json=None,
            reason_code=reason_code,
            reason_text=reason_text,
            status="success",
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=(request.user_agent.string or "")[:255],
        )
    )

    db.session.delete(d)
    db.session.commit()

    actor_name = (
        f"{(actor.first_name or '').strip()} {(actor.last_name or '').strip()}".strip()
        if actor else "A super admin"
    ) or "A super admin"
    actor_role = ((actor.role if actor and actor.role else "super_admin") or "super_admin").replace("_", " ").title()

    try:
        create_notification(
            audience="all_admins",
            type="device_deleted",
            title="Device deleted",
            body=f"{actor_name} ({actor_role}) deleted device {deleted_serial}.",
            link_path="/devices",
            related_admin_id=actor.admin_id if actor else None,
        )
    except Exception:
        pass

    return jsonify({"message": "Device deleted successfully."}), 200


@device_bp.route("/logs/", methods=["GET"])
@jwt_required()
def list_logs():
    err = require_admin()
    if err:
        return err
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    logs = (
        DeviceLog.query.order_by(DeviceLog.created_at.desc()).limit(limit).offset(offset).all()
    )
    return jsonify([_serialize_log(l) for l in logs]), 200


@device_bp.route("/<int:device_id>/logs/", methods=["GET"])
@jwt_required()
def list_device_logs(device_id):
    err = require_admin()
    if err:
        return err
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    logs = (
        DeviceLog.query.filter_by(device_id=device_id)
        .order_by(DeviceLog.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return jsonify([_serialize_log(l) for l in logs]), 200


@device_bp.route("/invitations/", methods=["GET"])
@jwt_required()
def list_invitations():
    err = require_admin()
    if err:
        return err
    invitations = GuardianInvitation.query.order_by(GuardianInvitation.id.desc()).all()
    return jsonify([_serialize_invitation(i) for i in invitations]), 200