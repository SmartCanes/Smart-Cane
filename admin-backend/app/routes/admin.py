import os
import uuid
import bcrypt
import json
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from werkzeug.utils import secure_filename
from app import db
from app.models import Admin, AdminArchive, AdminAuditLog, OTP
from app.routes.notifications import create_notification
from app.utils.admin_email_service import send_admin_otp_email, send_admin_invite_email
from datetime import datetime, timezone, timedelta
import random, string
from sqlalchemy import or_

admin_bp = Blueprint("admin", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_FILE_SIZE_MB   = 2
DELETED_ACCOUNT_MESSAGE = "This account has been deleted. Please contact the super administrator for assistance."



def require_super_admin():
    claims = get_jwt()
    if claims.get("role") != "super_admin":
        return jsonify({"message": "Access denied. Super admin only."}), 403
    return None


def require_admin_or_super_admin():
    claims = get_jwt()
    if claims.get("role") not in ("admin", "super_admin"):
        return jsonify({"message": "Access denied. Admin only."}), 403
    return None


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_otp(length=6):
    return "".join(random.choices(string.digits, k=length))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_folder() -> str:
    root: str = current_app.root_path or ""
    folder = os.path.join(root, "..", "static", "uploads", "profiles")
    os.makedirs(folder, exist_ok=True)
    return os.path.abspath(folder)


def _find_archived_admin_by_email(email: str):
    value = (email or "").strip()
    if not value:
        return None
    return AdminArchive.query.filter_by(email=value).first()


def _safe_json_loads(value):
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _matches_date_filter(created_at, date_filter):
    if date_filter == "all" or not created_at:
        return True

    now = datetime.now(timezone.utc)
    dt = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)

    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_filter == "today":
        return dt >= start_of_today

    if date_filter == "last7":
        return dt >= (start_of_today - timedelta(days=6))

    if date_filter == "last30":
        return dt >= (start_of_today - timedelta(days=29))

    if date_filter == "this_month":
        return dt.year == now.year and dt.month == now.month

    if date_filter == "this_year":
        return dt.year == now.year

    return True



@admin_bp.route("/", methods=["GET"])
@jwt_required()
def list_admins():
    admins = Admin.query.order_by(Admin.created_at.desc()).all()
    return jsonify([{
        "admin_id":          a.admin_id,
        "username":          a.username,
        "email":             a.email,
        "first_name":        a.first_name,
        "middle_name":       a.middle_name,
        "last_name":         a.last_name,
        "contact_number":    a.contact_number,
        "province":          a.province,
        "city":              a.city,
        "barangay":          a.barangay,
        "street_address":    a.street_address,
        "role":              a.role,
        "is_first_login":    a.is_first_login,
        "profile_image_url": a.profile_image_url,
        "created_at":        a.created_at.isoformat() if a.created_at else None,
    } for a in admins]), 200


@admin_bp.route("/create", methods=["POST"])
@jwt_required()
def create_admin():
    err = require_super_admin()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Request body must be JSON."}), 400

    for field in ["username", "email", "password", "first_name", "last_name"]:
        if not data.get(field, "").strip():
            return jsonify({"message": f"{field} is required."}), 400

    if Admin.query.filter_by(username=data["username"].strip()).first():
        return jsonify({"message": "Username already exists."}), 409
    if Admin.query.filter_by(email=data["email"].strip()).first():
        return jsonify({"message": "Email already exists."}), 409

    new_admin = Admin(
        username       = data["username"].strip(),
        email          = data["email"].strip(),
        password       = hash_password(data["password"].strip()),
        first_name     = data["first_name"].strip(),
        middle_name    = data.get("middle_name", "").strip() or None,
        last_name      = data["last_name"].strip(),
        contact_number = data.get("contact_number", "").strip() or None,
        province       = data.get("province", "").strip() or None,
        city           = data.get("city", "").strip() or None,
        barangay       = data.get("barangay", "").strip() or None,
        street_address = data.get("street_address", "").strip() or None,
        role           = data.get("role", "admin"),
        is_first_login = True,
    )
    db.session.add(new_admin)
    db.session.commit()

    frontend_urls = os.getenv("FRONTEND_URL", "http://localhost:5174")
    login_base = frontend_urls.split(",")[0].strip() or "http://localhost:5174"
    login_link = f"{login_base.rstrip('/')}/login"

    send_result = send_admin_invite_email(
        recipient_email=new_admin.email,
        login_link=login_link,
        temporary_username=new_admin.username,
        admin_name=new_admin.first_name,
    )
    email_sent = bool(send_result.get("ok"))
    email_error = send_result.get("error")

    actor_admin = Admin.query.get(int(get_jwt_identity()))
    actor_name = (
        f"{(actor_admin.first_name or '').strip()} {(actor_admin.last_name or '').strip()}".strip()
        if actor_admin else "An admin"
    )

    create_notification(
        audience="all_admins",
        type="admin_created",
        title="New admin created",
        body=(
            f"{actor_name} added {new_admin.first_name} {new_admin.last_name} "
            f"({new_admin.email})."
        ),
        link_path="/admins",
        related_admin_id=new_admin.admin_id,
    )
    return jsonify({"message": "Admin created successfully.", "admin_id": new_admin.admin_id}), 201


