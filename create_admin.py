from werkzeug.security import generate_password_hash
# Đảm bảo bạn đang import đúng hàm kết nối DB của bạn
from config.db_connection import get_mysql_connection


def auto_create_admin():
    print("⏳ Đang tự động khởi tạo tài khoản Admin...")

    # 1. Dữ liệu cứng bạn đã cung cấp
    username = "admin"
    full_name = "ADMIN"
    email = "admin@tmdt.com"
    phone = "0966116241"
    password = "123"

    # 2. Băm mật khẩu
    hashed_password = generate_password_hash(password)

    # 3. Kết nối và đẩy xuống DB
    conn = get_mysql_connection()
    if not conn:
        print("❌ Lỗi: Không thể kết nối tới Cơ sở dữ liệu MySQL.")
        return

    cursor = conn.cursor(dictionary=True)
    try:
        # Kiểm tra xem đã tạo trước đó chưa để tránh lỗi trùng lặp
        cursor.execute("SELECT user_id FROM USERS WHERE username = %s", (username,))
        if cursor.fetchone():
            print(f"⚠️ Tài khoản '{username}' đã tồn tại trong hệ thống rồi!")
            return

        # Thực thi lệnh INSERT
        sql = """
            INSERT INTO USERS (username, password_hash, full_name, email, phone, role) 
            VALUES (%s, %s, %s, %s, %s, 'ADMIN')
        """
        cursor.execute(sql, (username, hashed_password, full_name, email, phone))
        conn.commit()

        print("=========================================")
        print("🎉 THÀNH CÔNG! Đã tạo tài khoản Quản trị viên.")
        print(f"   - Tên đăng nhập : {username}")
        print(f"   - Mật khẩu      : {password}")
        print("👉 Hãy vào http://localhost:5000/admin/dashboard để đăng nhập!")
        print("=========================================")

    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi hệ thống khi ghi dữ liệu: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    auto_create_admin()