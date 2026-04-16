from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models import Guardian

guardian_bp = Blueprint("guardian", __name__)


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


def _serialize(g):
    """Full serialisation: guardian + linked devices + VIPs via those devices."""

    devices = []
    vips    = []
    vip_ids_seen = set()

    for link in g.device_links:
        d = link.device
        devices.append({
            "device_id":            d.device_id,
            "device_serial_number": d.device_serial_number,
            "is_paired":            d.is_paired,
            "role":                 link.role,
        })
        if d.vip and d.vip.vip_id not in vip_ids_seen:
            vip_ids_seen.add(d.vip.vip_id)
            vips.append({
                "vip_id":     d.vip.vip_id,
                "first_name": d.vip.first_name,
                "last_name":  d.vip.last_name,
            })

    return {
        "guardian_id":        g.guardian_id,
        "username":           g.username,
        "first_name":         g.first_name,
        "middle_name":        g.middle_name,
        "last_name":          g.last_name,
        "email":              g.email,
        "contact_number":     g.contact_number,
        "province":           g.province,
        "city":               g.city,
        "barangay":           g.barangay,
        "village":            g.village,
        "street_address":     g.street_address,
        "role":               g.role,
        "guardian_image_url": g.guardian_image_url,
        "has_seen_tour":      g.has_seen_tour,
        "created_at":         g.created_at.isoformat() if g.created_at else None,
        "updated_at":         g.updated_at.isoformat() if g.updated_at else None,
        # enriched
        "devices":            devices,
        "vips":               vips,
    }


#  GUARDIAN MANAGEMENT

@guardian_bp.route("/", methods=["GET"])
@jwt_required()
def list_guardians():
    """List all guardians with their linked devices and VIPs. Admin & super_admin."""
    err = require_admin()
    if err:
        return err
    guardians = Guardian.query.order_by(Guardian.created_at.desc()).all()
    return jsonify([_serialize(g) for g in guardians]), 200


@guardian_bp.route("/<int:guardian_id>", methods=["GET"])
@jwt_required()
def get_guardian(guardian_id):
    err = require_admin()
    if err:
        return err
    g = Guardian.query.get_or_404(guardian_id)
    return jsonify(_serialize(g)), 200


@guardian_bp.route("/<int:guardian_id>", methods=["DELETE"])
@jwt_required()
def delete_guardian(guardian_id):
    err = require_super_admin()
    if err:
        return err
    g = Guardian.query.get_or_404(guardian_id)
    db.session.delete(g)
    db.session.commit()
    return jsonify({"message": "Guardian deleted successfully."}), 200