import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
import pickle
import os
import sys

# Hack path để import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db_connection import Database

# Import thư viện Surprise (Giờ chắc chắn sẽ import được sau khi bạn cài xong)
try:
    from surprise import Reader, Dataset, SVD
    from surprise.model_selection import train_test_split
    from surprise import accuracy

    print("✅ Đã nạp thành công thư viện Scikit-Surprise!")
except ImportError:
    print("❌ Vẫn chưa tìm thấy 'scikit-surprise'. Hãy kiểm tra lại việc cài đặt.")
    sys.exit(1)


class HybridRecommender:
    def __init__(self):
        self.db = Database()
        self.svd_model = None
        self.tfidf_matrix = None
        self.indices = None
        self.products_df = None

        # Đường dẫn lưu model đã train (để web app dùng lại)
        self.model_path = os.path.join(os.path.dirname(__file__), 'saved_models')
        if not os.path.exists(self.model_path):
            os.makedirs(self.model_path)

    def load_data(self, limit_reviews=100000):
        """Load dữ liệu từ MongoDB"""
        print("⏳ Đang tải dữ liệu từ MongoDB...")

        # 1. Load Reviews (Giới hạn số lượng để train nhanh)
        reviews_col = self.db.get_collection(config.COL_REVIEWS)
        # Chỉ lấy các trường cần thiết để tiết kiệm RAM
        reviews_cursor = reviews_col.find(
            {},
            {"user_id": 1, "product_id": 1, "rating": 1, "_id": 0}
        ).limit(limit_reviews)

        self.reviews_df = pd.DataFrame(list(reviews_cursor))
        print(f"   -> Đã load {len(self.reviews_df)} reviews.")

        # 2. Load Products (Chỉ lấy những sản phẩm có trong reviews để đồng bộ)
        if not self.reviews_df.empty:
            unique_products = self.reviews_df['product_id'].unique()
            products_col = self.db.get_collection(config.COL_PRODUCTS)
            products_cursor = products_col.find(
                {"_id": {"$in": list(unique_products)}},
                {"title": 1, "_id": 1}
            )
            self.products_df = pd.DataFrame(list(products_cursor))

            # Xử lý text null
            if not self.products_df.empty:
                self.products_df['title'] = self.products_df['title'].fillna('')
                self.products_df.set_index('_id', inplace=True)
                print(f"   -> Đã load {len(self.products_df)} sản phẩm tương ứng.")
            else:
                print("⚠️ Không tìm thấy thông tin sản phẩm tương ứng.")
        else:
            print("❌ Không có reviews nào để train.")

    def train_content_based(self):
        """
        MODEL 1: Content-Based Filtering
        Sử dụng TF-IDF để tìm độ tương đồng giữa các Tiêu đề sản phẩm
        """
        if self.products_df is None or self.products_df.empty:
            print("⚠️ Bỏ qua Content-Based do thiếu dữ liệu sản phẩm.")
            return

        print("🧠 [1/2] Đang train Content-Based Model (TF-IDF)...")

        # Tính TF-IDF (Chỉ lấy 5000 từ quan trọng nhất để nhẹ máy)
        tfidf = TfidfVectorizer(stop_words='english', max_features=5000)
        self.tfidf_matrix = tfidf.fit_transform(self.products_df['title'])

        # Tạo mapping index để tra cứu nhanh
        self.indices = pd.Series(self.products_df.index, index=range(len(self.products_df)))

        # Lưu model xuống ổ cứng
        with open(os.path.join(self.model_path, 'tfidf_matrix.pkl'), 'wb') as f:
            pickle.dump(self.tfidf_matrix, f)
        with open(os.path.join(self.model_path, 'indices.pkl'), 'wb') as f:
            pickle.dump(self.indices, f)
        print("✅ Đã lưu Content-Based Model.")

    def train_collaborative_filtering(self):
        """
        MODEL 2: Collaborative Filtering
        Sử dụng thuật toán SVD (Matrix Factorization)
        """
        if self.reviews_df is None or self.reviews_df.empty:
            return

        print("🧠 [2/2] Đang train Collaborative Filtering (SVD)...")

        # Chuẩn bị dữ liệu cho Surprise
        reader = Reader(rating_scale=(1, 5))
        data = Dataset.load_from_df(self.reviews_df[['user_id', 'product_id', 'rating']], reader)

        # Chia train/test set (80/20)
        trainset, testset = train_test_split(data, test_size=0.2)

        # Train model SVD
        # n_factors=100: Số lượng đặc trưng ẩn
        # n_epochs=20: Số vòng lặp train
        self.svd_model = SVD(n_factors=100, n_epochs=20, random_state=42)
        self.svd_model.fit(trainset)

        # Đánh giá độ chính xác
        print("📊 Đang đánh giá mô hình trên tập Test...")
        predictions = self.svd_model.test(testset)
        rmse = accuracy.rmse(predictions)
        mae = accuracy.mae(predictions)

        # Lưu model SVD
        with open(os.path.join(self.model_path, 'svd_model.pkl'), 'wb') as f:
            pickle.dump(self.svd_model, f)
        print(f"✅ Đã lưu Collaborative Filtering Model (RMSE: {rmse:.4f}).")


# --- MAIN RUN ---
if __name__ == "__main__":
    recommender = HybridRecommender()

    # 1. Load Data
    # Mình để limit 100k dòng để train cho nhanh.
    # Nếu máy khoẻ bạn có thể tăng lên hoặc bỏ .limit() trong hàm load_data
    recommender.load_data(limit_reviews=100000)

    # 2. Train Content Based
    recommender.train_content_based()

    # 3. Train Collaborative Filtering
    recommender.train_collaborative_filtering()

    print("\n🎉 HOÀN TẤT HUẤN LUYỆN MÔ HÌNH!")