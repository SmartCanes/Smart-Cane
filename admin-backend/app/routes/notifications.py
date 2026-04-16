from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from sqlalchemy import exists, and_
from app import db
from app.models import Notification, NotificationRead, GuardianConcern, Admin
from datetime import datetime, timezone


notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


def _as_utc_iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _current_admin():
    admin_id = int(get_jwt_identity())
    return Admin.query.get(admin_id)


def _ensure_concern_notifications(limit: int = 50):
    # Sync notification rows for concerns submitted outside the admin app.
    concerns = (
        GuardianConcern.query.order_by(GuardianConcern.created_at.desc())
        .limit(limit)
        .all()
    )

    created_any = False
    for c in concerns:
        already = db.session.query(
            exists().where(
                and_(
                    Notification.type == "guardian_concern",
                    Notification.related_concern_id == c.concern_id,
                )
            )
        ).scalar()
        if already:
            continue

        n = Notification(
            audience="all_admins",
            type="guardian_concern",
            title="New guardian concern",
            body=f"{c.name}: {c.message[:120]}{'…' if c.message and len(c.message) > 120 else ''}",
            link_path="/guardian-concerns",
            related_concern_id=c.concern_id,
        )
        db.session.add(n)
        created_any = True

    if created_any:
        db.session.commit()


@notifications_bp.route("", methods=["GET"], strict_slashes=False)
@notifications_bp.route("/", methods=["GET"], strict_slashes=False)
@jwt_required()
def list_notifications():
    admin = _current_admin()
    if not admin or admin.role not in ("admin", "super_admin"):
        return jsonify({"message": "Admin access required."}), 403

    _ensure_concern_notifications()

    limit = int(request.args.get("limit", 20))
    limit = max(1, min(limit, 50))

    allowed_audiences = ["all_admins"]
    if admin.role == "super_admin":
        allowed_audiences.append("super_admins")
    rows = (
        db.session.query(Notification, NotificationRead)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.notification_id,
                NotificationRead.admin_id == admin.admin_id,
            ),
        )
        .filter(Notification.audience.in_(allowed_audiences))
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    unread_count = 0
    for n, r in rows:
        is_read = r is not None
        if not is_read:
            unread_count += 1
        d = n.to_dict()
        d["created_at"] = _as_utc_iso(n.created_at)
        d["is_read"] = is_read
        d["read_at"] = _as_utc_iso(r.read_at) if r and r.read_at else None
        items.append(d)

    return jsonify({"items": items, "unread_count": unread_count}), 200


@notifications_bp.route("/<int:notification_id>/read", methods=["PATCH"])
@jwt_required()
def mark_read(notification_id: int):
    admin = _current_admin()
    if not admin or admin.role not in ("admin", "super_admin"):
        return jsonify({"message": "Admin access required."}), 403

    n = Notification.query.get_or_404(notification_id)

    allowed_audiences = {"all_admins"}
    if admin.role == "super_admin":
        allowed_audiences.add("super_admins")
    if n.audience not in allowed_audiences:
        return jsonify({"message": "Not allowed."}), 403

    existing = NotificationRead.query.filter_by(
        notification_id=notification_id, admin_id=admin.admin_id
    ).first()
    if existing:
        return jsonify({"message": "Already read."}), 200

    db.session.add(
        NotificationRead(
            notification_id=notification_id,
            admin_id=admin.admin_id,
            read_at=datetime.now(timezone.utc),
        )
    )
    db.session.commit()
    return jsonify({"message": "Marked as read."}), 200


@notifications_bp.route("/read-all", methods=["PATCH"])
@jwt_required()
def mark_all_read():
    admin = _current_admin()
    if not admin or admin.role not in ("admin", "super_admin"):
        return jsonify({"message": "Admin access required."}), 403

    allowed_audiences = ["all_admins"]
    if admin.role == "super_admin":
        allowed_audiences.append("super_admins")

    notif_ids = [
        n.notification_id
        for n in Notification.query.filter(Notification.audience.in_(allowed_audiences)).all()
    ]

    if not notif_ids:
        return jsonify({"message": "No notifications."}), 200

    existing_ids = {
        r.notification_id
        for r in NotificationRead.query.filter(
            NotificationRead.admin_id == admin.admin_id,
            NotificationRead.notification_id.in_(notif_ids),
        ).all()
    }

    now = datetime.now(timezone.utc)
    for nid in notif_ids:
        if nid in existing_ids:
            continue
        db.session.add(
            NotificationRead(
                notification_id=nid,
                admin_id=admin.admin_id,
                read_at=now,
            )
        )

    db.session.commit()
    return jsonify({"message": "All marked as read."}), 200


def create_notification(
    *,
    audience: str,
    type: str,
    title: str,
    body: str | None = None,
    link_path: str | None = None,
    related_concern_id: int | None = None,
    related_admin_id: int | None = None,
):
    n = Notification(
        audience=audience,
        type=type,
        title=title,
        body=body,
        link_path=link_path,
        related_concern_id=related_concern_id,
        related_admin_id=related_admin_id,
    )
    db.session.add(n)
    db.session.commit()
    return n

