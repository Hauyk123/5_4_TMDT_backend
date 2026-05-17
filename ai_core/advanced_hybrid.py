import pandas as pd
import numpy as np
import pickle
import os
import sys
import json
from datetime import datetime
from collections import defaultdict
from surprise.model_selection import GridSearchCV

# --- CẤU HÌNH ĐƯỜNG DẪN ---
# Hack path để import config từ thư mục cha
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db_connection import Database

# --- IMPORT THƯ VIỆN AI ---
try:
    from surprise import Reader, Dataset, SVD
    from surprise.model_selection import train_test_split
    from surprise import accuracy

    print("✅ Đã nạp thư viện Surprise (SVD).")
except ImportError:
    print("❌ Lỗi: Chưa cài 'scikit-surprise'. Hãy chạy: pip install scikit-surprise")
    sys.exit(1)

# Không bắt buộc SentenceTransformer vì chúng ta sẽ dùng file có sẵn từ cleaner
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class UltimateRecommenderTrainer:
    def __init__(self):
        self.db = Database()
        # Đảm bảo đường dẫn này khớp với nơi advanced_cleaner.py đã lưu
        self.model_path = os.path.join(os.path.dirname(__file__), 'saved_models')

        if not os.path.exists(self.model_path):
            os.makedirs(self.model_path)

        self.products_df = None
        self.reviews_df = None

        # Kiểm tra xem đã có vector từ cleaner chưa
        self.bert_exists = (
                os.path.exists(os.path.join(self.model_path, 'bert_embeddings.pkl')) and
                os.path.exists(os.path.join(self.model_path, 'product_ids.pkl'))
        )

    def load_data(self):
        """
        Tải dữ liệu từ MongoDB.
        Tối ưu: Nếu đã có BERT embeddings thì không cần tải chi tiết sản phẩm nữa.
        """
        print("\n🔄 [1/4] Đang tải dữ liệu từ MongoDB...")

        # 1. Load Products (Chỉ tải nếu chưa chạy Cleaner)
        if not self.bert_exists:
            print("   -> Chưa thấy file vector, đang tải dữ liệu sản phẩm để tạo vector...")
            products_col = self.db.get_collection(config.COL_PRODUCTS)
            products_cursor = products_col.find(
                {"title": {"$exists": True, "$ne": ""}},
                {"title": 1}
            )
            self.products_df = pd.DataFrame(list(products_cursor))
            if not self.products_df.empty:
                self.products_df['_id'] = self.products_df['_id'].astype(str)
                print(f"   -> Đã tải xong {len(self.products_df)} sản phẩm.")
        else:
            print("   -> ✅ Đã phát hiện file vector từ 'advanced_cleaner.py'. Bỏ qua bước tải sản phẩm.")

        # 2. Load Reviews (Luôn cần tải để train SVD)
        reviews_col = self.db.get_collection(config.COL_REVIEWS)
        # Lấy hết toàn bộ review
        reviews_cursor = reviews_col.find(
            {},
            {"user_id": 1, "product_id": 1, "rating": 1, "_id": 0}
        )

        self.reviews_df = pd.DataFrame(list(reviews_cursor))
        print(f"   -> Đã tải xong {len(self.reviews_df)} đánh giá (cho Collaborative Filtering).")

        if len(self.reviews_df) < 1000:
            print("   ⚠️ Lưu ý: Số lượng review ít (<1000), kết quả gợi ý có thể chưa chuẩn.")

    def train_content_based_bert(self):
        """
        HUẤN LUYỆN MODEL 1: CONTENT-BASED (BERT)
        Logic mới: Nếu file đã tồn tại (do cleaner tạo) thì BỎ QUA.
        """
        print("\n🧠 [2/4] Kiểm tra Content-Based (BERT)...")

        if self.bert_exists:
            print("   ✅ Đã tìm thấy 'bert_embeddings.pkl' từ Cleaner.")
            print("   ⏩ Bỏ qua bước mã hóa văn bản (Tiết kiệm thời gian & RAM).")
            return

        # Nếu chưa có thì mới chạy (phòng hờ)
        if self.products_df is None or self.products_df.empty:
            print("   ⚠️ Không có dữ liệu sản phẩm để chạy BERT.")
            return

        if SentenceTransformer is None:
            print("   ⚠️ Không có thư viện sentence_transformers.")
            return

        print("   ⚠️ Không tìm thấy file cũ. Đang chạy tạo mới (Sẽ lâu)...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        titles = self.products_df['title'].tolist()

        # Tăng batch_size
        bert_embeddings = model.encode(titles, batch_size=64, show_progress_bar=True)
        product_ids = self.products_df['_id'].tolist()

        with open(os.path.join(self.model_path, 'bert_embeddings.pkl'), 'wb') as f:
            pickle.dump(bert_embeddings, f)
        with open(os.path.join(self.model_path, 'product_ids.pkl'), 'wb') as f:
            pickle.dump(product_ids, f)

        print("   ✅ Đã tạo và lưu xong BERT Embeddings.")

    def calculate_precision_recall_at_k(self, predictions, k=10, threshold=3.5):
        """Hàm đánh giá độ chính xác"""
        user_est_true = defaultdict(list)
        for uid, _, true_r, est, _ in predictions:
            user_est_true[uid].append((est, true_r))

        precisions = dict()
        recalls = dict()

        for uid, user_ratings in user_est_true.items():
            user_ratings.sort(key=lambda x: x[0], reverse=True)
            n_rel = sum((true_r >= threshold) for (_, true_r) in user_ratings)
            n_rec_k = sum((est >= threshold) for (est, _) in user_ratings[:k])
            n_rel_and_rec_k = sum(((true_r >= threshold) and (est >= threshold))
                                  for (est, true_r) in user_ratings[:k])

            precisions[uid] = n_rel_and_rec_k / n_rec_k if n_rec_k != 0 else 0
            recalls[uid] = n_rel_and_rec_k / n_rel if n_rel != 0 else 0

        avg_precision = sum(prec for prec in precisions.values()) / len(precisions) if precisions else 0
        avg_recall = sum(rec for rec in recalls.values()) / len(recalls) if recalls else 0
        return avg_precision, avg_recall

    def train_collaborative_svd(self):
        """
        HUẤN LUYỆN MODEL 2: SVD VỚI GRID SEARCH
        Cập nhật: Hạ ngưỡng lọc xuống 3 để lấy nhiều dữ liệu hơn
        """
        print("\n🧠 [3/4] Bắt đầu Grid Search để tìm tham số tốt nhất...")

        if self.reviews_df is None or self.reviews_df.empty:
            print("   ❌ Không có dữ liệu Review.")
            return

        # --- BƯỚC 1: LỌC DỮ LIỆU (NGƯỠNG 3) ---
        print(f"   📉 Dữ liệu thô: {len(self.reviews_df):,} dòng.")

        # [ĐÃ SỬA] Hạ xuống 3.
        # Ý nghĩa: Giữ lại User đánh giá >= 3 lần & Sản phẩm được đánh giá >= 3 lần
        min_threshold = 3

        print(f"   ... Đang lọc giữ lại tương tác >= {min_threshold}...")

        # Lọc User
        user_counts = self.reviews_df['user_id'].value_counts()
        active_users = user_counts[user_counts >= min_threshold].index
        self.reviews_df = self.reviews_df[self.reviews_df['user_id'].isin(active_users)]

        # Lọc Product
        prod_counts = self.reviews_df['product_id'].value_counts()
        active_prods = prod_counts[prod_counts >= min_threshold].index
        self.reviews_df = self.reviews_df[self.reviews_df['product_id'].isin(active_prods)]

        print(f"   📉 Dữ liệu train (Clean): {len(self.reviews_df):,} dòng.")

        if len(self.reviews_df) == 0: return
        # --------------------------------------------------------

        # Setup dữ liệu
        reader = Reader(rating_scale=(1, 5))
        data = Dataset.load_from_df(self.reviews_df[['user_id', 'product_id', 'rating']], reader)

        # --- BƯỚC 2: CẤU HÌNH GRID SEARCH ---
        print("   🚀 Đang chạy Grid Search (Dữ liệu nhiều hơn nên sẽ lâu hơn xíu)...")

        param_grid = {
            'n_factors': [50, 100],
            'n_epochs': [20, 30],
            'lr_all': [0.005, 0.01],
            'reg_all': [0.05, 0.1]
        }

        gs = GridSearchCV(SVD, param_grid, measures=['rmse', 'mae'], cv=3, n_jobs=-1)
        gs.fit(data)

        # IN KẾT QUẢ GRID SEARCH
        print("\n   🔍 --- KẾT QUẢ TÌM KIẾM THAM SỐ (GRID SEARCH) ---")
        print(f"   💎 Best RMSE: {gs.best_score['rmse']:.4f} | Tham số: {gs.best_params['rmse']}")
        print(f"   💎 Best MAE:  {gs.best_score['mae']:.4f} | Tham số: {gs.best_params['mae']}")

        best_params = gs.best_params['rmse']

        # --- BƯỚC 3: TRAIN & ĐÁNH GIÁ ---
        print(f"\n   ⚙️ Đang train model cuối cùng với tham số tối ưu: {best_params}...")

        svd = SVD(
            n_factors=best_params['n_factors'],
            n_epochs=best_params['n_epochs'],
            lr_all=best_params['lr_all'],
            reg_all=best_params['reg_all'],
            random_state=42
        )

        # Chia train/test 80/20
        trainset, testset = train_test_split(data, test_size=0.2, random_state=42)
        svd.fit(trainset)
        predictions = svd.test(testset)

        # Tính toán chỉ số
        rmse = accuracy.rmse(predictions, verbose=False)
        mae = accuracy.mae(predictions, verbose=False)
        prec, rec = self.calculate_precision_recall_at_k(predictions, k=10, threshold=4.0)

        # IN BẢNG BÁO CÁO
        print("\n   📊 --- BẢNG ĐÁNH GIÁ HIỆU SUẤT (TEST SET) ---")
        print(f"   🎯 RMSE:          {rmse:.4f}  (Mục tiêu < 1.0)")
        print(f"   🎯 MAE:           {mae:.4f}")
        print(f"   🎯 Precision@10:  {prec:.4f}")
        print(f"   🎯 Recall@10:     {rec:.4f}")
        print("   ---------------------------------------------")

        # Lưu kết quả JSON
        metrics = {
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(os.path.join(self.model_path, 'model_metrics.json'), 'w') as f:
            json.dump(metrics, f)

        # Train Full & Save
        full_trainset = data.build_full_trainset()
        svd.fit(full_trainset)
        with open(os.path.join(self.model_path, 'svd_model.pkl'), 'wb') as f:
            pickle.dump(svd, f)
        print("   ✅ Đã hoàn tất và lưu model.")
# --- CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    print("🚀 KHỞI ĐỘNG TRAIN FULL DATASET (OPTIMIZED)")
    sys.setrecursionlimit(5000)

    trainer = UltimateRecommenderTrainer()

    # 1. Tải dữ liệu (Sẽ tự động bỏ qua Products nếu đã có BERT)
    trainer.load_data()

    # 2. Xử lý Content-Based (Sẽ tự động bỏ qua nếu đã có file)
    trainer.train_content_based_bert()

    # 3. Train Collaborative Filtering (Luôn chạy)
    trainer.train_collaborative_svd()

    print("\n🎉 HOÀN TẤT! Hệ thống đã sẵn sàng.")