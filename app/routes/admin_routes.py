from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from app.controllers.auth_controller import get_mysql_connection
from app.utils.decorators import admin_required
from datetime import datetime, timedelta
admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin/dashboard')
@admin_required
def dashboard():
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Thống kê tổng quan
            cursor.execute(
                "SELECT SUM(total_amount) as revenue, COUNT(id) as total_orders FROM orders WHERE status != 'cancelled'")
            stats = cursor.fetchone()

            cursor.execute("SELECT COUNT(id) as total_users FROM users WHERE role = 'customer'")
            user_count = cursor.fetchone()

            # 2. Lấy 5 đơn hàng mới nhất
            cursor.execute("""
                SELECT o.id, u.full_name, o.total_amount, o.status, o.created_at 
                FROM orders o JOIN users u ON o.user_id = u.id 
                ORDER BY o.created_at DESC LIMIT 5
            """)
            recent_orders = cursor.fetchall()

            # 3. Dữ liệu biểu đồ doanh thu 7 ngày gần nhất (Ví dụ)
            # Trong thực tế bạn sẽ viết SQL GROUP BY date
            chart_data = {
                "labels": ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"],
                "values": [1200000, 1900000, 3000000, 5000000, 2300000, 7000000, 9000000]
            }

        return render_template('admin_dashboard.html',
                               stats=stats,
                               user_count=user_count,
                               recent_orders=recent_orders,
                               chart_data=chart_data)
    finally:
        conn.close()
# --- QUẢN LÝ SẢN PHẨM ---
@admin_bp.route('/admin/products')
@admin_required
def manage_products():
    conn = get_mysql_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT p.*, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id = c.id")
        products = cursor.fetchall()
    conn.close()
    return render_template('admin_product.html', products=products)

@admin_bp.route('/api/admin/products', methods=['POST'])
@admin_required
def add_product():
    data = request.form
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO products (name, category_id, brand, price, description) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (data['name'], data['category_id'], data['brand'], data['price'], data['description']))
        conn.commit()
        flash("Thêm sản phẩm thành công!", "success")
    finally:
        conn.close()
    return redirect(url_for('admin.manage_products'))

@admin_bp.route('/api/admin/products/<int:id>', methods=['DELETE'])
@admin_required
def delete_product(id):
    conn = get_mysql_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM products WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Đã xóa sản phẩm"})


# --- QUẢN LÝ ĐƠN HÀNG ---
@admin_bp.route('/admin/orders')
@admin_required
def manage_orders():
    """Trang quản lý toàn bộ đơn hàng của hệ thống"""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # Truy vấn lấy đơn hàng và thông tin khách hàng tương ứng
            sql = """
                SELECT o.id, o.total_amount, o.status, o.created_at, 
                       u.full_name, u.phone
                FROM orders o 
                JOIN users u ON o.user_id = u.id 
                ORDER BY o.created_at DESC
            """
            cursor.execute(sql)
            orders = cursor.fetchall()

        # Render ra file admin_orders.html mà bạn đã thiết kế
        return render_template('admin_orders.html', orders=orders)
    except Exception as e:
        flash(f"Lỗi tải danh sách đơn hàng: {str(e)}", "danger")
        return redirect(url_for('admin.dashboard'))
    finally:
        if conn:
            conn.close()


# --- CẬP NHẬT TRẠNG THÁI & XEM CHI TIẾT ĐƠN HÀNG ---

@admin_bp.route('/api/admin/orders/<int:id>/status', methods=['POST'])
@admin_required
def update_order_status(id):
    """API Cập nhật trạng thái đơn hàng"""
    data = request.json
    new_status = data.get('status')

    valid_statuses = ['pending', 'confirmed', 'shipping', 'delivered', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({"status": "error", "message": "Trạng thái không hợp lệ!"}), 400

    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, id))
        conn.commit()
        return jsonify({"status": "success", "message": f"Đã chuyển đơn #{id} sang: {new_status}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/admin/orders/<int:id>', methods=['GET'])
@admin_required
def get_order_details(id):
    """API Lấy thông tin chi tiết của 1 đơn hàng để hiển thị Popup (Modal)"""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Lấy thông tin chung của đơn
            cursor.execute("""
                SELECT o.*, u.full_name, u.phone, u.email 
                FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = %s
            """, (id,))
            order = cursor.fetchone()

            if not order:
                return jsonify({"status": "error", "message": "Không tìm thấy đơn hàng"}), 404

            # 2. Lấy danh sách sản phẩm trong đơn
            cursor.execute("""
                SELECT oi.quantity, oi.unit_price, p.name 
                FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = %s
            """, (id,))
            items = cursor.fetchall()

            # Đóng gói dữ liệu trả về Frontend
            order['created_at'] = order['created_at'].strftime('%d/%m/%Y %H:%M')
            order['items'] = items
            return jsonify({"status": "success", "data": order})
    finally:
        conn.close()
# --- QUẢN LÝ VOUCHER ---
@admin_bp.route('/api/admin/vouchers', methods=['POST'])
@admin_required
def add_voucher():
    data = request.json
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO vouchers (code, discount_type, discount_value, expired_at) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (data['code'], data['type'], data['value'], data['expiry']))
        conn.commit()
        return jsonify({"status": "success"})
    finally:
        conn.close()