@admin_bp.route("/<int:target_id>/update", methods=["PUT"])
@jwt_required()
def update_admin(target_id):
    err = require_super_admin()
    if err:
        return err

    target = Admin.query.get_or_404(target_id)
    data   = request.get_json(silent=True) or {}

    new_username = data.get("username", "").strip()
    if new_username and new_username != target.username:
        clash = Admin.query.filter_by(username=new_username).first()
        if clash and clash.admin_id != target_id:
            return jsonify({"message": "Username already taken."}), 409

    new_email = data.get("email", "").strip()
    if new_email and new_email != target.email:
        clash = Admin.query.filter_by(email=new_email).first()
        if clash and clash.admin_id != target_id:
            return jsonify({"message": "Email already taken."}), 409

    target.first_name     = data.get("first_name",     target.first_name).strip()
    target.middle_name    = data.get("middle_name",     target.middle_name or "").strip() or None
    target.last_name      = data.get("last_name",       target.last_name).strip()
    target.username       = new_username or target.username
    target.email          = new_email    or target.email
    target.contact_number = data.get("contact_number",  target.contact_number or "").strip() or None
    target.province       = data.get("province",        target.province or "").strip() or None
    target.city           = data.get("city",             target.city or "").strip() or None
    target.barangay       = data.get("barangay",         target.barangay or "").strip() or None
    target.street_address = data.get("street_address",   target.street_address or "").strip() or None
    target.role           = data.get("role",             target.role)
    target.updated_at     = datetime.now(timezone.utc)

    new_password = data.get("password", "").strip()
    if new_password:
        target.password       = hash_password(new_password)
        target.is_first_login = True    # force the admin to go through first-login flow again

    db.session.commit()
    return jsonify({"message": "Admin updated successfully."}), 200


