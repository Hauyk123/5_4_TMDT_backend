import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import pickle
import os
import sys
import re
import gc  # Garbage Collector để dọn RAM thủ công

# Thêm đường dẫn thư mục gốc
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db_connection import Database


class AdvancedCleaner:
    def __init__(self):
        self.db = Database()
        self.col_products = self.db.get_collection(config.COL_PRODUCTS)

        print("⏳ Đang tải model BERT (all-MiniLM-L6-v2)...")
        # Dùng device='cpu' để đảm bảo chạy được trên mọi máy
        self.bert_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

        self.save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models', 'saved_models')
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

    def clean_text(self, text):
        if not isinstance(text, str): return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text.strip()

    def generate_embeddings_optimized(self):
        """
        Phiên bản tối ưu cho RAM 8GB:
        - Đọc dữ liệu theo từng Batch (Lô) từ MongoDB
        - Xử lý xong lưu ngay, không giữ trong RAM
        """
        print("🚀 BẮT ĐẦU TẠO VECTOR CHO TOÀN BỘ SẢN PHẨM...")

        # 1. Cấu hình Batch
        BATCH_SIZE = 2000  # Mỗi lần chỉ xử lý 2000 sản phẩm (Rất an toàn cho RAM 8GB)

        # Đếm tổng số lượng để hiện thanh tiến trình
        total_docs = self.col_products.count_documents({})
        print(f"📦 Tổng số sản phẩm cần xử lý: {total_docs}")

        all_embeddings = []
        all_ids = []

        # 2. Xử lý từng Batch bằng con trỏ MongoDB (Cursor)
        cursor = self.col_products.find({}, {"title": 1, "_id": 1}).batch_size(BATCH_SIZE)

        current_batch_titles = []
        current_batch_ids = []
        processed_count = 0

        for doc in cursor:
            # Làm sạch title
            title = doc.get('title', '')
            clean_t = self.clean_text(title)

            # Nếu title rỗng thì đặt placeholder để giữ đúng vị trí index
            if not clean_t: clean_t = "unknown product"

            current_batch_titles.append(clean_t)
            current_batch_ids.append(doc['_id'])

            # Khi đủ 1 Batch thì đưa vào BERT encode
            if len(current_batch_titles) >= BATCH_SIZE:
                # Encode
                embeddings = self.bert_model.encode(current_batch_titles, show_progress_bar=False)

                # Lưu vào list tổng (chỉ lưu vector số, tốn rất ít RAM)
                all_embeddings.extend(embeddings)
                all_ids.extend(current_batch_ids)

                processed_count += len(current_batch_titles)
                print(
                    f"   -> Đã xử lý: {processed_count}/{total_docs} ({round(processed_count / total_docs * 100, 1)}%)",
                    end='\r')

                # Reset batch và dọn dẹp RAM
                current_batch_titles = []
                current_batch_ids = []
                gc.collect()  # Ép máy giải phóng RAM ngay lập tức

        # Xử lý nốt phần dư cuối cùng (nếu có)
        if current_batch_titles:
            embeddings = self.bert_model.encode(current_batch_titles, show_progress_bar=False)
            all_embeddings.extend(embeddings)
            all_ids.extend(current_batch_ids)
            processed_count += len(current_batch_titles)
            print(f"   -> Đã xử lý: {processed_count}/{total_docs} (100%)")

        print("\n💾 Đang lưu xuống ổ cứng...")

        # Convert sang numpy array để nén nhỏ hơn
        final_embeddings = np.array(all_embeddings)

        with open(os.path.join(self.save_dir, 'bert_embeddings.pkl'), 'wb') as f:
            pickle.dump(final_embeddings, f)

        with open(os.path.join(self.save_dir, 'product_ids.pkl'), 'wb') as f:
            pickle.dump(all_ids, f)

        print(f"✅ HOÀN TẤT! Đã tạo vector cho {len(all_ids)} sản phẩm.")


if __name__ == "__main__":
    cleaner = AdvancedCleaner()
    # Chạy hàm tối ưu mới
    cleaner.generate_embeddings_optimized()