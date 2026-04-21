from app import db
from datetime import datetime, timezone
import bcrypt
import json


class OTP(db.Model):
    __tablename__ = "otp_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    otp_code = db.Column(db.String(255), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.TIMESTAMP, nullable=True, default=None)
    purpose = db.Column(db.String(50), default="general")

    def __repr__(self):
        return f"<OTP {self.email}>"


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.TIMESTAMP, default=datetime.now(timezone.utc))

class Admin(db.Model):
    __tablename__ = "admin_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    admin_id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username          = db.Column(db.String(100), nullable=False, unique=True)
    email             = db.Column(db.String(255), nullable=False, unique=True)
    password          = db.Column(db.String(255), nullable=False)
    first_name        = db.Column(db.String(255), nullable=False)
    middle_name       = db.Column(db.String(255), nullable=True)
    last_name         = db.Column(db.String(255), nullable=False)
    contact_number    = db.Column(db.String(20),  nullable=True)
    province          = db.Column(db.String(100), nullable=True)
    city              = db.Column(db.String(100), nullable=True)
    barangay          = db.Column(db.String(100), nullable=True)
    street_address    = db.Column(db.Text,        nullable=True)
    role              = db.Column(
        db.Enum("super_admin", "admin", name="admin_role"),
        nullable=False,
        default="admin",
    )
    # 1 = first time logging in, 0 = already set their own password
    is_first_login    = db.Column(db.Boolean,     nullable=False, default=True)
    # URL of uploaded profile picture e.g. http://localhost:5000/static/uploads/profiles/xxx.jpg
    profile_image_url = db.Column(db.String(500), nullable=True,  default=None)
    created_at        = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at        = db.Column(
        db.TIMESTAMP,
        default=lambda:  datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def check_password(self, plain_password: str) -> bool:
       if self.password.startswith(("$2b$", "$2a$")):
           return bcrypt.checkpw(
               plain_password.encode("utf-8"),
               self.password.encode("utf-8"),
           )
       # fallback for any legacy plain-text rows (remove once all are migrated)
       return self.password == plain_password

    def __repr__(self):
        return f"<Admin {self.username}>"


class Notification(db.Model):
    __tablename__ = "notifications_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    notification_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    audience = db.Column(
        db.Enum(
            "all_admins",
            "super_admins",
            name="notification_audience",
            schema="smart_cane_db",
        ),
        nullable=False,
        default="all_admins",
        index=True,
    )

    type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=True)

    link_path = db.Column(db.String(255), nullable=True)  # frontend route e.g. /admins

    related_concern_id = db.Column(db.Integer, nullable=True, index=True)
    related_admin_id = db.Column(db.Integer, nullable=True, index=True)

    created_at = db.Column(
        db.TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    reads = db.relationship(
        "NotificationRead",
        back_populates="notification",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "notification_id": self.notification_id,
            "audience": self.audience,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "link_path": self.link_path,
            "related_concern_id": self.related_concern_id,
            "related_admin_id": self.related_admin_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class NotificationRead(db.Model):
    __tablename__ = "notification_reads_tbl"
    __table_args__ = (
        db.UniqueConstraint(
            "notification_id",
            "admin_id",
            name="uq_notification_read_notification_admin",
        ),
        {"schema": "smart_cane_db"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    notification_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.notifications_tbl.notification_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.admin_tbl.admin_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    read_at = db.Column(
        db.TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    notification = db.relationship("Notification", back_populates="reads")
    admin = db.relationship("Admin", lazy=True)


class AdminArchive(db.Model):
    # Deleted admin rows copied here before removal from admin_tbl.
    __tablename__ = "admin_archive_tbl"
    __table_args__ = {"schema": "smart_cane_db"}
 
    archive_id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
 
    admin_id          = db.Column(db.Integer,      nullable=False)   # original PK
    username          = db.Column(db.String(100),  nullable=False)
    email             = db.Column(db.String(255),  nullable=False)
    password          = db.Column(db.String(255),  nullable=False)   # keep hashed
    first_name        = db.Column(db.String(255),  nullable=False)
    middle_name       = db.Column(db.String(255),  nullable=True)
    last_name         = db.Column(db.String(255),  nullable=False)
    contact_number    = db.Column(db.String(20),   nullable=True)
    province          = db.Column(db.String(100),  nullable=True)
    city              = db.Column(db.String(100),  nullable=True)
    barangay          = db.Column(db.String(100),  nullable=True)
    street_address    = db.Column(db.Text,         nullable=True)
    role              = db.Column(db.String(50),   nullable=False)
    profile_image_url = db.Column(db.String(500),  nullable=True)
    original_created_at = db.Column(db.TIMESTAMP, nullable=True)
 
    archived_at       = db.Column(
        db.TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    archived_by       = db.Column(db.Integer, nullable=True)   # admin_id of deleter
    archived_reason_code = db.Column(db.String(50), nullable=True)
    archived_reason_text = db.Column(db.String(500), nullable=True)
 
    def __repr__(self):
        return f"<AdminArchive admin_id={self.admin_id} username={self.username}>"


class AdminAuditLog(db.Model):
    # Append-only audit trail for admin/super-admin sensitive actions.
    __tablename__ = "admin_audit_log_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    audit_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    actor_admin_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.admin_tbl.admin_id"),
        nullable=False,
        index=True,
    )
    target_admin_id = db.Column(db.Integer, nullable=True, index=True)
    target_concern_id = db.Column(db.Integer, nullable=True, index=True)
    action_type = db.Column(db.String(50), nullable=False, index=True)
    old_value_json = db.Column(db.Text, nullable=True)
    new_value_json = db.Column(db.Text, nullable=True)
    reason_code = db.Column(db.String(50), nullable=False)
    reason_text = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="success")
    failure_message = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    actor = db.relationship("Admin", lazy=True)

    def to_dict(self):
        actor_name = None
        if self.actor:
            actor_name = " ".join(
                p for p in [self.actor.first_name, self.actor.last_name] if p
            ).strip()

        parsed_old_value = {}
        if self.old_value_json:
            try:
                parsed_old_value = json.loads(self.old_value_json)
            except Exception:
                parsed_old_value = {}

        deleted_admin_name = (
            parsed_old_value.get("full_name")
            or parsed_old_value.get("deleted_admin_name")
            or parsed_old_value.get("username")
        )
        deleted_concern_message = (
            parsed_old_value.get("message")
            or parsed_old_value.get("deleted_concern_message")
        )
        deleted_device_serial = (
            parsed_old_value.get("deleted_device_serial")
            or parsed_old_value.get("device_serial_number")
        )

        return {
            "audit_id": self.audit_id,
            "actor_admin_id": self.actor_admin_id,
            "actor_name": actor_name,
            "target_admin_id": self.target_admin_id,
            "target_concern_id": self.target_concern_id,
            "action_type": self.action_type,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "status": self.status,
            "failure_message": self.failure_message,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "deleted_admin_name": deleted_admin_name,
            "deleted_concern_message": deleted_concern_message,
            "deleted_device_serial": deleted_device_serial,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<AdminAuditLog #{self.audit_id} {self.action_type} by {self.actor_admin_id}>"

class GuardianInvitation(db.Model):
    __tablename__ = "guardian_invitations"
    __table_args__ = {"schema": "smart_cane_db"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.device_tbl.device_id"),
        nullable=False,
    )

    invited_by_guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id"),
        nullable=False,
    )

    status = db.Column(
        db.Enum(
            "pending",
            "accepted",
            "expired",
            "revoked",
            name="invite_status",
            schema="smart_cane_db",
        ),
        default="pending",
        nullable=False,
    )

    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.TIMESTAMP)


class VIP(db.Model):
    __tablename__ = "vip_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    vip_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name = db.Column(db.String(255))
    middle_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255))
    vip_image_url = db.Column(db.String(500))
    province = db.Column(db.String(100))
    city = db.Column(db.String(100))
    barangay = db.Column(db.String(100))
    street_address = db.Column(db.Text)
    created_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    devices = db.relationship("Device", backref="vip", lazy=True)
    # locations = db.relationship("GPSLocation", backref="vip", lazy=True)
    reminders = db.relationship("NoteReminder", backref="vip", lazy=True)
    # alerts = db.relationship("EmergencyAlert", backref="vip", lazy=True)


