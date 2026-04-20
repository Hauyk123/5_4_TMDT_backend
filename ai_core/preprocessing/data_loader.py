import pandas as pd
import os
import sys

# Hack để import được module từ thư mục cha
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.db_connection import Database


def process_and_import():
    db = Database()
    col_reviews = db.get_collection(config.COL_REVIEWS)
    col_products = db.get_collection(config.COL_PRODUCTS)

    print("🚀 BẮT ĐẦU QUÁ TRÌNH ETL (Extract - Transform - Load)...")

    # --- 1. XỬ LÝ METADATA (SẢN PHẨM) ---
    meta_path = os.path.join(config.DATA_DIR, config.FILE_META)
    if os.path.exists(meta_path):
        print(f"\n📦 Đang xử lý file Meta: {config.FILE_META}")

        # Đọc theo chunk để tiết kiệm RAM
        chunk_size = 10000
        count = 0

        # Xóa dữ liệu cũ
        col_products.delete_many({})

        # Các cột cần giữ lại (Feature selection)
        keep_cols = ['parent_asin', 'title', 'average_rating', 'rating_number', 'features', 'description', 'price',
                     'images', 'main_category', 'store']

        with pd.read_json(meta_path, lines=True, compression='gzip', chunksize=chunk_size) as reader:
            for chunk in reader:
                # == BƯỚC 2: DATA CLEANING (LÀM SẠCH) ==

                # 1. Chọn lọc features
                # Dataset 2023 dùng 'parent_asin' làm ID chính cho nhóm sản phẩm
                valid_cols = [c for c in keep_cols if c in chunk.columns]
                df_chunk = chunk[valid_cols].copy()

                # 2. Xử lý Missing Values
                # Nếu không có title, điền "Unknown Product"
                df_chunk['title'] = df_chunk['title'].fillna("Unknown Product")
                # Nếu giá null, điền 0
                if 'price' in df_chunk.columns:
                    df_chunk['price'] = df_chunk['price'].fillna(0)

                # 3. Loại bỏ Duplicates (trùng parent_asin)
                df_chunk.drop_duplicates(subset=['parent_asin'], inplace=True)

                # Đổi tên parent_asin thành _id để Mongo dùng làm khóa chính
                df_chunk.rename(columns={'parent_asin': '_id'}, inplace=True)

                # Insert vào Mongo
                records = df_chunk.to_dict('records')
                if records:
                    try:
                        col_products.insert_many(records, ordered=False)
                        count += len(records)
                        print(f"   -> Đã nạp {count} sản phẩm...", end='\r')
                    except Exception as e:
                        pass  # Bỏ qua lỗi trùng key nếu có

        print(f"\n✅ Hoàn tất Metadata: {count} sản phẩm.")
        # Tạo index cho tìm kiếm nhanh
        col_products.create_index([("title", "text")])

    # --- 2. XỬ LÝ REVIEWS (ĐÁNH GIÁ) ---
    review_path = os.path.join(config.DATA_DIR, config.FILE_REVIEWS)
    if os.path.exists(review_path):
        print(f"\n⭐ Đang xử lý file Reviews: {config.FILE_REVIEWS}")

        col_reviews.delete_many({})
        count = 0

        # Các cột cần thiết
        # Dataset 2023: rating, title, text, images, asin, parent_asin, user_id, timestamp, verified_purchase, helpful_vote

        with pd.read_json(review_path, lines=True, compression='gzip', chunksize=10000) as reader:
            for chunk in reader:
                # == DATA CLEANING ==

                # 1. Loại bỏ các dòng thiếu rating hoặc user_id
                chunk.dropna(subset=['rating', 'user_id', 'parent_asin'], inplace=True)

                # 2. Loại bỏ duplicates (một user đánh giá 1 sp nhiều lần -> giữ lần mới nhất)
                # (Ở đây làm đơn giản là drop duplicate thuần túy để code chạy nhanh)
                chunk.drop_duplicates(subset=['user_id', 'parent_asin', 'timestamp'], inplace=True)

                # Chuẩn hóa: Đổi tên parent_asin -> product_id cho dễ hiểu
                chunk.rename(columns={'parent_asin': 'product_id'}, inplace=True)

                records = chunk.to_dict('records')
                if records:
                    col_reviews.insert_many(records)
                    count += len(records)
                    print(f"   -> Đã nạp {count} đánh giá...", end='\r')

        print(f"\n✅ Hoàn tất Reviews: {count} đánh giá.")

        # Tạo Index
        print("⚡ Đang tạo Index (có thể mất vài giây)...")
        col_reviews.create_index("user_id")
        col_reviews.create_index("product_id")
        col_reviews.create_index("rating")
        print("✅ Xong Index.")


if __name__ == "__main__":
    process_and_import()