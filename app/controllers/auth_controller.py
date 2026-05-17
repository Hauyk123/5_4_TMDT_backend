# File: app/controllers/auth_controller.py
import pymysql
import os
from werkzeug.security import generate_password_hash, check_password_hash
from config.settings import Config


def get_mysql_connection():
    """Tạo kết nối tới MySQL dựa trên biến môi trường"""
    try:
        return pymysql.connect(
            host=os.environ.get('MYSQL_HOST', 'localhost'),
            user=os.environ.get('MYSQL_USER', 'root'),
            password=os.environ.get('MYSQL_PASSWORD', ''),
            database=os.environ.get('MYSQL_DB', 'tmdt_giadung'),
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"❌ [MySQL] Lỗi kết nối Controller: {e}")
        return None


def verify_login(email_or_username, password):
    """Xử lý logic kiểm tra đăng nhập (Hỗ trợ cả Email hoặc Username)"""
    conn = get_mysql_connection()
    if not conn:
        return False, "Lỗi kết nối cơ sở dữ liệu."

    try:
        with conn.cursor() as cursor:
            # BỔ SUNG QUAN TRỌNG: Lấy thêm cột 'role' để bẻ lái điều hướng sau đăng nhập
            sql = """
                SELECT user_id, username, full_name, email, password_hash, role 
                FROM USERS 
                WHERE email = %s OR username = %s
            """
            cursor.execute(sql, (email_or_username, email_or_username))
            user = cursor.fetchone()

            # Đối chiếu mật khẩu người dùng nhập với mã hash trong DB
            if user and check_password_hash(user['password_hash'], password):
                return True, user
            else:
                return False, "Tài khoản hoặc mật khẩu không chính xác."
    finally:
        conn.close()


def register_user(user_data):
    """Xử lý logic đăng ký tài khoản mới đồng bộ với file Route"""
    conn = get_mysql_connection()
    if not conn:
        return False, "Lỗi kết nối cơ sở dữ liệu."

    # Bóc tách dữ liệu từ Dictionary truyền sang
    username = user_data.get('username')
    email = user_data.get('email')
    password = user_data.get('password')
    full_name = user_data.get('full_name')
    phone = user_data.get('phone')

    # Băm mật khẩu để bảo mật tuyệt đối
    hashed_pw = generate_password_hash(password)

    try:
        with conn.cursor() as cursor:
            # Kiểm tra xem Email hoặc Username đã bị người khác đăng ký chưa
            check_sql = "SELECT user_id FROM USERS WHERE email = %s OR username = %s"
            cursor.execute(check_sql, (email, username))
            if cursor.fetchone():
                return False, "Email hoặc Tên đăng nhập này đã được sử dụng."

            # Thêm mới user vào CSDL
            insert_sql = """
                INSERT INTO USERS (username, email, password_hash, full_name, phone) 
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (username, email, hashed_pw, full_name, phone))

        conn.commit()
        return True, "🎉 Đăng ký tài khoản thành công! Vui lòng đăng nhập."
    except Exception as e:
        return False, f"Lỗi hệ thống: {str(e)}"
    finally:
        conn.close()