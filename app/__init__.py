import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    db_url = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Render/Postgres can close idle SSL connections. These options force
    # SQLAlchemy to test/recycle connections instead of reusing dead ones.
    if db_url.startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            "pool_timeout": 30,
            "pool_size": 5,
            "max_overflow": 2,
        }
    upload_folder = os.getenv("UPLOAD_FOLDER")
    if upload_folder:
        upload_folder = os.path.abspath(upload_folder)
    else:
        upload_folder = os.path.join(app.root_path, "static", "uploads")
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["BASE_URL"] = os.getenv("BASE_URL", "http://localhost:5000")

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.models import User

    # Auto-create missing tables for small Render deployments. This keeps new
    # helper tables, such as QR login tokens, from breaking existing databases.
    # Proper Flask migrations can still be added later.
    if os.getenv("AUTO_CREATE_TABLES", "1") == "1":
        with app.app_context():
            db.create_all()

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))


    @app.teardown_request
    def shutdown_session(exception=None):
        if exception is not None:
            db.session.rollback()
        db.session.remove()

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.applications import applications_bp
    from app.routes.signing import signing_bp
    from app.routes.policies import policies_bp
    from app.routes.recovery import recovery_bp
    from app.routes.qa import qa_bp
    from app.routes.documents import documents_bp
    from app.routes.advanced import advanced_bp
    from app.routes.security_center import security_center_bp
    from app.routes.settings import settings_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(signing_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(qa_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(advanced_bp)
    app.register_blueprint(security_center_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(reports_bp)

    return app
