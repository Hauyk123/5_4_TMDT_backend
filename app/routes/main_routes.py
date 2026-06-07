from flask import Blueprint, render_template, request, session, jsonify, abort, flash, redirect, url_for
import pandas as pd
import numpy as np
import pickle
import os
import random
import math
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity

# Import cấu hình và kết nối Polyglot (MySQL + MongoDB)
from config.settings import Config
from config.db_connection import get_mysql_connection, get_mongo_db

# Khởi tạo Blueprint
main_bp = Blueprint('main', __name__)

# --- 1. KHỞI TẠO KẾT NỐI MONGODB VÀ LOAD MODEL AI ---
mongo_db = get_mongo_db()
col_reviews = mongo_db['reviews'] if mongo_db is not None else None
col_search_logs = mongo_db['search_logs'] if mongo_db is not None else None

MODEL_PATH = os.path.join(Config.BASE_DIR, 'ai_core', 'models', 'saved_models')

# Load BERT Embeddings
try:
    with open(os.path.join(MODEL_PATH, 'bert_embeddings.pkl'), 'rb') as f:
        bert_embeddings = pickle.load(f)
    with open(os.path.join(MODEL_PATH, 'product_ids.pkl'), 'rb') as f:
        product_ids = pickle.load(f)
    print("✅ [AI Core] Đã load BERT Embeddings thành công.")
except Exception as e:
    bert_embeddings, product_ids = None, None
    print(f"⚠️ [AI Core] Không tìm thấy BERT Embeddings: {e}")

# Load SVD Model
try:
    with open(os.path.join(MODEL_PATH, 'svd_model.pkl'), 'rb') as f:
        svd_model = pickle.load(f)
    print("✅ [AI Core] Đã load SVD Model thành công.")
except Exception as e:
    svd_model = None
    print(f"⚠️ [AI Core] Không tìm thấy SVD Model: {e}")


# --- 2. HÀM TRỢ GIÚP (HELPER): LẤY DỮ LIỆU TỪ MYSQL ---
def get_products_from_mysql(id_list):
    """Lấy thông tin sản phẩm từ MySQL dựa trên danh sách ID từ AI"""
    if not id_list: return []
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        format_strings = ','.join(['%s'] * len(id_list))
        query = f"SELECT product_id, name, price, image_url, category_id, avg_rating FROM PRODUCT WHERE product_id IN ({format_strings})"
        cursor.execute(query, tuple(id_list))
        results = cursor.fetchall()

        # Ánh xạ lại tên biến để tương thích với HTML Template cũ (Mongo style)
        prod_map = {}
        for p in results:
            p['_id'] = p['product_id']
            p['title'] = p['name']
            p['images'] = [p['image_url']]  # Giả lập cấu trúc mảng ảnh của Mongo
            p['average_rating'] = p.get('avg_rating', 4.5)
            prod_map[p['product_id']] = p

        # Giữ đúng thứ tự ID mà AI trả về
        return [prod_map[pid] for pid in id_list if pid in prod_map]
    finally:
        cursor.close()
        conn.close()


# --- 3. CÁC HÀM LOGIC AI ĐÃ NÂNG CẤP ---
def get_bert_ids(target_id, top_k=12):
    if bert_embeddings is None or product_ids is None: return []
    try:
        if target_id in product_ids:
            idx = product_ids.index(target_id)
            sim_scores = cosine_similarity([bert_embeddings[idx]], bert_embeddings).flatten()
            sim_indices = sim_scores.argsort()[-(top_k + 1):-1][::-1]
            return [product_ids[i] for i in sim_indices]
    except:
        pass
    return []


def get_svd_ids(target_id, top_k=12):
    if svd_model is None: return []
    try:
        inner_id = svd_model.trainset.to_inner_iid(target_id)
        item_vector = svd_model.qi[inner_id]
        sims = cosine_similarity([item_vector], svd_model.qi).flatten()
        sim_indices = sims.argsort()[-(top_k + 1):-1][::-1]
        return [svd_model.trainset.to_raw_iid(i) for i in sim_indices]
    except:
        return []


def get_hybrid_recommendations(target_id, top_k=12):
    bert_ids = get_bert_ids(target_id, top_k=top_k)
    svd_ids = get_svd_ids(target_id, top_k=top_k)
    final_ids, seen_ids = [], set()
    max_len = max(len(bert_ids), len(svd_ids))
    for i in range(max_len):
        if i < len(bert_ids) and bert_ids[i] not in seen_ids:
            final_ids.append(bert_ids[i])
            seen_ids.add(bert_ids[i])
        if i < len(svd_ids) and svd_ids[i] not in seen_ids:
            final_ids.append(svd_ids[i])
            seen_ids.add(svd_ids[i])
        if len(final_ids) >= top_k: break

    return get_products_from_mysql(final_ids)


