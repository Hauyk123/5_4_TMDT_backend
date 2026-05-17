import os
import sys
import pandas as pd
from dotenv import load_dotenv

# 1. Nạp biến môi trường từ .env
load_dotenv()

from config.settings import Config
from config.db_connection import get_mysql_connection


def seed_directly_from_gz():
    # Lấy đường dẫn file từ cấu hình settings.py của bạn
    meta_path = os.path.join(Config.DATA_DIR, Config.FILE_META)

    if not os.path.exists(meta_path):
        print(f"❌ Không tìm thấy file nén tại: {meta_path}")
        print("Vui lòng kiểm tra lại thư mục 'data' xem đã có file meta_Appliances.jsonl.gz chưa.")
        return

    try:
        mysql_conn = get_mysql_connection()
        cursor = mysql_conn.cursor()
    except Exception as e:
        print(f"❌ Lỗi kết nối MySQL Connection Pool: {e}")
        return

    print(f"🚀 Bắt đầu trích xuất trực tiếp dữ liệu từ: {Config.FILE_META}")

    chunk_size = 5000  # Đọc 5000 dòng một lần để tối ưu bộ nhớ
    count = 0
    cat_mapping = {}

    # Sử dụng bộ đọc chunk của pandas để xử lý file json nén dòng
    with pd.read_json(meta_path, lines=True, compression='gzip', chunksize=chunk_size) as reader:
        for chunk in reader:
            for _, row in chunk.iterrows():

                # 1. Trích xuất Khóa chính (parent_asin) giống hệt logic bên Mongo
                product_id = row.get('parent_asin')
                if not product_id or pd.isna(product_id):
                    continue
                product_id = str(product_id)

                # 2. Trích xuất Tên sản phẩm
                name = str(row.get('title', 'Unknown Product'))[:255]

                # 3. Trích xuất và ép kiểu Giá tiền
                raw_price = row.get('price', 0)
                try:
                    price = float(raw_price) if not pd.isna(raw_price) else 0.0
                except (ValueError, TypeError):
                    price = 0.0

                # 4. Trích xuất Danh mục chính
                cat_name = row.get('main_category')
                if not cat_name or pd.isna(cat_name) or str(cat_name).strip() == '':
                    cat_name = 'Khác'
                cat_name = str(cat_name)[:255]

                # 5. Trích xuất Ảnh sản phẩm (Lấy ảnh chất lượng cao đầu tiên nếu có)
                image_url = ''
                images = row.get('images')
                if isinstance(images, list) and len(images) > 0:
                    if isinstance(images[0], dict):
                        image_url = images[0].get('hi_res') or images[0].get('large') or images[0].get('thumb') or ''
                    elif isinstance(images[0], str):
                        image_url = images[0]
                image_url = str(image_url)[:500]

                # --- TIẾN HÀNH BƠM VÀO MYSQL ---
                # Xử lý bảng CATEGORY để đồng bộ khóa ngoại trước
                if cat_name not in cat_mapping:
                    cursor.execute("INSERT IGNORE INTO CATEGORY (name) VALUES (%s)", (cat_name,))
                    mysql_conn.commit()

                    cursor.execute("SELECT category_id FROM CATEGORY WHERE name = %s", (cat_name,))
                    res = cursor.fetchone()
                    if res:
                        cat_mapping[cat_name] = res[0]

                category_id = cat_mapping.get(cat_name)

                # Chèn dữ liệu sạch vào bảng PRODUCT trong MySQL Workbench
                insert_query = """
                    INSERT IGNORE INTO PRODUCT (product_id, name, price, category_id, image_url)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (product_id, name, price, category_id, image_url))
                count += 1

            # Commit dữ liệu sau khi chạy xong một lô (chunk) để giải phóng hàng đợi DB
            mysql_conn.commit()
            print(f"-> Đã nạp thành công {count} sản phẩm vào MySQL...", end='\r')

    cursor.close()
    mysql_conn.close()
    print(f"\n🎉 Hoàn thành! Toàn bộ {count} sản phẩm đã được đổ thẳng từ file nén vào MySQL Workbench.")


if __name__ == "__main__":
    seed_directly_from_gz()