# File: app/controllers/cart_controller.py
from flask import session
from config.db_connection import Database


def get_cart_items():
    """Lấy chi tiết các sản phẩm đang có trong giỏ hàng từ MongoDB"""
    cart = session.get('cart', {})  # cart = {'product_id': quantity}
    if not cart:
        return [], 0, 0

    db = Database()
    col_products = db.get_collection("products")

    product_ids = list(cart.keys())
    # Lấy thông tin từ MongoDB
    products = list(col_products.find({"_id": {"$in": product_ids}}))

    cart_items = []
    total_price = 0
    total_items = 0

    for p in products:
        pid = str(p['_id'])
        quantity = cart[pid]
        subtotal = float(p.get('price', 0)) * quantity

        cart_items.append({
            'id': pid,
            'title': p.get('title', 'Sản phẩm không xác định'),
            'price': p.get('price', 0),
            'image': p.get('images', [''])[0] if p.get('images') else '',
            'quantity': quantity,
            'subtotal': subtotal
        })
        total_price += subtotal
        total_items += quantity

    return cart_items, total_items, total_price


def add_item_to_cart(product_id, quantity=1):
    """Thêm sản phẩm vào giỏ"""
    cart = session.get('cart', {})
    if product_id in cart:
        cart[product_id] += int(quantity)
    else:
        cart[product_id] = int(quantity)

    session['cart'] = cart
    session.modified = True