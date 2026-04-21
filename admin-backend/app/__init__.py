from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import os
from dotenv import load_dotenv
from sqlalchemy import inspect, text

load_dotenv()

db  = SQLAlchemy()
jwt = JWTManager()


def _ensure_guardian_concern_process_columns(app: Flask):
    """Best-effort schema sync for concern process tracking fields."""
    try:
        inspector = inspect(db.engine)
        table_name = "guardian_concerns_tbl"
        schema_name = "smart_cane_db"

        if not inspector.has_table(table_name, schema=schema_name):
            return

        columns = {
            col.get("name")
            for col in inspector.get_columns(table_name, schema=schema_name)
        }

        statements = []
        if "process_stage" not in columns:
            statements.append(
                "ALTER TABLE smart_cane_db.guardian_concerns_tbl "
                "ADD COLUMN process_stage VARCHAR(50) NOT NULL DEFAULT 'new'"
            )
        if "resolution_remarks" not in columns:
            statements.append(
                "ALTER TABLE smart_cane_db.guardian_concerns_tbl "
                "ADD COLUMN resolution_remarks TEXT NULL"
            )
        if "process_updated_by_admin_id" not in columns:
            statements.append(
                "ALTER TABLE smart_cane_db.guardian_concerns_tbl "
                "ADD COLUMN process_updated_by_admin_id INT NULL"
            )
        if "process_updated_at" not in columns:
            statements.append(
                "ALTER TABLE smart_cane_db.guardian_concerns_tbl "
                "ADD COLUMN process_updated_at TIMESTAMP NULL"
            )

        with db.engine.begin() as conn:
            for ddl in statements:
                conn.execute(text(ddl))

        if statements:
            app.logger.info("Applied guardian concern process schema sync")
    except Exception:
        # Non-blocking to avoid breaking startup in restricted DB environments.
        app.logger.exception("Failed to sync guardian concern process schema")


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"]        = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"]                 = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"]       = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    app.config["MAX_CONTENT_LENGTH"]             = 2 * 1024 * 1024  # 2MB max upload

    db.init_app(app)
    jwt.init_app(app)
    frontend_origins = os.getenv("FRONTEND_URL")
    if frontend_origins:
        cors_origins = [origin.strip() for origin in frontend_origins.split(",") if origin.strip()]
    else:
        cors_origins = ["http://localhost:5174", "http://127.0.0.1:5174"]
    CORS(app, origins=cors_origins, supports_credentials=True)

    @app.route("/static/uploads/profiles/<filename>")
    def serve_profile_image(filename: str):
        root: str = app.root_path or ""
        folder = os.path.join(root, "..", "static", "uploads", "profiles")
        return send_from_directory(os.path.abspath(folder), filename)

    from app.routes.auth     import auth_bp
    from app.routes.admin    import admin_bp
    from app.routes.guardian import guardian_bp
    from app.routes.vip      import vip_bp
    from app.routes.device   import device_bp
    from app.routes.emergency import emergency_bp
    from app.routes.concerns import concerns_bp
    from app.routes.notifications import notifications_bp
    from app.routes.restore import restore_bp

    app.register_blueprint(concerns_bp)
    app.register_blueprint(auth_bp,     url_prefix="/api/auth")
    app.register_blueprint(admin_bp,    url_prefix="/api/admin")
    app.register_blueprint(guardian_bp, url_prefix="/api/guardians")
    app.register_blueprint(vip_bp,      url_prefix="/api/vips")
    app.register_blueprint(device_bp,   url_prefix="/api/devices")
    app.register_blueprint(emergency_bp, url_prefix="/api/emergency-logs")
    app.register_blueprint(notifications_bp)
    app.register_blueprint(restore_bp)

    with app.app_context():
        _ensure_guardian_concern_process_columns(app)
        #db.create_all()
        pass
    return app