def get_random_products_mysql(limit=12):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT product_id, name as title, price, image_url, avg_rating FROM PRODUCT ORDER BY RAND() LIMIT %s",
            (limit,))
        results = cursor.fetchall()
        for p in results:
            p['_id'], p['images'] = p['product_id'], [p['image_url']]
            p['average_rating'] = p.get('avg_rating', 4.5)
        return results
    finally:
        cursor.close()
        conn.close()


def get_top_search_products(limit=6):
    if col_search_logs is None: return get_random_products_mysql(limit)
    top_keywords = list(col_search_logs.find().sort("count", -1).limit(limit))
    return get_random_products_mysql(limit)


# --- 4. ĐỊNH NGHĨA CÁC ROUTES ---
@main_bp.route('/')
def index():
    h = datetime.now().hour
    greeting = "Chào buổi sáng! ☀️" if 5 <= h < 12 else "Chào buổi chiều! 🌤️" if 12 <= h < 18 else "Chào buổi tối! 🌙"

    categories = {
        "🍳 Phòng Bếp": [
            {"name": "Tủ lạnh", "query": "refrigerator",
             "icon": "https://cdn-icons-png.flaticon.com/512/2662/2662588.png"},
            {"name": "Bếp (Gas/Từ)", "query": "cooktop stove",
             "icon": "https://cdn-icons-png.flaticon.com/512/3565/3565430.png"},
            {"name": "Lò vi sóng", "query": "microwave",
             "icon": "https://cdn-icons-png.flaticon.com/512/6526/6526841.png"},
            {"name": "Lò nướng", "query": "oven", "icon": "https://cdn-icons-png.flaticon.com/512/3565/3565430.png"},
            {"name": "Máy rửa bát", "query": "dishwasher",
             "icon": "https://cdn-icons-png.flaticon.com/512/2403/2403649.png"},
            {"name": "Nồi cơm điện", "query": "rice cooker",
             "icon": "https://cdn-icons-png.flaticon.com/512/1261/1261122.png"},
            {"name": "Máy xay", "query": "blender", "icon": "https://cdn-icons-png.flaticon.com/512/1261/1261044.png"}
        ],
        "🛋️ Phòng Khách": [
            {"name": "Tivi", "query": "television", "icon": "https://cdn-icons-png.flaticon.com/512/3054/3054889.png"},
            {"name": "Âm thanh", "query": "home theater system",
             "icon": "https://cdn-icons-png.flaticon.com/512/3342/3342130.png"},
            {"name": "Máy chiếu", "query": "projector",
             "icon": "https://cdn-icons-png.flaticon.com/512/3246/3246358.png"},
            {"name": "Quạt trần", "query": "ceiling fan",
             "icon": "https://cdn-icons-png.flaticon.com/512/2403/2403606.png"},
            {"name": "Đèn trang trí", "query": "chandelier light",
             "icon": "https://cdn-icons-png.flaticon.com/512/427/427735.png"}
        ],
        "🛏️ Phòng Ngủ": [
            {"name": "Điều hòa", "query": "air conditioner",
             "icon": "https://cdn-icons-png.flaticon.com/512/911/911409.png"},
            {"name": "Lọc không khí", "query": "air purifier",
             "icon": "https://cdn-icons-png.flaticon.com/512/2662/2662580.png"},
            {"name": "Máy hút ẩm", "query": "dehumidifier",
             "icon": "https://cdn-icons-png.flaticon.com/512/4047/4047321.png"},
            {"name": "Đèn ngủ", "query": "night light",
             "icon": "https://cdn-icons-png.flaticon.com/512/2987/2987995.png"}
        ],
        "🛁 Vệ Sinh & Giặt": [
            {"name": "Máy giặt", "query": "washing machine",
             "icon": "https://cdn-icons-png.flaticon.com/512/3565/3565154.png"},
            {"name": "Máy sấy", "query": "clothes dryer",
             "icon": "https://cdn-icons-png.flaticon.com/512/624/624838.png"},
            {"name": "Bình nóng lạnh", "query": "water heater",
             "icon": "https://cdn-icons-png.flaticon.com/512/2372/2372078.png"},
            {"name": "Máy hút bụi", "query": "vacuum cleaner",
             "icon": "https://cdn-icons-png.flaticon.com/512/2403/2403619.png"},
            {"name": "Bàn là", "query": "iron steam", "icon": "https://cdn-icons-png.flaticon.com/512/2372/2372093.png"}
        ]
    }

    viewed_ids = session.get('history', [])
    history_prods, personal_recs = [], []

    if viewed_ids:
        history_prods = get_products_from_mysql(viewed_ids[:10])
        seen_ids = set(viewed_ids)
        for vid in viewed_ids[:3]:
            for r in get_hybrid_recommendations(vid, top_k=5):
                if r['_id'] not in seen_ids:
                    personal_recs.append(r)
                    seen_ids.add(r['_id'])
        random.shuffle(personal_recs)

    return render_template('index.html', greeting=greeting, categories=categories,
                           history=history_prods, personal_recs=personal_recs[:12],
                           top_search=get_top_search_products(6),
                           top_trending=get_random_products_mysql(6),
                           today_recs=get_random_products_mysql(12))




