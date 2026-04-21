from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import GuardianConcern, Admin, AdminAuditLog
from app.models import Notification, NotificationRead
from app.routes.notifications import create_notification
from datetime import datetime, timezone
import logging
import json
from sqlalchemy import and_

logger = logging.getLogger(__name__)

concerns_bp = Blueprint("concerns", __name__, url_prefix="/api/guardian-concerns")

CONCERN_STATUS_OPTIONS = {"unread", "read", "resolved"}
CONCERN_PROCESS_OPTIONS = (
    "new",
    "acknowledged",
    "ongoing",
    "awaiting_client",
    "escalated",
    "resolved",
    "failed_to_resolve",
)
CONCERN_PROCESS_OPTION_SET = set(CONCERN_PROCESS_OPTIONS)
PROCESS_REQUIRES_REMARKS = {"failed_to_resolve", "escalated"}


# Helper: get current admin from JWT
def get_current_admin():
    """Return the Admin instance of the authenticated user."""
    admin_id = get_jwt_identity()
    return Admin.query.get(admin_id)


# Helper: admin access decorator (role: admin or super_admin)
def admin_required(f):
    from functools import wraps

    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if not admin or admin.role not in ("admin", "super_admin"):
            return jsonify({"error": "Admin access required"}), 403
        g.current_admin = admin   # store for later use if needed
        return f(*args, **kwargs)
    return decorated


# Helper: super admin only decorator
def super_admin_required(f):
    from functools import wraps

    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if not admin or admin.role != "super_admin":
            return jsonify({"error": "Super admin access required"}), 403
        g.current_admin = admin
        return f(*args, **kwargs)
    return decorated


# GET all concerns (admin only)
@concerns_bp.route("/", methods=["GET"])
@admin_required
def get_concerns():
    """
    Returns all guardian concerns, optionally filtered by status/process.
    Query parameters:
      ?status=unread|read|resolved
      ?process_stage=<single or comma-separated process stages>
    """
    try:
        status = request.args.get("status")
        process_stage = request.args.get("process_stage")
        query = GuardianConcern.query.filter_by(is_deleted=False)

        if status:
            statuses = {
                s.strip().lower() for s in status.split(",") if s and s.strip()
            }
            valid_statuses = statuses.intersection(CONCERN_STATUS_OPTIONS)
            if valid_statuses:
                query = query.filter(GuardianConcern.status.in_(valid_statuses))

        if process_stage:
            process_stages = {
                p.strip().lower() for p in process_stage.split(",") if p and p.strip()
            }
            valid_process_stages = process_stages.intersection(CONCERN_PROCESS_OPTION_SET)
            if valid_process_stages:
                query = query.filter(GuardianConcern.process_stage.in_(valid_process_stages))

        concerns = query.order_by(GuardianConcern.created_at.desc()).all()
        return jsonify([c.to_dict() for c in concerns])
    except Exception as e:
        logger.exception("Error fetching guardian concerns")
        return jsonify({"error": "Internal server error"}), 500