@admin_bp.route("/<int:target_id>/delete", methods=["DELETE"])
@jwt_required()
def delete_admin(target_id):
    # Archive row then delete from admin_tbl.
    err = require_super_admin()
    if err:
        return err

    caller_id = int(get_jwt_identity())

    # Prevent super-admin from deleting themselves
    if caller_id == target_id:
        return jsonify({"message": "You cannot delete your own account."}), 400

    data = request.get_json(silent=True) or {}
    reason_code = str(data.get("reason_code", "")).strip()
    reason_text = str(data.get("reason_text", "")).strip()

    if not reason_code:
        return jsonify({"message": "reason_code is required."}), 400
    if len(reason_text) < 10:
        return jsonify({"message": "reason_text is required and must be at least 10 characters."}), 400

    target = Admin.query.get_or_404(target_id)
    actor = Admin.query.get(caller_id)
    deleted_name = " ".join(
        p for p in [target.first_name, target.middle_name, target.last_name] if p
    ).strip() or target.username

    archive = AdminArchive(
        admin_id            = target.admin_id,
        username            = target.username,
        email               = target.email,
        password            = target.password,
        first_name          = target.first_name,
        middle_name         = target.middle_name,
        last_name           = target.last_name,
        contact_number      = target.contact_number,
        province            = target.province,
        city                = target.city,
        barangay            = target.barangay,
        street_address      = target.street_address,
        role                = target.role,
        profile_image_url   = target.profile_image_url,
        original_created_at = target.created_at,
        archived_at         = datetime.now(timezone.utc),
        archived_by         = caller_id,
    )
    db.session.add(archive)

    db.session.add(
        AdminAuditLog(
            actor_admin_id=caller_id,
            target_admin_id=None,
            action_type="admin_delete",
            old_value_json=json.dumps({
                "deleted_admin_id": target.admin_id,
                "full_name": " ".join(
                    p for p in [target.first_name, target.middle_name, target.last_name] if p
                ).strip(),
                "username": target.username,
                "email": target.email,
                "role": target.role,
                "was_first_login": bool(target.is_first_login),
            }),
            new_value_json=None,
            reason_code=reason_code,
            reason_text=reason_text,
            status="success",
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=(request.user_agent.string or "")[:255],
        )
    )

    db.session.delete(target)
    db.session.commit()

    actor_name = (
        f"{(actor.first_name or '').strip()} {(actor.last_name or '').strip()}".strip()
        if actor else "A super admin"
    ) or "A super admin"
    actor_role = ((actor.role if actor and actor.role else "super_admin") or "super_admin").replace("_", " ").title()

    create_notification(
        audience="all_admins",
        type="admin_deleted",
        title="Admin account deleted",
        body=f"{actor_name} ({actor_role}) deleted admin account {deleted_name} ({target.email}).",
        link_path="/admins",
        related_admin_id=caller_id,
    )

    return jsonify({"message": "Admin deleted and archived successfully."}), 200


@admin_bp.route("/audit-logs", methods=["GET"])
@jwt_required()
def list_audit_logs():
    err = require_admin_or_super_admin()
    if err:
        return err

    page = max(int(request.args.get("page", 1)), 1)
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    q = (request.args.get("q", "") or "").strip()
    action_type = (request.args.get("action_type", "") or "").strip()
    date_filter = (request.args.get("date_filter", "all") or "all").strip().lower()

    query = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc())

    if action_type:
        query = query.filter(AdminAuditLog.action_type == action_type)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                AdminAuditLog.action_type.ilike(like),
                AdminAuditLog.reason_code.ilike(like),
                AdminAuditLog.reason_text.ilike(like),
                AdminAuditLog.old_value_json.ilike(like),
                AdminAuditLog.new_value_json.ilike(like),
            )
        )

    rows = query.all()
    filtered_rows = [row for row in rows if _matches_date_filter(row.created_at, date_filter)]

    total = len(filtered_rows)
    start = (page - 1) * limit
    end = start + limit
    page_rows = filtered_rows[start:end]

    items = []
    for row in page_rows:
        old_data = _safe_json_loads(row.old_value_json)
        actor = row.actor_admin
        actor_name = " ".join(
            p for p in [getattr(actor, "first_name", None), getattr(actor, "last_name", None)] if p
        ).strip() or "Unknown"

        deleted_admin_name = (
            old_data.get("full_name")
            or old_data.get("deleted_admin_name")
            or old_data.get("username")
            or ""
        )
        deleted_concern_message = (
            old_data.get("deleted_concern_message")
            or old_data.get("message")
            or ""
        )
        deleted_device_serial = (
            old_data.get("deleted_device_serial")
            or old_data.get("device_serial_number")
            or ""
        )

        created_at = row.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        items.append(
            {
                "audit_id": row.audit_id,
                "actor_admin_id": row.actor_admin_id,
                "target_admin_id": row.target_admin_id,
                "actor_name": actor_name,
                "action_type": row.action_type,
                "reason_code": row.reason_code,
                "reason_text": row.reason_text,
                "status": row.status,
                "created_at": created_at.isoformat().replace("+00:00", "Z") if created_at else None,
                "deleted_admin_name": deleted_admin_name,
                "deleted_concern_message": deleted_concern_message,
                "deleted_device_serial": deleted_device_serial,
            }
        )

    return jsonify({"items": items, "total": total, "page": page, "limit": limit}), 200



