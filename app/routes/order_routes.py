from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template
from app.controllers.auth_controller import get_mysql_connection
from app.utils.decorators import login_required

order_bp = Blueprint('order', __name__)


@order_bp.route('/api/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    data = request.json
    user_id = session['user_id']
    product_id = data['product_id']
    quantity = data.get('quantity', 1)

    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Tìm hoặc tạo Cart cho User
            cursor.execute("SELECT id FROM carts WHERE user_id = %s", (user_id,))
            cart = cursor.fetchone()
            if not cart:
                cursor.execute("INSERT INTO carts (user_id) VALUES (%s)", (user_id,))
                cart_id = cursor.lastrowid
            else:
                cart_id = cart['id']

            # 2. Thêm sản phẩm vào cart_items
            sql = "INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE quantity = quantity + %s"
            cursor.execute(sql, (cart_id, product_id, quantity, quantity))
        conn.commit()
        return jsonify({"status": "success", "message": "Đã thêm vào giỏ hàng"})
    finally:
        conn.close()


@order_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    user_id = session['user_id']
    address = request.form.get('address')

    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Lấy dữ liệu giỏ hàng
            cursor.execute("""
                SELECT ci.*, p.price FROM cart_items ci 
                JOIN carts c ON ci.cart_id = c.id 
                JOIN products p ON ci.product_id = p.id 
                WHERE c.user_id = %s""", (user_id,))
            items = cursor.fetchall()

            if not items:
                flash("Giỏ hàng của bạn đang trống!", "warning")
                return redirect(url_for('main.index'))

            total_amount = sum(i['quantity'] * i['price'] for i in items)

            # 2. Tạo đơn hàng (Orders)
            cursor.execute(
                "INSERT INTO orders (user_id, shipping_address, total_amount, status) VALUES (%s, %s, %s, 'pending')",
                (user_id, address, total_amount))
            order_id = cursor.lastrowid

            # 3. Chuyển item sang Order_Items
            for item in items:
                cursor.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
                    (order_id, item['product_id'], item['quantity'], item['price']))

            # 4. Xóa giỏ hàng sau khi chốt đơn
            cursor.execute("DELETE FROM cart_items WHERE cart_id = (SELECT id FROM carts WHERE user_id = %s)",
                           (user_id,))

        conn.commit()
        flash(f"Đặt hàng thành công! Mã đơn: #ORD-{order_id}", "success")
        return render_template('payment_new (1).html', order_id=order_id, total=total_amount)
    except Exception as e:
        conn.rollback()
        flash(f"Lỗi đặt hàng: {str(e)}", "danger")
        return redirect(url_for('main.index'))
    finally:
        conn.close()