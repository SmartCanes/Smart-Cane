from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import GuardianConcern, Admin, AdminAuditLog
from app.models import Notification, NotificationRead
from datetime import datetime, timezone
import logging
import json
from sqlalchemy import and_

logger = logging.getLogger(__name__)

concerns_bp = Blueprint("concerns", __name__, url_prefix="/api/guardian-concerns")


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
    Returns all guardian concerns, optionally filtered by status.
    Query parameter: ?status=unread|read|resolved
    """
    try:
        status = request.args.get("status")
        query = GuardianConcern.query.filter_by(is_deleted=False)
        if status and status in ["unread", "read", "resolved"]:
            query = query.filter_by(status=status)
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
        "admin_reply": "optional reply text"
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

        # Update status if provided
        if "status" in data:
            new_status = data["status"]
            if new_status not in ("unread", "read", "resolved"):
                return jsonify({"error": "Invalid status"}), 400
            concern.status = new_status

        # Update admin reply if provided
        if "admin_reply" in data:
            # Only set reply metadata if the reply text is actually provided
            if data["admin_reply"]:
                concern.admin_reply = data["admin_reply"]
                # If this is a new reply (was empty), set the admin who replied
                if not concern.replied_by_admin_id:
                    concern.replied_by_admin_id = g.current_admin.admin_id
                    concern.replied_at = datetime.now(timezone.utc)
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
        return jsonify({"message": "Concern deleted successfully"})

    except Exception as e:
        db.session.rollback()
        logger.exception("Error deleting concern %s", concern_id)
        return jsonify({"error": "Internal server error"}), 500