class Guardian(db.Model):
    __tablename__ = "guardian_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    guardian_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(255))
    middle_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255))
    guardian_image_url = db.Column(db.String(500))
    email = db.Column(db.String(255), nullable=False, unique=True)
    contact_number = db.Column(db.String(20))
    province = db.Column(db.String(100))
    city = db.Column(db.String(100))
    barangay = db.Column(db.String(100))
    village = db.Column(db.String(100))
    street_address = db.Column(db.Text)
    role = db.Column(db.String(50), default="guardian")
    has_seen_tour = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    device_links = db.relationship("DeviceGuardian", backref="guardian", lazy=True)
    reminders = db.relationship("NoteReminder", backref="guardian", lazy=True)
    push_subscriptions = db.relationship(
        "PushSubscription",
        back_populates="guardian",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password):
        return bcrypt.checkpw(password.encode("utf-8"), self.password.encode("utf-8"))


class Device(db.Model):
    __tablename__ = "device_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    device_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    vip_id = db.Column(
        db.Integer, db.ForeignKey("smart_cane_db.vip_tbl.vip_id"), nullable=True
    )
    device_serial_number = db.Column(db.String(100), unique=True, nullable=False)
    is_paired = db.Column(db.Boolean, default=False)
    paired_at = db.Column(db.TIMESTAMP, nullable=True)
    last_active_at = db.Column(db.TIMESTAMP, nullable=True)
    created_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    guardian_links = db.relationship("DeviceGuardian", backref="device", lazy=True)


