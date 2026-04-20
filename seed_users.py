# File: seed_orders.py
import os
import pymysql
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Nhập module kết nối MongoDB của chính bạn!
from config.db_connection import Database

# Đọc cấu hình từ file .env
load_dotenv('.env')


def sync_products_and_seed_orders():
    # ==========================================
    # BƯỚC 1: LẤY SẢN PHẨM TỪ MONGODB
    # ==========================================
    print("🔄 Đang kết nối tới MongoDB để tải sản phẩm...")
    try:
        mongo_db = Database()
        col_products = mongo_db.get_collection("products")

        # Tìm 20 sản phẩm bất kỳ có chứa giá và tên
        mongo_products = list(col_products.find(
            {"price": {"$exists": True, "$ne": ""}, "title": {"$exists": True}}
        ).limit(20))

        if not mongo_products:
            print("❌ Không tìm thấy sản phẩm nào trong MongoDB! Hãy kiểm tra lại database 'amazon_recommender'.")
            return
        print(f"✅ Đã tải về {len(mongo_products)} sản phẩm từ MongoDB.")
    except Exception as e:
        print(f"❌ Lỗi kết nối MongoDB: {e}")
        return

    # ==========================================
    # BƯỚC 2: KẾT NỐI MYSQL VÀ ĐỒNG BỘ
    # ==========================================
    print("🔄 Đang kết nối tới MySQL...")
    conn = pymysql.connect(
        host=os.environ.get('MYSQL_HOST', 'localhost'),
        user=os.environ.get('MYSQL_USER', 'root'),
        password=os.environ.get('MYSQL_PASSWORD', ''),
        database=os.environ.get('MYSQL_DB', 'tmdt_giadung'),
        cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with conn.cursor() as cursor:
            print("📥 Đang đồng bộ danh mục sản phẩm từ Mongo sang MySQL...")

            for mp in mongo_products:
                # Cắt ngắn tên nếu vượt quá 255 ký tự (chuẩn MySQL)
                title = mp.get('title', 'Sản phẩm Amazon')[:250]

                # Chuyển đổi giá tiền từ USD sang VNĐ (Giả sử 1 USD = 25,000 VNĐ)
                raw_price = mp.get('price', 0)
                try:
                    if isinstance(raw_price, str):
                        clean_price = float(raw_price.replace('$', '').replace(',', '').strip())
                        price_vnd = clean_price * 25000
                    else:
                        price_vnd = float(raw_price) * 25000
                except:
                    price_vnd = 500000  # Giá mặc định nếu dữ liệu Mongo bị lỗi text

                # Chèn vào MySQL (Kiểm tra xem tên này đã được chèn chưa để tránh lặp)
                cursor.execute("SELECT id FROM products WHERE name = %s", (title,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO products (name, price, status) VALUES (%s, %s, 'active')",
                        (title, price_vnd)
                    )

            print("✅ Đã đồng bộ sản phẩm vào MySQL thành công!")

            # ==========================================
            # BƯỚC 3: TẠO ĐƠN HÀNG ẢO (DÙNG SẢN PHẨM VỪA ĐỒNG BỘ)
            # ==========================================
            cursor.execute("SELECT id FROM users WHERE role = 'customer'")
            users = cursor.fetchall()
            if not users:
                print("❌ Không tìm thấy Khách hàng trong MySQL! Vui lòng chạy seed_users.py trước.")
                return

            cursor.execute("SELECT id, price FROM products")
            mysql_products = cursor.fetchall()

            addresses = [
                "Học viện PTIT, Km10 Nguyễn Trãi, Hà Đông",
                "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội",
                "123 Nguyễn Văn Cừ, Quận 5, TP.HCM",
                "Ký túc xá Mỹ Đình, Nam Từ Liêm, Hà Nội"
            ]
            statuses = ['pending', 'confirmed', 'shipping', 'delivered', 'cancelled']

            print("⏳ Đang tạo 15 đơn hàng ảo để vẽ biểu đồ Dashboard...")
            for i in range(15):
                user_id = random.choice(users)['id']
                status = random.choice(statuses)
                address = random.choice(addresses)

                # Random ngày đặt trong 7 ngày qua
                days_ago = random.randint(0, 6)
                created_at = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23))

                # Lưu vào bảng orders
                sql_order = "INSERT INTO orders (user_id, shipping_address, total_amount, status, created_at) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql_order, (user_id, address, 0, status, created_at))
                order_id = cursor.lastrowid

                # Nhặt 1-3 sản phẩm bất kỳ bỏ vào đơn hàng
                total_amount = 0
                num_items = random.randint(1, 3)
                selected_products = random.sample(mysql_products, min(num_items, len(mysql_products)))

                for prod in selected_products:
                    qty = random.randint(1, 2)
                    total_amount += qty * prod['price']

                    sql_item = "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql_item, (order_id, prod['id'], qty, prod['price']))

                # Cập nhật lại tổng tiền đơn hàng
                cursor.execute("UPDATE orders SET total_amount = %s WHERE id = %s", (total_amount, order_id))

        conn.commit()
        print("🎉 XONG TUYỆT ĐỐI! Đã đồng bộ Mongo -> MySQL và tạo xong Đơn hàng ảo.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Có lỗi xảy ra trong quá trình xử lý MySQL: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    sync_products_and_seed_orders()