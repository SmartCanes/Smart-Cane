from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from .. import db
from ..models import DeviceLog, Device 

emergency_bp = Blueprint("emergency", __name__)


def require_admin():
    claims = get_jwt()
    if claims.get("role") not in ("super_admin", "admin"):
        return jsonify({"message": "Access denied."}), 403
    return None


def _extract_location(metadata_json):
    """
    Pull the human-readable location label out of metadata_json.
    Tries multiple known key paths used by the frontend normalizer.
    """
    if not metadata_json or not isinstance(metadata_json, dict):
        return None

    payload = metadata_json.get("payload") or {}

    candidates = [
        # payload-level keys (set by pushRealtimeAlertLog)
        payload.get("location"),
        payload.get("locationLabel"),
        payload.get("address"),
        payload.get("placeName"),
        # top-level fallbacks
        metadata_json.get("location"),
        metadata_json.get("locationLabel"),
        metadata_json.get("address"),
    ]

    for c in candidates:
        if isinstance(c, str) and c.strip():
            return c.strip()

    # Last resort: return raw coords string if available
    lat = payload.get("lat") or metadata_json.get("lat")
    lng = payload.get("lng") or metadata_json.get("lng")
    if lat is not None and lng is not None:
        try:
            return f"{float(lat):.6f}, {float(lng):.6f}"
        except (TypeError, ValueError):
            pass

    return None


# Source: DEVICE_LOG_TYPE_ALIASES in deviceLogs.js
EMERGENCY_TYPES = [
    # Emergency / SOS variants
    "EMERGENCY",
    "SOS",
    "LIVE_EMERGENCY",
    "SET_EMERGENCY",
    # Fall variants
    "FALL",
    "FALL_DETECTED",
    "LIVE_FALL",
]


@emergency_bp.route("/", methods=["GET"])
@jwt_required()
def list_emergency_logs():
    err = require_admin()
    if err:
        return err

    limit  = request.args.get("limit",  100, type=int)
    offset = request.args.get("offset", 0,   type=int)

    logs = (
        DeviceLog.query
        .filter(DeviceLog.activity_type.in_(EMERGENCY_TYPES))
        .order_by(DeviceLog.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    result = []
    for log in logs:
        # ← fetch device manually since DeviceLog has no relationship defined
        device = Device.query.get(log.device_id)
        if not device:
            continue

        vip = device.vip
        guardians = []
        for link in device.guardian_links:
            g = link.guardian
            guardians.append({
                "guardian_id": g.guardian_id,
                "first_name":  g.first_name,
                "last_name":   g.last_name,
                "email":       g.email,
                "role":        link.role,
            })

        raw_type = (log.activity_type or "").upper().replace("-", "_").replace(" ", "_")
        if raw_type in ("FALL", "FALL_DETECTED", "LIVE_FALL"):
            emergency_type = "FALL"
        else:
            emergency_type = "EMERGENCY"

        result.append({
            "id":                    log.log_id,
            "device_serial_number":  device.device_serial_number,
            "vip": {
                "vip_id":     vip.vip_id,
                "first_name": vip.first_name,
                "last_name":  vip.last_name,
            } if vip else None,
            "guardians":      guardians,
            "log_message":    log.message,
            "emergency_type": emergency_type,
            "last_location":  _extract_location(log.metadata_json),
            "created_at":     log.created_at.isoformat() if log.created_at else None,
        })

    return jsonify(result), 200