class DeviceGuardian(db.Model):
    __tablename__ = "device_guardian_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_id = db.Column(
        db.Integer, db.ForeignKey("smart_cane_db.device_tbl.device_id"), nullable=False
    )
    device_name = db.Column(db.String(255), nullable=True)
    relationship = db.Column(db.String(100), nullable=True)
    is_emergency_contact = db.Column(db.Boolean, default=False)
    role = db.Column(
        db.Enum(
            "primary",
            "secondary",
            "guardian",
            name="guardian_role",
            schema="smart_cane_db",
        ),
        default="guardian",
        nullable=False,
    )
    guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id"),
        nullable=False,
    )
    assigned_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("device_id", "guardian_id", name="_device_guardian_uc"),
        {"schema": "smart_cane_db"},
    )


# class GPSLocation(db.Model):
#     __tablename__ = "gps_location_tbl"
#     __table_args__ = {"schema": "smart_cane_db"}

#     location_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     vip_id = db.Column(
#         db.Integer, db.ForeignKey("smart_cane_db.vip_tbl.vip_id"), nullable=False
#     )
#     latitude = db.Column(db.Numeric(10, 8), nullable=False)
#     longitude = db.Column(db.Numeric(11, 8), nullable=False)
#     location = db.Column(db.Text, nullable=False)
#     timestamp = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))

#     alerts = db.relationship("EmergencyAlert", backref="location", lazy=True)


class DeviceLastLocation(db.Model):
    __tablename__ = "device_last_location_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.device_tbl.device_id"),
        primary_key=True,
    )
    lat = db.Column(db.Numeric(10, 7), nullable=True)
    lng = db.Column(db.Numeric(10, 7), nullable=True)
    sats = db.Column(db.Integer, nullable=True)
    fix_status = db.Column(db.SmallInteger, nullable=False, default=0)
    hdop = db.Column(db.Numeric(6, 2), nullable=True)
    gps_status = db.Column(db.Integer, nullable=False, default=0)
    recorded_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    device = db.relationship(
        "Device",
        backref=db.backref("last_location", uselist=False),
    )

    def __repr__(self):
        return f"<DeviceLastLocation {self.device_id}>"


class DeviceRoute(db.Model):
    __tablename__ = "device_route_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    route_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.device_tbl.device_id"),
        nullable=False,
        unique=True,
    )

    guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id"),
        nullable=True,
    )

    destination_label = db.Column(db.String(255), nullable=True)
    destination_lat = db.Column(db.Numeric(10, 7), nullable=False)
    destination_lng = db.Column(db.Numeric(10, 7), nullable=False)

    route_geojson = db.Column(db.JSON, nullable=True)
    provider_payload = db.Column(db.JSON, nullable=True)

    status = db.Column(
        db.Enum(
            "pending",
            "active",
            "completed",
            "cleared",
            "failed",
            name="route_status",
            schema="smart_cane_db",
        ),
        default="pending",
        nullable=False,
    )

    distance_meters = db.Column(db.Numeric(12, 2), nullable=True)
    duration_ms = db.Column(db.BigInteger, nullable=True)

    requested_at = db.Column(
        db.TIMESTAMP, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at = db.Column(db.TIMESTAMP, nullable=True)
    cleared_at = db.Column(db.TIMESTAMP, nullable=True)
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<DeviceRoute {self.device_id} - {self.status}>"


class NoteReminder(db.Model):
    __tablename__ = "note_reminder_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    note_reminder_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id"),
        nullable=False,
    )
    vip_id = db.Column(
        db.Integer, db.ForeignKey("smart_cane_db.vip_tbl.vip_id"), nullable=False
    )
    message = db.Column(db.Text, nullable=False)
    reminder_time = db.Column(db.Time, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# class EmergencyAlert(db.Model):
#     __tablename__ = "emergency_alert_tbl"
#     __table_args__ = {"schema": "smart_cane_db"}

#     alert_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     vip_id = db.Column(
#         db.Integer, db.ForeignKey("smart_cane_db.vip_tbl.vip_id"), nullable=False
#     )
#     location_id = db.Column(
#         db.Integer,
#         db.ForeignKey("smart_cane_db.gps_location_tbl.location_id"),
#         nullable=False,
#     )
#     triggered_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
#     acknowledged = db.Column(db.Boolean, default=False)


class DeviceConfig(db.Model):
    __tablename__ = "device_config_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    config_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.device_tbl.device_id"),
        nullable=False,
        unique=True,
    )

    config_json = db.Column(db.JSON, nullable=False)

    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AccountHistory(db.Model):
    __tablename__ = "account_history_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    history_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id"),
        nullable=False,
    )
    device_id = db.Column(  # NEW
        db.Integer,
        db.ForeignKey("smart_cane_db.device_tbl.device_id"),
        nullable=True,
    )
    action = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<AccountHistory {self.guardian_id} - {self.action}>"


