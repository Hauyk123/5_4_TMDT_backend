from flask import Flask
from config.settings import Config


def create_app():
    # Khởi tạo Flask, chỉ định đúng thư mục template và static
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)

    # Bắt buộc phải có secret_key để dùng được Session (phục vụ Giỏ hàng và Đăng nhập)
    app.secret_key = Config.SECRET_KEY or 'dev_secret_key_nhom04'

    # Khởi tạo và test Database theo kiến trúc Polyglot mới (MySQL + MongoDB)
    try:
        from config.db_connection import get_mysql_connection, get_mongo_db
        get_mongo_db()  # Test MongoDB
        conn = get_mysql_connection()  # Test MySQL
        if conn:
            conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo Database ban đầu: {e}")

    # Đăng ký các Blueprint (Routes) ở đây
    from app.routes.main_routes import main_bp
    app.register_blueprint(main_bp)
    # Đăng ký Blueprint Admin
    try:
        from app.routes.admin_routes import admin_bp
        app.register_blueprint(admin_bp)
    except ImportError as e:
        print(f"⚠️ Module Admin đang bảo trì hoặc có lỗi: {e}")
    # Bọc try-except để nếu file auth hoặc cart chưa viết xong code thì web vẫn chạy được trang chủ
    try:
        from app.routes.auth_routes import auth_bp
        app.register_blueprint(auth_bp)
    except ImportError as e:
        print(f"⚠️ Module Auth đang bảo trì hoặc có lỗi: {e}")

    try:
        from app.routes.cart_routes import cart_bp
        app.register_blueprint(cart_bp)
    except ImportError as e:
        print(f"⚠️ Module Cart đang bảo trì hoặc có lỗi: {e}")

    # Đăng ký Blueprint Order vào đúng vị trí bên trong hàm create_app
    try:
        from app.routes.order_routes import order_bp
        app.register_blueprint(order_bp)
    except ImportError as e:
        print(f"⚠️ Module Order đang bảo trì hoặc có lỗi: {e}")

    return app