@main_bp.route('/search')
def search():
    """Hàm xử lý tìm kiếm sản phẩm kết hợp Bộ lọc nâng cao và Sắp xếp"""
    # 1. Hứng toàn bộ tham số từ form giao diện truyền lên URL
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'relevance')

    # Hứng tham số bộ lọc (ép kiểu float/int an toàn)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    rating = request.args.get('rating', type=int)

    per_page = 12  # Số sản phẩm trên 1 trang

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 2. Xây dựng câu SQL nền tảng (Luôn bỏ qua các sản phẩm giá 0 hoặc bị khóa)
        base_sql = "FROM PRODUCT WHERE (price > 0 OR price IS NOT NULL)"
        # Nếu bảng có cột status, thêm vào: base_sql += " AND status = 'ACTIVE'"
        params = []

        # -- Nối điều kiện: Từ khóa tìm kiếm --
        if query:
            base_sql += " AND name LIKE %s"
            params.append(f"%{query}%")

        # -- Nối điều kiện: Bộ lọc khoảng giá --
        if min_price is not None:
            base_sql += " AND price >= %s"
            params.append(min_price)
        if max_price is not None:
            base_sql += " AND price <= %s"
            params.append(max_price)

        # -- Nối điều kiện: Bộ lọc đánh giá sao --
        if rating is not None:
            # Chú ý tên cột đánh giá, ở đây giả sử là avg_rating
            base_sql += " AND avg_rating >= %s"
            params.append(rating)

        # 3. Xử lý Sắp xếp (Sorting)
        order_clause = ""
        if sort == 'price_asc':
            order_clause = " ORDER BY price ASC"
        elif sort == 'price_desc':
            order_clause = " ORDER BY price DESC"
        elif sort == 'review_desc':
            # Sắp xếp theo số lượt mua hoặc số sao
            order_clause = " ORDER BY avg_rating DESC"
        else:
            # Mặc định relevance (sản phẩm mới nhất hoặc khớp nhất)
            order_clause = " ORDER BY product_id DESC"

        # 4. Đếm tổng số sản phẩm THỎA MÃN BỘ LỌC để phân trang
        count_sql = "SELECT COUNT(product_id) as total " + base_sql
        cursor.execute(count_sql, tuple(params))
        total_products = cursor.fetchone()['total'] or 0

        # Tính toán tham số phân trang
        total_pages = math.ceil(total_products / per_page) if total_products > 0 else 1
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page

        # 5. Truy vấn dữ liệu thực tế đẩy ra giao diện
        # Chú ý: Đổi tên cột cho khớp với biến trong HTML (product_id as _id, name as title)
        fetch_sql = f"""
            SELECT product_id as _id, name as title, price, image_url, avg_rating 
            {base_sql} 
            {order_clause} 
            LIMIT %s OFFSET %s
        """
        fetch_params = params + [per_page, offset]

        cursor.execute(fetch_sql, tuple(fetch_params))
        results = cursor.fetchall()

        # Lấy lịch sử xem gần đây từ session (Nếu kĩ sư đã làm logic này)
        history = session.get('recently_viewed', [])

        # 6. Truyền TRẢ LẠI các biến bộ lọc xuống giao diện để HTML giữ nguyên lựa chọn của khách
        return render_template('search_results.html',
                               query=query,
                               results=results,
                               total_products=total_products,
                               page=page,
                               total_pages=total_pages,
                               current_sort=sort,
                               current_min_price=min_price,
                               current_max_price=max_price,
                               current_rating=rating,
                               history=history)

    except Exception as e:
        print(f"❌ Lỗi tìm kiếm / lọc sản phẩm: {e}")
        return redirect(url_for('main.index'))
    finally:
        cursor.close()
        conn.close()