class DeviceLog(db.Model):
    __tablename__ = "device_logs_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.device_tbl.device_id"),
        nullable=False,
        index=True,
    )

    guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id"),
        nullable=True,
        index=True,
    )

    activity_type = db.Column(db.String(50), nullable=False)

    status = db.Column(db.String(20), nullable=True)
    message = db.Column(db.Text, nullable=False)

    metadata_json = db.Column(db.JSON, nullable=True)

    created_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self):
        return f"<DeviceLog {self.device_id} - {self.activity_type}>"


class PushSubscription(db.Model):
    __tablename__ = "push_subscription_tbl"
    __table_args__ = {"schema": "smart_cane_db"}

    subscription_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    guardian_id = db.Column(
        db.Integer,
        db.ForeignKey("smart_cane_db.guardian_tbl.guardian_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    endpoint = db.Column(db.Text, nullable=False, unique=False)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    user_agent = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    guardian = db.relationship("Guardian", back_populates="push_subscriptions")

    def to_dict(self):
        return {
            "subscription_id": self.subscription_id,
            "guardian_id": self.guardian_id,
            "endpoint": self.endpoint,
            "p256dh": self.p256dh,
            "auth": self.auth,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<PushSubscription {self.guardian_id}>"

class GuardianConcern(db.Model):
    # Guardian contact form submissions (public submit; admins manage in panel).
    __tablename__ = "guardian_concerns_tbl"
    __table_args__ = {"schema": "smart_cane_db"}
 
    concern_id  = db.Column(db.Integer, primary_key=True, autoincrement=True)
 

    name        = db.Column(db.String(255), nullable=False)
    email       = db.Column(db.String(255), nullable=False, index=True)
    message     = db.Column(db.Text,        nullable=False)
 
    status      = db.Column(
        db.Enum("unread", "read", "resolved",
                name="concern_status",
                schema="smart_cane_db"),
        nullable=False,
        default="unread",
        index=True,
    )
    admin_reply         = db.Column(db.Text,      nullable=True, default=None)
    replied_by_admin_id = db.Column(db.Integer,   nullable=True, default=None)
    replied_at          = db.Column(db.TIMESTAMP, nullable=True, default=None)
    process_stage       = db.Column(db.String(50), nullable=False, default="new", index=True)
    resolution_remarks  = db.Column(db.Text, nullable=True, default=None)
    process_updated_by_admin_id = db.Column(db.Integer, nullable=True, default=None)
    process_updated_at  = db.Column(db.TIMESTAMP, nullable=True, default=None)
 
    created_at  = db.Column(
        db.TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at  = db.Column(
        db.TIMESTAMP,
        nullable=False,
        default=lambda:  datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.TIMESTAMP, nullable=True, default=None)
    deleted_by_admin_id = db.Column(db.Integer, nullable=True, default=None)
    deleted_reason_code = db.Column(db.String(50), nullable=True)
    deleted_reason_text = db.Column(db.String(500), nullable=True)
 
    def to_dict(self):
        return {
            "concern_id":          self.concern_id,
            "name":                self.name,
            "email":               self.email,
            "message":             self.message,
            "status":              self.status,
            "admin_reply":         self.admin_reply,
            "replied_by_admin_id": self.replied_by_admin_id,
            "replied_at":          self.replied_at.isoformat() if self.replied_at else None,
            "process_stage":       self.process_stage,
            "resolution_remarks":  self.resolution_remarks,
            "process_updated_by_admin_id": self.process_updated_by_admin_id,
            "process_updated_at":  self.process_updated_at.isoformat() if self.process_updated_at else None,
            "created_at":          self.created_at.isoformat() if self.created_at else None,
            "updated_at":          self.updated_at.isoformat() if self.updated_at else None,
            "is_deleted":          self.is_deleted,
            "deleted_at":          self.deleted_at.isoformat() if self.deleted_at else None,
            "deleted_by_admin_id": self.deleted_by_admin_id,
            "deleted_reason_code": self.deleted_reason_code,
            "deleted_reason_text": self.deleted_reason_text,
        }
 
    def __repr__(self):
        return f"<GuardianConcern {self.concern_id} [{self.status}] from {self.email}>"