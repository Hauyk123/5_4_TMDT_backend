# File: app/routes/cart_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.controllers.cart_controller import get_cart_items, add_item_to_cart

cart_bp = Blueprint('cart', __name__)


@cart_bp.route('/cart')
def view_cart():
    cart_items, total_items, total_price = get_cart_items()
    return render_template('cart.html', cart_items=cart_items, total_price=total_price, total_items=total_items)


@cart_bp.route('/cart/add/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    quantity = request.form.get('quantity', 1)
    add_item_to_cart(product_id, quantity)
    flash("Đã thêm sản phẩm vào giỏ hàng!", "success")
    # Quay lại trang trước đó hoặc về trang chủ
    return redirect(request.referrer or url_for('main.index'))


@cart_bp.route('/checkout')
def checkout():
    # Bắt buộc đăng nhập mới được thanh toán
    if 'user_id' not in session:
        flash("Vui lòng đăng nhập để tiến hành thanh toán.", "warning")
        return redirect(url_for('auth.login'))

    cart_items, total_items, total_price = get_cart_items()
    if total_items == 0:
        flash("Giỏ hàng của bạn đang trống.", "warning")
        return redirect(url_for('main.index'))

    return render_template('checkout.html', cart_items=cart_items, total_price=total_price)