@admin_bp.route("/request-otp", methods=["POST"])
def request_otp():
    data  = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"message": "Email is required."}), 400
    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        archived = _find_archived_admin_by_email(email)
        if archived:
            return jsonify({"message": DELETED_ACCOUNT_MESSAGE}), 403
        return jsonify({"message": "If that email exists, an OTP has been sent."}), 200

    OTP.query.filter_by(email=email, purpose="first_login", is_used=False).update({"is_used": True})
    db.session.commit()

    code       = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    otp = OTP(email=email, otp_code=code, is_used=False, expires_at=expires_at, purpose="first_login")
    db.session.add(otp)
    db.session.commit()

    send_admin_otp_email(recipient_email=email, otp_code=code, admin_name=admin.first_name)
    return jsonify({"message": "OTP sent to email."}), 200


@admin_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data     = request.get_json(silent=True) or {}
    email    = data.get("email",    "").strip()
    otp_code = data.get("otp_code", "").strip()
    if not email or not otp_code:
        return jsonify({"message": "email and otp_code are required."}), 400

    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        archived = _find_archived_admin_by_email(email)
        if archived:
            return jsonify({"message": DELETED_ACCOUNT_MESSAGE}), 403

    otp = OTP.query.filter_by(email=email, otp_code=otp_code, is_used=False, purpose="first_login").first()
    if not otp:
        return jsonify({"message": "Invalid OTP."}), 400
    if datetime.now(timezone.utc) > otp.expires_at.replace(tzinfo=timezone.utc):
        return jsonify({"message": "OTP has expired. Please request a new one."}), 400

    otp.is_used = True
    otp.used_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"message": "OTP verified. You may now change your credentials."}), 200


@admin_bp.route("/change-credentials", methods=["POST"])
def change_credentials():
    data         = request.get_json(silent=True) or {}
    email        = data.get("email",        "").strip()
    new_username = data.get("new_username", "").strip()
    new_password = data.get("new_password", "").strip()
    if not email or not new_username or not new_password:
        return jsonify({"message": "email, new_username, and new_password are required."}), 400

    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        archived = _find_archived_admin_by_email(email)
        if archived:
            return jsonify({"message": DELETED_ACCOUNT_MESSAGE}), 403
        return jsonify({"message": "Admin not found."}), 404

    existing = Admin.query.filter_by(username=new_username).first()
    if existing and existing.admin_id != admin.admin_id:
        return jsonify({"message": "Username already taken."}), 409

    admin.username       = new_username
    admin.password       = hash_password(new_password)     # ← bcrypt hashed
    admin.is_first_login = False
    admin.updated_at     = datetime.now(timezone.utc)
    db.session.commit()

    create_notification(
        audience="super_admins",
        type="admin_setup_completed",
        title="Admin completed account setup",
        body=f"{admin.first_name} {admin.last_name} finished setting up their account.",
        link_path="/admins",
        related_admin_id=admin.admin_id,
    )
    return jsonify({"message": "Credentials updated successfully."}), 200



@admin_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    admin_id = int(get_jwt_identity())
    admin    = Admin.query.get_or_404(admin_id)
    return jsonify({
        "admin_id":          admin.admin_id,
        "username":          admin.username,
        "email":             admin.email,
        "first_name":        admin.first_name,
        "middle_name":       admin.middle_name,
        "last_name":         admin.last_name,
        "contact_number":    admin.contact_number,
        "province":          admin.province,
        "city":              admin.city,
        "barangay":          admin.barangay,
        "street_address":    admin.street_address,
        "role":              admin.role,
        "profile_image_url": admin.profile_image_url,
        "created_at":        admin.created_at.isoformat() if admin.created_at else None,
    }), 200


@admin_bp.route("/profile/update", methods=["PUT"])
@jwt_required()
def update_profile():
    admin_id = int(get_jwt_identity())
    admin    = Admin.query.get_or_404(admin_id)
    data     = request.get_json(silent=True) or {}

    new_username = data.get("username", "").strip()
    if new_username and new_username != admin.username:
        existing = Admin.query.filter_by(username=new_username).first()
        if existing and existing.admin_id != admin_id:
            return jsonify({"message": "Username already taken."}), 409

    admin.first_name     = data.get("first_name",     admin.first_name).strip()
    admin.middle_name    = data.get("middle_name",     admin.middle_name or "").strip() or None
    admin.last_name      = data.get("last_name",       admin.last_name).strip()
    admin.username       = new_username or admin.username
    admin.contact_number = data.get("contact_number",  admin.contact_number or "").strip() or None
    admin.province       = data.get("province",        admin.province or "").strip() or None
    admin.city           = data.get("city",             admin.city or "").strip() or None
    admin.barangay       = data.get("barangay",         admin.barangay or "").strip() or None
    admin.street_address = data.get("street_address",   admin.street_address or "").strip() or None
    admin.updated_at     = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"message": "Profile updated successfully."}), 200


