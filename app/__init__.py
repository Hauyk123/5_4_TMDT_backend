# File: app/__init__.py
from flask import Flask
from config.settings import Config

def create_app():
    # Khởi tạo Flask, chỉ định đúng thư mục template và static
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)

    # Khởi tạo Database (Gọi 1 lần để test kết nối)
    from config.db_connection import Database
    db = Database()

    # Đăng ký các Blueprint (Routes) ở đây
    from app.routes.main_routes import main_bp
    from app.routes.cart_routes import cart_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.order_routes import order_bp
    from app.routes.auth_routes import auth_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(auth_bp)

    app.register_blueprint(main_bp)
    app.register_blueprint(cart_bp)

    return app