# PATCH update a concern (admin only)
@concerns_bp.route("/<int:concern_id>", methods=["PATCH"])
@admin_required
def update_concern(concern_id):
    """
    Update status and optionally admin_reply.
    Expected JSON: {
        "status": "unread|read|resolved",
        "admin_reply": "optional reply text",
        "process_stage": "new|acknowledged|ongoing|awaiting_client|escalated|resolved|failed_to_resolve",
        "resolution_remarks": "optional remarks"
    }
    """
    try:
        concern = GuardianConcern.query.get(concern_id)
        if not concern:
            return jsonify({"error": "Concern not found"}), 404
        if concern.is_deleted:
            return jsonify({"error": "Concern not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request body"}), 400

        now = datetime.now(timezone.utc)

        # Update status if provided
        if "status" in data:
            new_status = str(data["status"] or "").strip().lower()
            if new_status not in CONCERN_STATUS_OPTIONS:
                return jsonify({"error": "Invalid status"}), 400
            concern.status = new_status

            # Keep process stage aligned for direct status-only updates.
            if "process_stage" not in data:
                if new_status == "unread":
                    concern.process_stage = "new"
                    concern.process_updated_by_admin_id = g.current_admin.admin_id
                    concern.process_updated_at = now
                elif new_status == "read" and concern.process_stage == "new":
                    concern.process_stage = "acknowledged"
                    concern.process_updated_by_admin_id = g.current_admin.admin_id
                    concern.process_updated_at = now
                elif new_status == "resolved":
                    concern.process_stage = "resolved"
                    concern.process_updated_by_admin_id = g.current_admin.admin_id
                    concern.process_updated_at = now

        if "process_stage" in data:
            next_process_stage = str(data["process_stage"] or "").strip().lower()
            if next_process_stage not in CONCERN_PROCESS_OPTION_SET:
                return jsonify({"error": "Invalid process_stage"}), 400

            next_remarks = concern.resolution_remarks
            if "resolution_remarks" in data:
                next_remarks = str(data.get("resolution_remarks") or "").strip() or None

            if next_process_stage in PROCESS_REQUIRES_REMARKS and not next_remarks:
                return jsonify({"error": "resolution_remarks is required for the selected process_stage"}), 400

            concern.process_stage = next_process_stage
            concern.process_updated_by_admin_id = g.current_admin.admin_id
            concern.process_updated_at = now

            # Auto-sync coarse status from process stage.
            if next_process_stage == "resolved":
                concern.status = "resolved"
            elif next_process_stage == "new":
                concern.status = "unread"
            elif next_process_stage in {
                "acknowledged",
                "ongoing",
                "awaiting_client",
                "escalated",
                "failed_to_resolve",
            }:
                concern.status = "read"

        if "resolution_remarks" in data:
            remarks = str(data.get("resolution_remarks") or "").strip()
            current_stage = (
                str(concern.process_stage or "").strip().lower() or "new"
            )
            if current_stage in PROCESS_REQUIRES_REMARKS and not remarks:
                return jsonify({"error": "resolution_remarks is required for the selected process_stage"}), 400
            concern.resolution_remarks = remarks or None
            concern.process_updated_by_admin_id = g.current_admin.admin_id
            concern.process_updated_at = now

        # Update admin reply if provided
        if "admin_reply" in data:
            reply_text = str(data.get("admin_reply") or "").strip()
            # Only set reply metadata if the reply text is actually provided
            if reply_text:
                concern.admin_reply = reply_text
                # If this is a new reply (was empty), set the admin who replied
                if not concern.replied_by_admin_id:
                    concern.replied_by_admin_id = g.current_admin.admin_id
                concern.replied_at = now
            else:
                # Clearing the reply text -> also clear metadata
                concern.admin_reply = None
                concern.replied_by_admin_id = None
                concern.replied_at = None

        db.session.commit()

        # Keep notification read-state in sync for the current admin
        if concern.status in ("read", "resolved"):
            n = Notification.query.filter(
                and_(
                    Notification.type == "guardian_concern",
                    Notification.related_concern_id == concern.concern_id,
                )
            ).order_by(Notification.created_at.desc()).first()
            if n:
                existing = NotificationRead.query.filter_by(
                    notification_id=n.notification_id,
                    admin_id=g.current_admin.admin_id,
                ).first()
                if not existing:
                    db.session.add(
                        NotificationRead(
                            notification_id=n.notification_id,
                            admin_id=g.current_admin.admin_id,
                            read_at=datetime.now(timezone.utc),
                        )
                    )
                    db.session.commit()
        return jsonify(concern.to_dict())

    except Exception as e:
        db.session.rollback()
        logger.exception("Error updating concern %s", concern_id)
        return jsonify({"error": "Internal server error"}), 500


# DELETE a concern (super admin only)
@concerns_bp.route("/<int:concern_id>", methods=["DELETE"])
@super_admin_required
def delete_concern(concern_id):
    """
    Soft-delete a guardian concern. Super admin only.
    """
    try:
        concern = GuardianConcern.query.get(concern_id)
        if not concern:
            return jsonify({"error": "Concern not found"}), 404

        if concern.is_deleted:
            return jsonify({"error": "Concern already deleted"}), 400

        data = request.get_json(silent=True) or {}
        reason_code = str(data.get("reason_code", "")).strip()
        reason_text = str(data.get("reason_text", "")).strip()

        if not reason_code:
            return jsonify({"error": "reason_code is required"}), 400
        if len(reason_text) < 10:
            return jsonify({"error": "reason_text is required and must be at least 10 characters"}), 400

        concern.is_deleted = True
        concern.deleted_at = datetime.now(timezone.utc)
        concern.deleted_by_admin_id = g.current_admin.admin_id
        concern.deleted_reason_code = reason_code
        concern.deleted_reason_text = reason_text

        db.session.add(
            AdminAuditLog(
                actor_admin_id=g.current_admin.admin_id,
                target_concern_id=concern.concern_id,
                action_type="concern_delete",
                old_value_json=json.dumps(
                    {
                        "concern_id": concern.concern_id,
                        "name": concern.name,
                        "email": concern.email,
                        "message": concern.message,
                        "status": concern.status,
                    }
                ),
                new_value_json=json.dumps({"is_deleted": True}),
                reason_code=reason_code,
                reason_text=reason_text,
                status="success",
                ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
                user_agent=(request.user_agent.string or "")[:255],
            )
        )

        db.session.commit()

        try:
            actor_name = (
                " ".join(
                    part for part in [g.current_admin.first_name, g.current_admin.last_name] if part
                ).strip()
                or "A super admin"
            )
            actor_role = (g.current_admin.role or "super_admin").replace("_", " ")
            create_notification(
                audience="all_admins",
                type="concern_deleted",
                title="Guardian concern deleted",
                body=(
                    f"{actor_name} ({actor_role}) deleted a concern from {concern.name} "
                    f"({concern.email}). Reason: {reason_code.replace('_', ' ')}."
                ),
                link_path="/guardian-concerns",
                related_admin_id=g.current_admin.admin_id,
            )
        except Exception:
            pass

        return jsonify({"message": "Concern deleted successfully"})

    except Exception as e:
        db.session.rollback()
        logger.exception("Error deleting concern %s", concern_id)
        return jsonify({"error": "Internal server error"}), 500