@admin_bp.route("/profile/upload-image", methods=["POST"])
@jwt_required()
def upload_image():
    admin_id = int(get_jwt_identity())
    admin    = Admin.query.get_or_404(admin_id)

    if "image" not in request.files:
        return jsonify({"message": "No image file provided."}), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({"message": "No file selected."}), 400
    if not allowed_file(file.filename):
        return jsonify({"message": "Only PNG, JPG, JPEG, and WEBP files are allowed."}), 400

    file.seek(0, os.SEEK_END)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if size_mb > MAX_FILE_SIZE_MB:
        return jsonify({"message": f"Image must be under {MAX_FILE_SIZE_MB}MB."}), 400

    if admin.profile_image_url:
        old_filename = admin.profile_image_url.split("/")[-1]
        old_path     = os.path.join(get_upload_folder(), old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    ext          = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    new_filename = f"admin_{admin_id}_{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(get_upload_folder(), new_filename))

    base_url  = request.host_url.rstrip("/")
    image_url = f"{base_url}/static/uploads/profiles/{new_filename}"

    admin.profile_image_url = image_url
    admin.updated_at        = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"message": "Profile image uploaded successfully.", "profile_image_url": image_url}), 200


@admin_bp.route("/profile/remove-image", methods=["DELETE"])
@jwt_required()
def remove_image():
    admin_id = int(get_jwt_identity())
    admin    = Admin.query.get_or_404(admin_id)

    if admin.profile_image_url:
        old_filename = admin.profile_image_url.split("/")[-1]
        old_path     = os.path.join(get_upload_folder(), old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)
        admin.profile_image_url = None
        admin.updated_at        = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({"message": "Profile image removed."}), 200


@admin_bp.route("/profile/request-email-otp", methods=["POST"])
@jwt_required()
def request_email_otp():
    admin_id  = int(get_jwt_identity())
    admin     = Admin.query.get_or_404(admin_id)
    data      = request.get_json(silent=True) or {}
    new_email = data.get("new_email", "").strip()

    if not new_email:
        return jsonify({"message": "new_email is required."}), 400
    if new_email == admin.email:
        return jsonify({"message": "New email must be different from current email."}), 400

    existing = Admin.query.filter_by(email=new_email).first()
    if existing and existing.admin_id != admin_id:
        return jsonify({"message": "Email already in use by another account."}), 409

    OTP.query.filter_by(email=new_email, purpose="email_change", is_used=False).update({"is_used": True})
    db.session.commit()

    code       = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    otp = OTP(email=new_email, otp_code=code, is_used=False, expires_at=expires_at, purpose="email_change")
    db.session.add(otp)
    db.session.commit()

    send_admin_otp_email(recipient_email=new_email, otp_code=code, admin_name=admin.first_name)
    return jsonify({"message": "OTP sent to new email."}), 200


@admin_bp.route("/profile/verify-email-otp", methods=["POST"])
@jwt_required()
def verify_email_otp():
    admin_id  = int(get_jwt_identity())
    admin     = Admin.query.get_or_404(admin_id)
    data      = request.get_json(silent=True) or {}
    new_email = data.get("new_email", "").strip()
    otp_code  = data.get("otp_code",  "").strip()

    if not new_email or not otp_code:
        return jsonify({"message": "new_email and otp_code are required."}), 400

    otp = OTP.query.filter_by(email=new_email, otp_code=otp_code, is_used=False, purpose="email_change").first()
    if not otp:
        return jsonify({"message": "Invalid OTP."}), 400
    if datetime.now(timezone.utc) > otp.expires_at.replace(tzinfo=timezone.utc):
        return jsonify({"message": "OTP has expired. Please request a new one."}), 400

    otp.is_used      = True
    otp.used_at      = datetime.now(timezone.utc)
    admin.email      = new_email
    admin.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"message": "Email updated successfully."}), 200