# File: app/routes/main_routes.py
from flask import Blueprint, render_template, request, session, jsonify, url_for, redirect
import pandas as pd
import numpy as np
import pickle
import os
import random
import math
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity

from app.controllers.auth_controller import get_mysql_connection
from config.settings import Config
from config.db_connection import Database

# Khởi tạo Blueprint
main_bp = Blueprint('main', __name__)

# --- 1. KHỞI TẠO KẾT NỐI VÀ LOAD MODEL ---
db = Database()
col_products = db.get_collection("products")
col_reviews = db.get_collection("reviews")
col_search_logs = db.get_collection("search_logs")

# Đường dẫn model lấy từ Config
MODEL_PATH = os.path.join(Config.BASE_DIR, 'ai_core', 'models', 'saved_models')

# Load BERT Embeddings
try:
    with open(os.path.join(MODEL_PATH, 'bert_embeddings.pkl'), 'rb') as f:
        bert_embeddings = pickle.load(f)
    with open(os.path.join(MODEL_PATH, 'product_ids.pkl'), 'rb') as f:
        product_ids = pickle.load(f)
    print("✅ [AI Core] Đã load BERT Embeddings thành công.")
except:
    bert_embeddings, product_ids = None, None
    print("⚠️ [AI Core] Không tìm thấy BERT Embeddings.")

# Load SVD Model
try:
    with open(os.path.join(MODEL_PATH, 'svd_model.pkl'), 'rb') as f:
        svd_model = pickle.load(f)
    print("✅ [AI Core] Đã load SVD Model thành công.")
except:
    svd_model = None
    print("⚠️ [AI Core] Không tìm thấy SVD Model.")


# --- 2. CÁC HÀM LOGIC AI (HELPER FUNCTIONS) ---

def get_bert_recommendations(target_id, top_k=12):
    if bert_embeddings is None or product_ids is None: return []
    try:
        if target_id in product_ids:
            idx = product_ids.index(target_id)
            sim_scores = cosine_similarity([bert_embeddings[idx]], bert_embeddings).flatten()
            sim_indices = sim_scores.argsort()[-(top_k + 1):-1][::-1]
            rec_ids = [product_ids[i] for i in sim_indices]
            return list(col_products.find({"_id": {"$in": rec_ids}}, {"title": 1, "price": 1, "images": 1}))
    except:
        pass
    return []

def get_svd_recommendations(target_id, top_k=12):
    if svd_model is None: return []
    try:
        inner_id = svd_model.trainset.to_inner_iid(target_id)
        item_vector = svd_model.qi[inner_id]
        sims = cosine_similarity([item_vector], svd_model.qi).flatten()
        sim_indices = sims.argsort()[-(top_k + 1):-1][::-1]
        rec_ids = [svd_model.trainset.to_raw_iid(i) for i in sim_indices]
        return list(col_products.find({"_id": {"$in": rec_ids}}, {"title": 1, "price": 1, "images": 1}))
    except:
        return []

def get_hybrid_recommendations(target_id, top_k=12):
    bert_list = get_bert_recommendations(target_id, top_k=top_k)
    svd_list = get_svd_recommendations(target_id, top_k=top_k)
    final_recs, seen_ids = [], set()
    max_len = max(len(bert_list), len(svd_list))
    for i in range(max_len):
        if i < len(bert_list) and bert_list[i]['_id'] not in seen_ids:
            final_recs.append(bert_list[i]);
            seen_ids.add(bert_list[i]['_id'])
        if i < len(svd_list) and svd_list[i]['_id'] not in seen_ids:
            final_recs.append(svd_list[i]);
            seen_ids.add(svd_list[i]['_id'])
        if len(final_recs) >= top_k: break
    return final_recs

def get_random_products(limit=12):
    return list(col_products.aggregate([{"$sample": {"size": limit}}]))