@main_bp.route('/product/<product_id>')
def product_detail(product_id):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM PRODUCT WHERE product_id = %s", (product_id,))
        p = cursor.fetchone()
        if not p: abort(404)

        p['_id'], p['title'], p['images'] = p['product_id'], p['name'], [p['image_url']]
    finally:
        cursor.close()
        conn.close()

    # Cập nhật History
    hist = session.get('history', [])
    if product_id in hist: hist.remove(product_id)
    hist.insert(0, product_id)
    session['history'] = hist[:10]
    session.modified = True

    # --- BỔ SUNG: TÍNH TOÁN REVIEW VÀ CẢM XÚC (SENTIMENT) TỪ MONGODB ---
    reviews_list = []
    total_reviews = 0
    avg_rating = 4.5
    sentiment = {"pos": 100, "neu": 0, "neg": 0}  # Mặc định nếu chưa có đánh giá

    if col_reviews is not None:
        total_reviews = col_reviews.count_documents({"product_id": product_id})

        if total_reviews > 0:
            reviews_list = list(col_reviews.find({"product_id": product_id}).sort("timestamp", -1).limit(20))

            # Tính điểm trung bình
            pipeline = [
                {"$match": {"product_id": product_id}},
                {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}
            ]
            agg_result = list(col_reviews.aggregate(pipeline))
            if agg_result:
                avg_rating = round(agg_result[0]['avg_rating'], 1)

            # Đếm phân loại cảm xúc (Sentiment Dynamics)
            pos_count = sum(1 for r in reviews_list if r.get('rating', 5) >= 4)
            neu_count = sum(1 for r in reviews_list if r.get('rating', 5) == 3)
            neg_count = sum(1 for r in reviews_list if r.get('rating', 5) <= 2)

            sentiment = {
                "pos": round((pos_count / len(reviews_list)) * 100),
                "neu": round((neu_count / len(reviews_list)) * 100),
                "neg": round((neg_count / len(reviews_list)) * 100)
            }

    p['avg_rating'] = avg_rating
    p['review_count'] = total_reviews

    # AI Model Recommendation
    model = request.args.get('model', 'hybrid')
    recs = get_hybrid_recommendations(product_id)

    return render_template('product_detail.html',
                           product=p,
                           recommendations=recs,
                           selected_model=model,
                           reviews=reviews_list,
                           total_reviews=total_reviews,
                           sentiment=sentiment)  # Truyền Sentiment thật xuống HTML


