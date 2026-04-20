# File: app/controllers/auth_controller.py
import pymysql
import os
from werkzeug.security import generate_password_hash, check_password_hash

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

def verify_login(email, password):
    """Xử lý logic kiểm tra đăng nhập"""
    conn = get_mysql_connection()
    if not conn:
        return False, "Lỗi kết nối cơ sở dữ liệu."

    try:
        with conn.cursor() as cursor:
            # Đã bổ sung thêm cột 'role' vào truy vấn để phục vụ phân quyền
            sql = "SELECT id, full_name, email, password_hash, role FROM users WHERE email = %s"
            cursor.execute(sql, (email,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password_hash'], password):
                return True, user
            else:
                return False, "Email hoặc mật khẩu không chính xác."
    finally:
        if conn:
            conn.close()

def register_user(full_name, email, password):
    """Xử lý logic đăng ký tài khoản mới"""
    conn = get_mysql_connection()
    if not conn: return False, "Lỗi cơ sở dữ liệu."

    hashed_pw = generate_password_hash(password)
    try:
        with conn.cursor() as cursor:
            # Kiểm tra email tồn tại chưa
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return False, "Email này đã được sử dụng."

            # Thêm mới vào CSDL
            sql = "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)"
            cursor.execute(sql, (full_name, email, hashed_pw))
        conn.commit()
        return True, "Đăng ký thành công!"
    except Exception as e:
        return False, f"Lỗi hệ thống: {str(e)}"
    finally:
        if conn:
            conn.close()