def get_top_search_products(limit=6):
    top_keywords = list(col_search_logs.find().sort("count", -1).limit(limit))
    products, seen_ids = [], set()
    for log in top_keywords:
        p = col_products.find_one({"title": {"$regex": log['term'], "$options": "i"}})
        if p and p['_id'] not in seen_ids:
            products.append(p);
            seen_ids.add(p['_id'])
    if len(products) < limit:
        for p in get_random_products(limit - len(products)):
            if p['_id'] not in seen_ids: products.append(p); seen_ids.add(p['_id'])
    return products[:limit]

def get_popular_products(limit=12):
    popular = list(col_reviews.aggregate([
        {"$group": {"_id": "$product_id", "count": {"$sum": 1}, "avg_rating": {"$avg": "$rating"}}},
        {"$sort": {"count": -1}}, {"$limit": limit}
    ]))
    ids = [x['_id'] for x in popular]
    products = list(col_products.find({"_id": {"$in": ids}}))
    prod_map = {p['_id']: p for p in products}
    results = []
    for item in popular:
        if item['_id'] in prod_map:
            p = prod_map[item['_id']]
            p['review_count'], p['avg_rating'] = item['count'], round(item['avg_rating'], 1)
            results.append(p)
    return results


# --- 3. ĐỊNH NGHĨA CÁC ROUTES ---

@main_bp.route('/')
def index():
    h = datetime.now().hour
    greeting = "Chào buổi sáng! ☀️" if 5 <= h < 12 else "Chào buổi chiều! 🌤️" if 12 <= h < 18 else "Chào buổi tối! 🌙"

    # Danh mục sản phẩm
    categories = {
        "🍳 Phòng Bếp": [
            {"name": "Tủ lạnh", "query": "refrigerator", "icon": "https://cdn-icons-png.flaticon.com/512/2662/2662588.png"},
            {"name": "Bếp (Gas/Từ)", "query": "cooktop stove", "icon": "https://cdn-icons-png.flaticon.com/512/3565/3565430.png"},
            {"name": "Lò vi sóng", "query": "microwave", "icon": "https://cdn-icons-png.flaticon.com/512/6526/6526841.png"},
            {"name": "Lò nướng", "query": "oven", "icon": "https://cdn-icons-png.flaticon.com/512/3565/3565430.png"},
            {"name": "Máy rửa bát", "query": "dishwasher", "icon": "https://cdn-icons-png.flaticon.com/512/2403/2403649.png"},
            {"name": "Nồi cơm điện", "query": "rice cooker", "icon": "https://cdn-icons-png.flaticon.com/512/1261/1261122.png"},
            {"name": "Máy xay", "query": "blender", "icon": "https://cdn-icons-png.flaticon.com/512/1261/1261044.png"}
        ],
        "🛋️ Phòng Khách": [
            {"name": "Tivi", "query": "television", "icon": "https://cdn-icons-png.flaticon.com/512/3054/3054889.png"},
            {"name": "Âm thanh", "query": "home theater system", "icon": "https://cdn-icons-png.flaticon.com/512/3342/3342130.png"},
            {"name": "Máy chiếu", "query": "projector", "icon": "https://cdn-icons-png.flaticon.com/512/3246/3246358.png"},
            {"name": "Quạt trần", "query": "ceiling fan", "icon": "https://cdn-icons-png.flaticon.com/512/2403/2403606.png"},
            {"name": "Đèn trang trí", "query": "chandelier light", "icon": "https://cdn-icons-png.flaticon.com/512/427/427735.png"}
        ],
        "🛏️ Phòng Ngủ": [
            {"name": "Điều hòa", "query": "air conditioner", "icon": "https://cdn-icons-png.flaticon.com/512/911/911409.png"},
            {"name": "Lọc không khí", "query": "air purifier", "icon": "https://cdn-icons-png.flaticon.com/512/2662/2662580.png"},
            {"name": "Máy hút ẩm", "query": "dehumidifier", "icon": "https://cdn-icons-png.flaticon.com/512/4047/4047321.png"},
            {"name": "Đèn ngủ", "query": "night light", "icon": "https://cdn-icons-png.flaticon.com/512/2987/2987995.png"}
        ],
        "🛁 Vệ Sinh & Giặt": [
            {"name": "Máy giặt", "query": "washing machine", "icon": "https://cdn-icons-png.flaticon.com/512/3565/3565154.png"},
            {"name": "Máy sấy", "query": "clothes dryer", "icon": "https://cdn-icons-png.flaticon.com/512/624/624838.png"},
            {"name": "Bình nóng lạnh", "query": "water heater", "icon": "https://cdn-icons-png.flaticon.com/512/2372/2372078.png"},
            {"name": "Máy hút bụi", "query": "vacuum cleaner", "icon": "https://cdn-icons-png.flaticon.com/512/2403/2403619.png"},
            {"name": "Bàn là", "query": "iron steam", "icon": "https://cdn-icons-png.flaticon.com/512/2372/2372093.png"}
        ]
    }

    viewed_ids = session.get('history', [])
    history_prods, personal_recs = [], []

    if viewed_ids:
        raw_prods = list(col_products.find({"_id": {"$in": viewed_ids[:10]}}, {"title": 1, "images": 1, "price": 1}))
        prod_map = {p['_id']: p for p in raw_prods}
        history_prods = [prod_map[vid] for vid in viewed_ids[:10] if vid in prod_map]

        # Gợi ý cá nhân hóa
        seen_ids = set(viewed_ids)
        for vid in viewed_ids[:3]:
            for r in get_hybrid_recommendations(vid, top_k=5):
                if r['_id'] not in seen_ids: personal_recs.append(r); seen_ids.add(r['_id'])
        random.shuffle(personal_recs)

    return render_template('index.html', greeting=greeting, categories=categories,
                           history=history_prods, personal_recs=personal_recs[:12],
                           top_search=get_top_search_products(6),
                           top_trending=get_popular_products(6),
                           today_recs=get_random_products(12))

