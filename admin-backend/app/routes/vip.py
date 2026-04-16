from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models import VIP

vip_bp = Blueprint("vip", __name__)


#  Helpers
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


def _serialize(v):
    """Full serialisation: VIP + linked devices + guardians via those devices."""

    devices   = []
    guardians = []
    guardian_ids_seen = set()

    for d in v.devices:
        devices.append({
            "device_id":            d.device_id,
            "device_serial_number": d.device_serial_number,
            "is_paired":            d.is_paired,
        })
        for link in d.guardian_links:
            g = link.guardian
            if g.guardian_id not in guardian_ids_seen:
                guardian_ids_seen.add(g.guardian_id)
                guardians.append({
                    "guardian_id": g.guardian_id,
                    "first_name":  g.first_name,
                    "last_name":   g.last_name,
                    "email":       g.email,
                    "role":        link.role,
                })

    return {
        "vip_id":         v.vip_id,
        "first_name":     v.first_name,
        "middle_name":    v.middle_name,
        "last_name":      v.last_name,
        "vip_image_url":  v.vip_image_url,
        "province":       v.province,
        "city":           v.city,
        "barangay":       v.barangay,
        "street_address": v.street_address,
        "created_at":     v.created_at.isoformat() if v.created_at else None,
        "updated_at":     v.updated_at.isoformat() if v.updated_at else None,
        # enriched
        "devices":        devices,
        "guardians":      guardians,
    }


#  VIP MANAGEMENT

@vip_bp.route("/", methods=["GET"])
@jwt_required()
def list_vips():
    """List all VIPs with devices and guardians. Admin & super_admin."""
    err = require_admin()
    if err:
        return err
    vips = VIP.query.order_by(VIP.created_at.desc()).all()
    return jsonify([_serialize(v) for v in vips]), 200


@vip_bp.route("/<int:vip_id>", methods=["GET"])
@jwt_required()
def get_vip(vip_id):
    err = require_admin()
    if err:
        return err
    v = VIP.query.get_or_404(vip_id)
    return jsonify(_serialize(v)), 200


@vip_bp.route("/<int:vip_id>", methods=["DELETE"])
@jwt_required()
def delete_vip(vip_id):
    err = require_super_admin()
    if err:
        return err
    v = VIP.query.get_or_404(vip_id)
    db.session.delete(v)
    db.session.commit()
    return jsonify({"message": "VIP deleted successfully."}), 200