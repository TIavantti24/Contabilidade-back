import pymysql
pymysql.install_as_MySQLdb()

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "mysql://root:root@localhost:3306/stratws?charset=utf8mb4"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_recycle": 280,
            "pool_pre_ping": True,
        },
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", "jwt-secret"),
        JWT_ACCESS_TOKEN_EXPIRES=28800,
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    )

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    from app.api.auth import auth_bp
    from app.api.dashboard import dashboard_bp
    from app.api.scorecard import scorecard_bp
    from app.api.custo_fixo import custo_fixo_bp
    from app.api.receita import receita_bp
    from app.api.dre import dre_bp
    from app.api.admin import admin_bp

    app.register_blueprint(auth_bp,        url_prefix="/api/auth")
    app.register_blueprint(dashboard_bp,   url_prefix="/api/dashboard")
    app.register_blueprint(scorecard_bp,   url_prefix="/api/scorecard")
    app.register_blueprint(custo_fixo_bp,  url_prefix="/api/custo-fixo")
    app.register_blueprint(receita_bp,     url_prefix="/api/receita")
    app.register_blueprint(dre_bp,          url_prefix="/api/dre")
    app.register_blueprint(admin_bp,       url_prefix="/api/admin")

    return app