@main_bp.route('/profile')
def profile():
    """Trang cá nhân (Chặn nếu chưa đăng nhập)"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('profile.html')

@main_bp.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'relevance')
    per_page, skip = 12, (page - 1) * 12

    filter_query = {"$or": [{"title": {"$regex": query, "$options": "i"}},
                            {"description": {"$regex": query, "$options": "i"}}]} if query else {}
    sort_criteria = [('price', 1)] if sort_by == 'price_asc' else [('price', -1)] if sort_by == 'price_desc' else [('_id', 1)]

    total_products = col_products.count_documents(filter_query)
    results = list(col_products.find(filter_query).sort(sort_criteria).skip(skip).limit(per_page))

    if query and page == 1:
        col_search_logs.update_one({"term": query.lower()}, {"$inc": {"count": 1}}, upsert=True)

    return render_template('search_results.html', query=query, results=results, page=page,
                           total_pages=math.ceil(total_products / per_page), total_products=total_products)

@main_bp.route('/product/<product_id>')
def product_detail(product_id):
    product = col_products.find_one({"_id": product_id})
    if not product: return "Sản phẩm không tồn tại", 404

    # Xử lý History Session
    hist = session.get('history', [])
    if product_id in hist: hist.remove(product_id)
    hist.insert(0, product_id)
    session['history'] = hist[:10]
    session.modified = True

    model = request.args.get('model', 'hybrid')
    recs = get_hybrid_recommendations(product_id) if model == 'hybrid' else get_bert_recommendations(product_id)

    return render_template('product_detail.html', product=product, recommendations=recs, selected_model=model,
                           sentiment={"pos": 80, "neu": 15, "neg": 5})

@main_bp.route('/api/suggest')
def api_suggest():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])
    prods = list(
        col_products.find({"title": {"$regex": query, "$options": "i"}}, {"title": 1, "images": 1, "price": 1}).limit(10))
    suggestions = [{"type": "product", "id": str(p['_id']), "label": p['title']} for p in prods]
    return jsonify(suggestions)

@main_bp.route('/dashboard')
def dashboard():
    stats = {
        "total_products": "{:,}".format(col_products.count_documents({})),
        "total_reviews": "{:,}".format(col_reviews.count_documents({})),
        "avg_rating": 4.5,
        "model": {"rmse": "0.85", "last_updated": datetime.now().strftime("%Y-%m-%d")}
    }
    return render_template('dashboard.html', stats=stats)