# --- API ĐĂNG ĐÁNH GIÁ MỚI VÀO MONGODB (CÓ KIỂM TRA LỊCH SỬ MUA HÀNG) ---
@main_bp.route('/product/<string:product_id>/review', methods=['POST'])
def submit_review(product_id):
    """Tiếp nhận review, kiểm tra đã mua hàng bên MySQL, ghi vào Mongo và đồng bộ điểm"""
    user_id = session.get('user_id')
    user_name = session.get('user_name', 'Khách hàng Amazon')

    if not user_id:
        flash('Vui lòng đăng nhập để đánh giá sản phẩm.', 'warning')
        return redirect(url_for('auth.login'))

    # =====================================================================
    # 1. BẢO MẬT KINH DOANH: KIỂM TRA KHÁCH ĐÃ MUA & NHẬN HÀNG CHƯA (MYSQL)
    # =====================================================================
    mysql_conn = get_mysql_connection()
    try:
        with mysql_conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT o.order_id 
                FROM ORDERS o
                JOIN ORDER_ITEM oi ON o.order_id = oi.order_id
                WHERE o.user_id = %s 
                  AND oi.product_id = %s 
                  AND o.status = 'DELIVERED'
                LIMIT 1
            """, (user_id, product_id))

            has_purchased = cursor.fetchone()

            if not has_purchased:
                flash('⛔ Bạn chỉ có thể đánh giá sau khi đã mua và nhận sản phẩm này thành công!', 'warning')
                return redirect(url_for('main.product_detail', product_id=product_id))
    except Exception as e:
        print(f"❌ Lỗi kiểm tra lịch sử mua hàng MySQL: {e}")
        flash('Lỗi hệ thống khi xác thực quyền đánh giá.', 'danger')
        return redirect(url_for('main.product_detail', product_id=product_id))
    finally:
        mysql_conn.close()

    # =====================================================================
    # 2. NẾU ĐÃ MUA HÀNG -> LẤY DỮ LIỆU & LƯU VÀO MONGODB
    # =====================================================================
    rating = request.form.get('rating', 5, type=int)
    title = request.form.get('title', '').strip()
    review_text = request.form.get('text', '').strip()

    if not review_text:
        flash('Nội dung đánh giá không được để trống.', 'warning')
        return redirect(url_for('main.product_detail', product_id=product_id))

    if col_reviews is None:
        flash('Lỗi kết nối cơ sở dữ liệu phi cấu trúc (MongoDB). Vui lòng thử lại sau.', 'danger')
        return redirect(url_for('main.product_detail', product_id=product_id))

    review_document = {
        "product_id": product_id,
        "userId": user_id,
        "reviewerName": user_name,
        "rating": rating,
        "title": title,
        "text": review_text,
        "timestamp": datetime.utcnow().strftime('%d/%m/%Y %H:%M'),
        "verified": True  # Lúc này gán True là hoàn toàn chính xác do đã vượt qua chốt chặn MySQL
    }

    try:
        # Ghi vào collection 'reviews' trong MongoDB
        col_reviews.insert_one(review_document)

        # Đồng bộ tính toán lại sang MySQL để làm báo cáo
        all_reviews = list(col_reviews.find({"product_id": product_id}))
        total_revs = len(all_reviews)
        avg_rat = sum(r.get('rating', 5) for r in all_reviews) / total_revs if total_revs > 0 else 5.0

        mysql_sync_conn = get_mysql_connection()
        with mysql_sync_conn.cursor() as sync_cursor:
            sync_cursor.execute("""
                UPDATE PRODUCT 
                SET avg_rating = %s, review_count = %s 
                WHERE product_id = %s
            """, (round(avg_rat, 1), total_revs, product_id))
        mysql_sync_conn.commit()
        mysql_sync_conn.close()

        flash('✨ Cảm ơn bạn đã gửi đánh giá! Trải nghiệm của bạn sẽ giúp AI gợi ý tốt hơn.', 'success')
    except Exception as e:
        print(f"❌ Lỗi lưu review: {e}")
        flash('Có lỗi xảy ra khi lưu đánh giá. Vui lòng thử lại.', 'danger')

    return redirect(url_for('main.product_detail', product_id=product_id))
@main_bp.route('/api/suggest')
def api_suggest():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT product_id, name as title FROM PRODUCT WHERE name LIKE %s LIMIT 10", (f"%{query}%",))
        prods = cursor.fetchall()
        suggestions = [{"type": "product", "id": str(p['product_id']), "label": p['title']} for p in prods]
        return jsonify(suggestions)
    finally:
        cursor.close()
        conn.close()


@main_bp.route('/dashboard')
def dashboard():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM PRODUCT")
    total_prods = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    stats = {
        "total_products": "{:,}".format(total_prods),
        "total_reviews": "{:,}".format(col_reviews.count_documents({}) if col_reviews is not None else 0),
        "avg_rating": 4.5,
        "model": {"rmse": "0.85", "last_updated": datetime.now().strftime("%Y-%m-%d")}
    }
    return render_template('dashboard.html', stats=stats)


@main_bp.route('/api/get_vouchers', methods=['GET'])
def get_vouchers():
    """API lấy danh sách các mã voucher đang hoạt động để hiển thị trên Dropdown Menu"""
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # ĐÃ SỬA: Đổi ORDER BY created_at thành ORDER BY start_date
        cursor.execute("""
            SELECT code, discount_type, discount_value, min_order_value, max_discount
            FROM VOUCHER 
            WHERE status = 'ACTIVE' 
              AND NOW() BETWEEN start_date AND end_date
              AND used_count < usage_limit
            ORDER BY start_date DESC LIMIT 5
        """)
        vouchers = cursor.fetchall()

        # Định dạng lại dữ liệu trả về JSON cho mượt
        result = []
        for v in vouchers:
            result.append({
                "code": v['code'],
                "type": v['discount_type'],
                "value": float(v['discount_value']),
                "min_order": float(v['min_order_value']),
                "max_discount": float(v['max_discount']) if v['max_discount'] else None
            })
        return jsonify(result)
    except Exception as e:
        print(f"❌ Lỗi API lấy danh sách voucher: {e}")
        return jsonify([])
    finally:
        cursor.close()
        conn.close()