import bcrypt                                        # ← pip install bcrypt
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from app.models import Admin, AdminArchive, LoginAttempt, OTP
from app.utils.admin_email_service import send_admin_otp_email
from datetime import datetime, timezone, timedelta
import random, string

auth_bp = Blueprint("auth", __name__)

DELETED_ACCOUNT_MESSAGE = "This account has been deleted. Please contact the super administrator for assistance."


def _record_attempt(username, ip):
    """Save every login attempt to the DB for audit purposes."""
    attempt = LoginAttempt(
        username=username,
        ip_address=ip,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(attempt)
    db.session.commit()


def _check_password(stored: str, plain: str) -> bool:
    """
    Accepts both bcrypt hashes (new) and legacy plain-text passwords (old rows).
    Once all passwords are migrated to bcrypt you can remove the plain-text branch.
    """
    if stored.startswith(("$2b$", "$2a$")):
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    # Legacy plain-text fallback — remove this after migration
    return stored == plain


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _find_archived_admin_by_identifier(identifier: str):
    value = (identifier or "").strip()
    if not value:
        return None
    return AdminArchive.query.filter(
        (AdminArchive.username == value) | (AdminArchive.email == value)
    ).first()


def _find_archived_admin_by_email(email: str):
    value = (email or "").strip()
    if not value:
        return None
    return AdminArchive.query.filter_by(email=value).first()


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"message": "Request body must be JSON."}), 400

    identifier = (data.get("identifier") or "").strip()
    password   = (data.get("password")   or "").strip()

    if not identifier or not password:
        return jsonify({"message": "identifier and password are required."}), 400

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    admin = Admin.query.filter(
        (Admin.username == identifier) | (Admin.email == identifier)
    ).first()

    _record_attempt(identifier, ip)

    if admin is None:
        archived = _find_archived_admin_by_identifier(identifier)
        if archived:
            return jsonify({"message": DELETED_ACCOUNT_MESSAGE}), 403
        return jsonify({"message": "Invalid credentials."}), 401

    if not _check_password(admin.password, password):
        return jsonify({"message": "Invalid credentials."}), 401

    access_token = create_access_token(
        identity=str(admin.admin_id),
        additional_claims={
            "role":  admin.role,
            "email": admin.email,
            "type":  "admin",
        },
    )

    return jsonify({
        "access_token":   access_token,
        "admin_id":       admin.admin_id,
        "role":           admin.role,
        "first_name":     admin.first_name,
        "last_name":      admin.last_name,
        "email":          admin.email,
        "is_first_login": admin.is_first_login,
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    admin_id = int(get_jwt_identity())
    admin = Admin.query.get_or_404(admin_id)

    return jsonify({
        "admin_id":       admin.admin_id,
        "username":       admin.username,
        "email":          admin.email,
        "first_name":     admin.first_name,
        "middle_name":    admin.middle_name,
        "last_name":      admin.last_name,
        "contact_number": admin.contact_number,
        "province":       admin.province,
        "city":           admin.city,
        "barangay":       admin.barangay,
        "street_address": admin.street_address,
        "role":           admin.role,
        "is_first_login": admin.is_first_login,
        "created_at":     admin.created_at.isoformat() if admin.created_at else None,
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    return jsonify({"message": "Logged out successfully."}), 200


# PASSWORD RESET (no auth required)
@auth_bp.route("/password-reset/request-otp", methods=["POST"])
def password_reset_request_otp():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"message": "Email is required."}), 400

    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        archived = _find_archived_admin_by_email(email)
        if archived:
            return jsonify({"message": DELETED_ACCOUNT_MESSAGE}), 403
        # Avoid leaking whether an email exists
        return jsonify({"message": "If that email exists, an OTP has been sent."}), 200

    OTP.query.filter_by(email=email, purpose="password_reset", is_used=False).update(
        {"is_used": True}
    )
    db.session.commit()

    code = _generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    otp = OTP(
        email=email,
        otp_code=code,
        is_used=False,
        expires_at=expires_at,
        purpose="password_reset",
    )
    db.session.add(otp)
    db.session.commit()

    send_admin_otp_email(recipient_email=email, otp_code=code, admin_name=admin.first_name)
    return jsonify({"message": "If that email exists, an OTP has been sent."}), 200


@auth_bp.route("/password-reset/verify-otp", methods=["POST"])
def password_reset_verify_otp():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    otp_code = (data.get("otp_code") or "").strip()
    if not email or not otp_code:
        return jsonify({"message": "email and otp_code are required."}), 400

    otp = OTP.query.filter_by(
        email=email,
        otp_code=otp_code,
        is_used=False,
        purpose="password_reset",
    ).first()
    if not otp:
        return jsonify({"message": "Invalid OTP."}), 400

    if datetime.now(timezone.utc) > otp.expires_at.replace(tzinfo=timezone.utc):
        return jsonify({"message": "OTP has expired. Please request a new one."}), 400

    return jsonify({"message": "OTP verified."}), 200


@auth_bp.route("/password-reset/reset", methods=["POST"])
def password_reset_reset():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    otp_code = (data.get("otp_code") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if not email or not otp_code or not new_password:
        return jsonify({"message": "email, otp_code, and new_password are required."}), 400

    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        archived = _find_archived_admin_by_email(email)
        if archived:
            return jsonify({"message": DELETED_ACCOUNT_MESSAGE}), 403
        return jsonify({"message": "Invalid request."}), 400

    otp = OTP.query.filter_by(
        email=email,
        otp_code=otp_code,
        is_used=False,
        purpose="password_reset",
    ).first()
    if not otp:
        return jsonify({"message": "Invalid OTP."}), 400

    if datetime.now(timezone.utc) > otp.expires_at.replace(tzinfo=timezone.utc):
        return jsonify({"message": "OTP has expired. Please request a new one."}), 400

    admin.password = _hash_password(new_password)
    admin.is_first_login = False
    admin.updated_at = datetime.now(timezone.utc)

    otp.is_used = True
    otp.used_at = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({"message": "Password updated successfully."}), 200