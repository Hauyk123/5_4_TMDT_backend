import math
import uuid
import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from config.db_connection import get_mysql_connection, get_mongo_db


# Khởi tạo Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

import math
from flask import session, request, flash, redirect, url_for, render_template


@admin_bp.route('/dashboard')
def dashboard():
    """Trang thống kê tổng quan: Quản lý đơn, Biểu đồ, Top SP và Cảnh báo ERP"""
    user_id = session.get('user_id')
    if not user_id:
        flash('Vui lòng đăng nhập để truy cập hệ thống quản trị!', 'warning')
        return redirect(url_for('auth.login', next='/admin/dashboard'))

    page = request.args.get('page', 1, type=int)
    per_page = 10

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Kiểm tra quyền ADMIN
        cursor.execute("SELECT role, full_name FROM USERS WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user or user['role'] != 'ADMIN':
            flash('⛔ Truy cập bị từ chối! Bạn không có quyền Quản trị viên.', 'danger')
            return redirect(url_for('main.index'))

        # 2. Thống kê tổng quan KPI
        cursor.execute("SELECT SUM(total_amount) as revenue FROM ORDERS WHERE status = 'DELIVERED'")
        revenue = cursor.fetchone()['revenue'] or 0

        cursor.execute("SELECT COUNT(order_id) as total_orders FROM ORDERS")
        total_orders = cursor.fetchone()['total_orders'] or 0

        cursor.execute("SELECT COUNT(user_id) as total_users FROM USERS WHERE role = 'CUSTOMER'")
        total_users = cursor.fetchone()['total_users'] or 0

        # 3. Phân trang Đơn hàng gần đây
        total_pages = math.ceil(total_orders / per_page) if total_orders > 0 else 1
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page

        cursor.execute("""
            SELECT order_id, receiver_name, total_amount, status, created_at, payment_method
            FROM ORDERS 
            ORDER BY created_at DESC 
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        recent_orders = cursor.fetchall()

        start_page = max(1, page - 2)
        end_page = min(total_pages + 1, page + 3)
        page_range = list(range(start_page, end_page))

        # 4. Thống kê Doanh thu 7 ngày (Dành cho Chart.js)
        cursor.execute("""
            SELECT DATE(created_at) as order_date, SUM(total_amount) as daily_revenue
            FROM ORDERS 
            WHERE created_at >= DATE(NOW()) - INTERVAL 7 DAY 
              AND status NOT IN ('CANCELLED', 'RETURNED', 'REFUNDED')
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at) ASC
        """)
        revenue_records = cursor.fetchall()
        chart_revenue_labels = [record['order_date'].strftime('%d/%m') for record in revenue_records]
        chart_revenue_data = [float(record['daily_revenue']) for record in revenue_records]

        # 5. Tỉ lệ Trạng thái Đơn hàng (Dành cho Chart.js)
        cursor.execute("SELECT status, COUNT(order_id) as status_count FROM ORDERS GROUP BY status")
        status_records = cursor.fetchall()

        status_map = {
            'PENDING': 'Chờ duyệt', 'PROCESSING': 'Đang chuẩn bị',
            'SHIPPING': 'Đang giao', 'DELIVERED': 'Đã giao',
            'RETURN_REQUESTED': 'Yêu cầu hoàn trả', 'RETURNED': 'Đã hoàn kho',
            'REFUNDED': 'Đã hoàn tiền', 'CANCELLED': 'Đã hủy'
        }
        chart_status_labels = [status_map.get(r['status'], r['status']) for r in status_records]
        chart_status_data = [r['status_count'] for r in status_records]

        # 6. Cảnh báo khẩn cấp (Alerts: Hàng sắp hết & Đơn xin hoàn trả)
        cursor.execute(
            "SELECT COUNT(product_id) as low_stock_count FROM PRODUCT WHERE stock <= 5 AND (price > 0 OR price IS NOT NULL)")
        low_stock_count = cursor.fetchone()['low_stock_count'] or 0

        cursor.execute("SELECT COUNT(order_id) as return_count FROM ORDERS WHERE status = 'RETURN_REQUESTED'")
        return_request_count = cursor.fetchone()['return_count'] or 0

        # 7. Top 5 Sản phẩm Bán chạy nhất
        cursor.execute("""
            SELECT P.product_id, P.name, P.price, P.image_url, SUM(OI.quantity) as total_sold
            FROM ORDER_ITEM OI
            JOIN PRODUCT P ON OI.product_id = P.product_id
            JOIN ORDERS O ON OI.order_id = O.order_id
            WHERE O.status NOT IN ('CANCELLED', 'RETURNED', 'REFUNDED')
            GROUP BY P.product_id, P.name, P.price, P.image_url
            ORDER BY total_sold DESC
            LIMIT 5
        """)
        top_products = cursor.fetchall()

        # 8. AI Business: Đề xuất Xả hàng/Marketing (Tồn kho >= 15 nhưng bán ế)
        cursor.execute("""
            SELECT P.product_id, P.name, P.stock, P.price, P.image_url, COALESCE(SUM(OI.quantity), 0) as total_sold
            FROM PRODUCT P
            LEFT JOIN ORDER_ITEM OI ON P.product_id = OI.product_id
            WHERE P.stock >= 15 AND (P.price > 0 OR P.price IS NOT NULL)
            GROUP BY P.product_id, P.name, P.stock, P.price, P.image_url
            ORDER BY total_sold ASC, P.stock DESC
            LIMIT 5
        """)
        overstock_products = cursor.fetchall()

        # 9. AI Business: Đề xuất Nhập kho gấp (Tồn kho <= 5)
        cursor.execute("""
            SELECT product_id, name, stock, price, image_url
            FROM PRODUCT 
            WHERE stock <= 5 AND (price > 0 OR price IS NOT NULL)
            ORDER BY stock ASC
            LIMIT 5
        """)
        low_stock_list = cursor.fetchall()

        # Render và truyền toàn bộ dữ liệu xuống HTML
        return render_template('admin/dashboard.html',
                               admin_name=user['full_name'],
                               revenue=revenue,
                               total_orders=total_orders,
                               total_users=total_users,
                               recent_orders=recent_orders,
                               current_page=page,
                               total_pages=total_pages,
                               page_range=page_range,
                               chart_revenue_labels=chart_revenue_labels,
                               chart_revenue_data=chart_revenue_data,
                               chart_status_labels=chart_status_labels,
                               chart_status_data=chart_status_data,
                               low_stock_count=low_stock_count,
                               return_request_count=return_request_count,
                               top_products=top_products,
                               overstock_products=overstock_products,
                               low_stock_list=low_stock_list)
    except Exception as e:
        print(f"❌ Lỗi Admin Dashboard: {e}")
        flash('Lỗi truy xuất dữ liệu quản trị.', 'danger')
        return redirect(url_for('main.index'))
    finally:
        cursor.close()
        conn.close()
@admin_bp.route('/order/update_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    """Xử lý cập nhật trạng thái đơn hàng (Duyệt, Đã giao, Hủy đơn, Hoàn tiền) từ phía Admin"""
    user_id = session.get('user_id')
    user_role = session.get('user_role')

    if not user_id or user_role != 'ADMIN':
        flash('⛔ Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('main.index'))

    new_status = request.form.get('new_status')
    redirect_to = request.form.get('redirect_to', 'admin.manage_orders')

    # ĐÃ BỔ SUNG: Thêm các trạng thái Trả hàng / Hoàn tiền vào danh sách hợp lệ
    valid_statuses = ['PENDING', 'PROCESSING', 'SHIPPING', 'DELIVERED', 'CANCELLED', 'RETURN_REQUESTED', 'RETURNED',
                      'REFUNDED']
    if new_status not in valid_statuses:
        flash('Trạng thái không hợp lệ.', 'warning')
        return redirect(url_for(redirect_to))

    conn = get_mysql_connection()
    try:
        # VÁ LỖI TUPLE: Bắt buộc thêm dictionary=True vào đây
        with conn.cursor(dictionary=True) as cursor:

            # 1. Cập nhật trạng thái
            cursor.execute("UPDATE ORDERS SET status = %s WHERE order_id = %s", (new_status, order_id))

            # 2. Logic Hoàn kho (Giữ nguyên tư duy của bạn):
            # Nếu Admin hủy đơn, tự động hoàn trả lại số lượng tồn kho (stock) cho sản phẩm
            if new_status == 'CANCELLED':
                cursor.execute("SELECT product_id, quantity FROM ORDER_ITEM WHERE order_id = %s", (order_id,))
                items = cursor.fetchall()
                for item in items:
                    # Nhờ có dictionary=True ở trên, lúc này gọi item['quantity'] sẽ hoạt động hoàn hảo
                    cursor.execute(
                        "UPDATE PRODUCT SET stock = stock + %s WHERE product_id = %s",
                        (item['quantity'], item['product_id'])
                    )

        conn.commit()
        flash(f'✅ Đã cập nhật đơn hàng #{order_id} sang trạng thái "{new_status}"!', 'success')

    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi Admin đổi trạng thái đơn: {e}")
        flash('Có lỗi xảy ra khi cập nhật đơn hàng.', 'danger')
    finally:
        conn.close()

    return redirect(url_for(redirect_to))
@admin_bp.route('/products')
def manage_products():
    """Trang Quản lý Danh sách Sản phẩm (Có phân trang, tìm kiếm và JOIN bảng)"""
    user_id = session.get('user_id')
    user_role = session.get('user_role')

    if not user_id or user_role != 'ADMIN':
        flash('⛔ Truy cập bị từ chối!', 'danger')
        return redirect(url_for('main.index'))

    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 12

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Đếm tổng số lượng (Sử dụng JOIN để có thể tìm theo tên Danh mục)
        count_sql = """
            SELECT COUNT(P.product_id) as total 
            FROM PRODUCT P 
            LEFT JOIN CATEGORY C ON P.category_id = C.category_id
        """
        params = []
        if search_query:
            count_sql += " WHERE P.name LIKE %s OR C.name LIKE %s"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        cursor.execute(count_sql, tuple(params))
        total_products = cursor.fetchone()['total'] or 0

        total_pages = math.ceil(total_products / per_page) if total_products > 0 else 1
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page

        # 2. Kéo dữ liệu (Sử dụng LEFT JOIN lấy cột C.name và đặt bí danh là category_name)
        fetch_sql = """
            SELECT P.product_id, P.name, P.price, P.stock, P.image_url, C.name as category_name 
            FROM PRODUCT P
            LEFT JOIN CATEGORY C ON P.category_id = C.category_id
        """
        if search_query:
            fetch_sql += " WHERE P.name LIKE %s OR C.name LIKE %s"

        fetch_sql += " ORDER BY P.product_id DESC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(fetch_sql, tuple(params))
        products = cursor.fetchall()

        start_page = max(1, page - 2)
        end_page = min(total_pages + 1, page + 3)
        page_range = list(range(start_page, end_page))

        return render_template('admin/products.html',
                               products=products,
                               search_query=search_query,
                               current_page=page,
                               total_pages=total_pages,
                               page_range=page_range,
                               total_products=total_products)
    except Exception as e:
        print(f"❌ Lỗi truy xuất sản phẩm: {e}")
        flash('Lỗi tải danh sách sản phẩm.', 'danger')
        return redirect(url_for('admin.dashboard'))
    finally:
        cursor.close()
        conn.close()


# Cấu hình thư mục lưu ảnh (sẽ nằm trong app/static/uploads)
UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Tự tạo thư mục nếu chưa có


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# 1. API THÊM SẢN PHẨM MỚI
# 1. API THÊM SẢN PHẨM MỚI
@admin_bp.route('/product/add', methods=['GET', 'POST'])
def add_product():
    user_id = session.get('user_id')
    if not user_id or session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            product_id = request.form.get('product_id') or f"SP{str(uuid.uuid4().hex[:8]).upper()}"
            name = request.form.get('name')
            price = request.form.get('price')
            stock = request.form.get('stock')
            category_id = request.form.get('category_id')

            # ĐÃ BỔ SUNG: Lấy dữ liệu mô tả từ Form
            description = request.form.get('description')

            # XỬ LÝ UPLOAD ẢNH
            image_url = '/static/images/default.png'  # Ảnh mặc định nếu có lỗi
            file = request.files.get('image_file')
            if file and file.filename != '' and allowed_file(file.filename):
                # Mã hóa tên file và ghép mã uuid để không bao giờ trùng lặp
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                save_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                file.save(save_path)
                image_url = f"/static/uploads/{unique_filename}"  # Đường dẫn để lưu vào DB

            # ĐÃ BỔ SUNG: Chèn cột description vào câu lệnh SQL
            cursor.execute("""
                INSERT INTO PRODUCT (product_id, name, price, stock, category_id, description, image_url) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (product_id, name, price, stock, category_id, description, image_url))
            conn.commit()

            flash('✅ Thêm sản phẩm mới thành công!', 'success')
            return redirect(url_for('admin.manage_products'))

        cursor.execute("SELECT category_id, name FROM CATEGORY")
        categories = cursor.fetchall()
        return render_template('admin/product_form.html', categories=categories, product=None)
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi hệ thống: {e}', 'danger')
        return redirect(url_for('admin.manage_products'))
    finally:
        cursor.close()
        conn.close()


# 2. API SỬA SẢN PHẨM
@admin_bp.route('/product/edit/<product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    user_id = session.get('user_id')
    if not user_id or session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            name = request.form.get('name')
            price = request.form.get('price')
            stock = request.form.get('stock')
            category_id = request.form.get('category_id')

            # ĐÃ BỔ SUNG: Lấy dữ liệu mô tả từ Form để cập nhật
            description = request.form.get('description')

            # XỬ LÝ ẢNH KHI SỬA
            image_url = request.form.get('current_image')  # Mặc định lấy lại ảnh cũ
            file = request.files.get('image_file')
            # Nếu người dùng có chọn upload ảnh MỚI
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                save_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                file.save(save_path)
                image_url = f"/static/uploads/{unique_filename}"  # Cập nhật link mới

            # ĐÃ BỔ SUNG: Cập nhật cột description trong câu lệnh SQL
            cursor.execute("""
                UPDATE PRODUCT 
                SET name=%s, price=%s, stock=%s, category_id=%s, description=%s, image_url=%s 
                WHERE product_id=%s
            """, (name, price, stock, category_id, description, image_url, product_id))
            conn.commit()

            flash('✅ Cập nhật sản phẩm thành công!', 'success')
            return redirect(url_for('admin.manage_products'))

        cursor.execute("SELECT * FROM PRODUCT WHERE product_id=%s", (product_id,))
        product = cursor.fetchone()
        cursor.execute("SELECT category_id, name FROM CATEGORY")
        categories = cursor.fetchall()

        return render_template('admin/product_form.html', categories=categories, product=product)
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi hệ thống: {e}', 'danger')
        return redirect(url_for('admin.manage_products'))
    finally:
        cursor.close()
        conn.close()
# 3. API XÓA SẢN PHẨM
@admin_bp.route('/product/delete/<product_id>', methods=['POST'])
def delete_product(product_id):
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM PRODUCT WHERE product_id=%s", (product_id,))
        conn.commit()
        flash('🗑️ Đã xóa sản phẩm khỏi hệ thống!', 'success')
    except Exception as e:
        conn.rollback()
        flash('Không thể xóa sản phẩm này vì có thể nó đã nằm trong Đơn hàng của khách.', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin.manage_products'))


# ==========================================
# PHÂN HỆ QUẢN LÝ ĐƠN HÀNG
# ==========================================


@admin_bp.route('/orders')
def manage_orders():
    """Trang Quản lý toàn bộ Đơn hàng (Có lọc trạng thái, phân trang + Bốc hồ sơ hoàn hàng từ MongoDB)"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')  # Lọc theo trạng thái
    page = request.args.get('page', 1, type=int)
    per_page = 10

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Xây dựng câu lệnh đếm tổng số đơn
        count_sql = "SELECT COUNT(order_id) as total FROM ORDERS WHERE 1=1"
        params = []

        if search_query:
            count_sql += " AND (receiver_name LIKE %s OR order_id = %s)"
            search_pattern = f"%{search_query}%"
            order_id_search = search_query if search_query.isdigit() else 0
            params.extend([search_pattern, order_id_search])

        if status_filter:
            count_sql += " AND status = %s"
            params.append(status_filter)

        cursor.execute(count_sql, tuple(params))
        total_orders = cursor.fetchone()['total'] or 0

        # 2. Tính toán phân trang
        total_pages = math.ceil(total_orders / per_page) if total_orders > 0 else 1
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page

        # 3. Kéo danh sách đơn hàng từ MySQL
        fetch_sql = """
            SELECT order_id, receiver_name, total_amount, status, created_at, payment_method 
            FROM ORDERS WHERE 1=1
        """
        fetch_params = []
        if search_query:
            fetch_sql += " AND (receiver_name LIKE %s OR order_id = %s)"
            fetch_params.extend([search_pattern, order_id_search])
        if status_filter:
            fetch_sql += " AND status = %s"
            fetch_params.append(status_filter)

        fetch_sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        fetch_params.extend([per_page, offset])

        cursor.execute(fetch_sql, tuple(fetch_params))
        orders = cursor.fetchall()

        # 4. ĐÃ TÍCH HỢP: Sang MongoDB bốc hồ sơ minh chứng hoàn hàng đính vào đơn hàng
        mongo_db = get_mongo_db()
        if mongo_db is not None:
            col_returns = mongo_db['return_requests']
            for order in orders:
                if order['status'] == 'RETURN_REQUESTED':
                    # Tìm thông tin lưu bằng order_id trong MongoDB và đính vào object order của MySQL
                    order['return_proof'] = col_returns.find_one({"order_id": str(order['order_id'])})

        start_page = max(1, page - 2)
        end_page = min(total_pages + 1, page + 3)
        page_range = list(range(start_page, end_page))

        return render_template('admin/orders.html',
                               orders=orders,
                               search_query=search_query,
                               status_filter=status_filter,
                               current_page=page,
                               total_pages=total_pages,
                               page_range=page_range,
                               total_orders=total_orders)
    except Exception as e:
        print(f"❌ Lỗi truy xuất đơn hàng: {e}")
        flash('Lỗi tải danh sách đơn hàng.', 'danger')
        return redirect(url_for('admin.dashboard'))
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/order/detail/<int:order_id>')
def order_detail(order_id):
    """Trang xem chi tiết một hóa đơn cụ thể - Đã tích hợp bốc minh chứng hoàn hàng từ MongoDB"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Lấy thông tin chung của đơn hàng
        cursor.execute("SELECT * FROM ORDERS WHERE order_id = %s", (order_id,))
        order_info = cursor.fetchone()

        if not order_info:
            flash('Không tìm thấy hóa đơn này!', 'warning')
            return redirect(url_for('admin.manage_orders'))

        # Lấy danh sách sản phẩm trong hóa đơn đó (JOIN với bảng PRODUCT để lấy tên và ảnh)
        cursor.execute("""
            SELECT OI.quantity, OI.price_at_purchase, P.name, P.image_url, P.product_id
            FROM ORDER_ITEM OI
            JOIN PRODUCT P ON OI.product_id = P.product_id
            WHERE OI.order_id = %s
        """, (order_id,))
        order_items = cursor.fetchall()

        # --- ĐÃ BỔ SUNG: BỐC HỒ SƠ MINH CHỨNG TỪ MONGODB ---
        return_proof = None
        if order_info['status'] == 'RETURN_REQUESTED':
            mongo_db = get_mongo_db()
            if mongo_db is not None:
                col_returns = mongo_db['return_requests']
                # Thử lấy bằng cả kiểu số nguyên và kiểu chuỗi để đảm bảo không bị lệch type dữ liệu
                return_proof = col_returns.find_one({"order_id": order_id})
                if not return_proof:
                    return_proof = col_returns.find_one({"order_id": str(order_id)})

        # Truyền chính xác các biến xuống template admin/order_detail.html
        return render_template('admin/order_detail.html', order=order_info, items=order_items,
                               return_proof=return_proof)

    except Exception as e:
        print(f"❌ Lỗi truy xuất chi tiết đơn hàng: {e}")
        flash('Lỗi tải chi tiết đơn hàng.', 'danger')
        return redirect(url_for('admin.manage_orders'))
    finally:
        cursor.close()
        conn.close()
# ==========================================
# PHÂN HỆ QUẢN LÝ KHÁCH HÀNG (USERS)
# ==========================================

@admin_bp.route('/customers')
def manage_customers():
    """Trang Quản lý Tài khoản Người dùng (Có lọc trạng thái và tìm kiếm)"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()  # ĐÃ THÊM: Hứng bộ lọc trạng thái từ giao diện
    page = request.args.get('page', 1, type=int)
    per_page = 10

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Xây dựng câu lệnh SQL đếm số lượng tài khoản (Loại bỏ tài khoản ADMIN)
        count_sql = "SELECT COUNT(user_id) as total FROM users WHERE role != 'ADMIN'"
        params = []

        if search_query:
            count_sql += " AND (full_name LIKE %s OR email LIKE %s OR phone LIKE %s OR username LIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

        if status_filter:
            count_sql += " AND status = %s"
            params.append(status_filter)

        cursor.execute(count_sql, tuple(params))
        total_users = cursor.fetchone()['total'] or 0

        # 2. Tính toán phân trang chính xác
        total_pages = math.ceil(total_users / per_page) if total_users > 0 else 1
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page

        # 3. Kéo danh sách tài khoản từ bảng 'users' (ĐÃ BỔ SUNG: Lấy thêm trường 'status')
        fetch_sql = """
            SELECT user_id, username, full_name, email, phone, role, status, created_at 
            FROM users WHERE role != 'ADMIN'
        """
        fetch_params = []
        if search_query:
            fetch_sql += " AND (full_name LIKE %s OR email LIKE %s OR phone LIKE %s OR username LIKE %s)"
            fetch_params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

        if status_filter:
            fetch_sql += " AND status = %s"
            fetch_params.append(status_filter)

        fetch_sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        fetch_params.extend([per_page, offset])

        cursor.execute(fetch_sql, tuple(fetch_params))
        customers = cursor.fetchall()

        # 4. Tạo dải phân trang mượt mà
        start_page = max(1, page - 2)
        end_page = min(total_pages + 1, page + 3)
        page_range = list(range(start_page, end_page))

        # 5. ĐỂ Ý: Đã đổi tên template thành 'admin/manage_customers.html' và truyền status_filter xuống
        return render_template('admin/customers.html',
                               customers=customers,
                               search_query=search_query,
                               status_filter=status_filter,  # ĐÃ THÊM: Truyền xuống để giữ trạng thái thẻ select
                               current_page=page,
                               total_pages=total_pages,
                               page_range=page_range,
                               total_users=total_users)
    except Exception as e:
        print(f"❌ Lỗi truy xuất khách hàng: {e}")
        flash('Lỗi tải danh sách người dùng.', 'danger')
        return redirect(url_for('admin.dashboard'))
    finally:
        cursor.close()
        conn.close()

# --- 2 API MỚI BỔ SUNG VÀO BÊN DƯỚI ---

@admin_bp.route('/customer/<int:user_id>')
def view_customer(user_id):
    """Trang xem chi tiết Hồ sơ Khách hàng và Lịch sử mua hàng"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Lấy thông tin khách hàng
        cursor.execute("SELECT * FROM USERS WHERE user_id = %s", (user_id,))
        customer = cursor.fetchone()

        if not customer:
            flash('Không tìm thấy khách hàng này!', 'warning')
            return redirect(url_for('admin.manage_customers'))

        # 2. Lấy toàn bộ lịch sử đơn hàng của khách đó
        cursor.execute("""
            SELECT order_id, total_amount, status, created_at, payment_method 
            FROM ORDERS WHERE user_id = %s ORDER BY created_at DESC
        """, (user_id,))
        orders = cursor.fetchall()

        # 3. Thống kê tổng tiền khách đã chi tiêu
        cursor.execute(
            "SELECT SUM(total_amount) as total_spent FROM ORDERS WHERE user_id = %s AND status = 'DELIVERED'",
            (user_id,))
        total_spent = cursor.fetchone()['total_spent'] or 0

        return render_template('admin/customer_detail.html', customer=customer, orders=orders, total_spent=total_spent)
    except Exception as e:
        flash(f'Lỗi tải hồ sơ: {e}', 'danger')
        return redirect(url_for('admin.manage_customers'))
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/customer/delete/<int:user_id>', methods=['POST'])
def delete_customer(user_id):
    """Xóa tài khoản khách hàng"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            # Xóa giỏ hàng trước để tránh lỗi khóa ngoại
            cursor.execute("DELETE FROM CART WHERE user_id = %s", (user_id,))
            # Xóa tài khoản
            cursor.execute("DELETE FROM USERS WHERE user_id = %s", (user_id,))
        conn.commit()
        flash('🗑️ Đã xóa tài khoản khách hàng thành công!', 'success')
    except Exception as e:
        conn.rollback()
        flash(
            '⛔ Không thể xóa! Tài khoản này đang có lịch sử đơn hàng trong hệ thống. Vui lòng giữ lại để đảm bảo dữ liệu.',
            'danger')
    finally:
        conn.close()
    return redirect(url_for('admin.manage_customers'))


@admin_bp.route('/order/approve_return/<int:order_id>', methods=['POST'])
def admin_approve_return(order_id):
    """Admin duyệt yêu cầu trả hàng, chuyển trạng thái và cộng lại tồn kho"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            # 1. Kiểm tra đơn hàng có đang yêu cầu trả không
            cursor.execute("SELECT status FROM ORDERS WHERE order_id = %s", (order_id,))
            order = cursor.fetchone()

            if not order or order['status'] != 'RETURN_REQUESTED':
                flash('Đơn hàng không ở trạng thái yêu cầu trả hàng hợp lệ.', 'warning')
                return redirect(url_for('admin.manage_orders'))  # Đổi lại tên route quản lý đơn hàng của bạn

            # 2. Đổi trạng thái đơn thành ĐÃ HOÀN TRẢ
            cursor.execute("UPDATE ORDERS SET status = 'RETURNED' WHERE order_id = %s", (order_id,))

            # 3. LOGIC HOÀN KHO: Lấy danh sách sản phẩm trong đơn
            cursor.execute("SELECT product_id, quantity FROM ORDER_ITEM WHERE order_id = %s", (order_id,))
            returned_items = cursor.fetchall()

            # 4. Cộng trả lại số lượng tồn kho cho từng sản phẩm
            for item in returned_items:
                cursor.execute("""
                    UPDATE PRODUCT 
                    SET stock = stock + %s 
                    WHERE product_id = %s
                """, (item['quantity'], item['product_id']))

        conn.commit()
        flash('✅ Đã xác nhận hoàn trả hàng và tự động cộng lại tồn kho thành công!', 'success')

    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi duyệt trả hàng: {e}")
        flash('Lỗi hệ thống khi xử lý hoàn kho.', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin.manage_orders'))  # Đổi lại tên route quản lý đơn hàng của bạn




from datetime import datetime

# SỬA LẠI LUỒNG HIỂN THỊ & THÊM MỚI
@admin_bp.route('/voucher/create', methods=['GET', 'POST'])
def create_voucher():
    """Trang quản lý Voucher (Hiển thị danh sách + Xử lý thêm mới)"""
    if session.get('user_role') != 'ADMIN':
        flash('⛔ Bạn không có quyền truy cập khu vực này!', 'danger')
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    # Nếu khách truy cập trang (GET) -> Đọc danh sách voucher truyền xuống bảng
    if request.method == 'GET':
        try:
            cursor.execute("SELECT * FROM VOUCHER ORDER BY start_date DESC")
            vouchers = cursor.fetchall()
            return render_template('admin/voucher_form.html', vouchers=vouchers, current_time=datetime.now())
        finally:
            cursor.close()
            conn.close()

    # Nếu nhấn Lưu (POST) -> Xử lý thêm mới như bình thường
    code = request.form.get('code', '').strip().upper()
    usage_limit = request.form.get('usage_limit', 100, type=int)
    discount_type = request.form.get('discount_type', 'PERCENT')
    discount_value = request.form.get('discount_value', type=float)
    max_discount = request.form.get('max_discount', type=float)
    min_order_value = request.form.get('min_order_value', 0, type=float)
    end_date = request.form.get('end_date')

    if discount_type == 'FIXED': max_discount = None

    try:
        cursor.execute("SELECT code FROM VOUCHER WHERE code = %s", (code,))
        if cursor.fetchone():
            flash(f'Mã Voucher {code} đã tồn tại trong hệ thống!', 'danger')
            return redirect(url_for('admin.create_voucher'))

        voucher_id = f"VC{str(uuid.uuid4().hex[:6]).upper()}"
        cursor.execute("""
            INSERT INTO VOUCHER (voucher_id, code, discount_type, discount_value, min_order_value, max_discount, start_date, end_date, usage_limit, used_count, status)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, 0, 'ACTIVE')
        """, (voucher_id, code, discount_type, discount_value, min_order_value, max_discount, end_date, usage_limit))
        conn.commit()
        flash(f'✨ Kích hoạt thành công mã giảm giá: {code}', 'success')
    except Exception as e:
        print(f"Lỗi tạo voucher: {e}")
        flash('Lỗi hệ thống không thể tạo mã.', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.create_voucher'))


# BỔ SUNG LUỒNG CẬP NHẬT (UPDATE)
@admin_bp.route('/voucher/update', methods=['POST'])
def update_voucher():
    """Xử lý cập nhật thông tin Voucher đã có"""
    if session.get('user_role') != 'ADMIN':
        flash('⛔ Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('main.index'))

    voucher_id = request.form.get('voucher_id')
    code = request.form.get('code', '').strip().upper()
    usage_limit = request.form.get('usage_limit', type=int)
    discount_type = request.form.get('discount_type')
    discount_value = request.form.get('discount_value', type=float)
    max_discount = request.form.get('max_discount', type=float)
    min_order_value = request.form.get('min_order_value', type=float)
    end_date = request.form.get('end_date')

    if discount_type == 'FIXED': max_discount = None

    conn = get_mysql_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE VOUCHER 
            SET code=%s, usage_limit=%s, discount_type=%s, discount_value=%s, min_order_value=%s, max_discount=%s, end_date=%s
            WHERE voucher_id=%s
        """, (code, usage_limit, discount_type, discount_value, min_order_value, max_discount, end_date, voucher_id))
        conn.commit()
        flash(f'✅ Đã cập nhật thành công thông tin mã: {code}', 'success')
    except Exception as e:
        print(f"Lỗi update voucher: {e}")
        flash('Không thể cập nhật thông tin.', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.create_voucher'))


# BỔ SUNG LUỒNG XÓA (DELETE)
@admin_bp.route('/voucher/delete/<string:voucher_id>', methods=['POST'])
def delete_voucher(voucher_id):
    """Xóa bỏ mã voucher ra khỏi hệ thống"""
    if session.get('user_role') != 'ADMIN':
        flash('⛔ Bạn không có quyền thực hiện thao tác này!', 'danger')
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM VOUCHER WHERE voucher_id = %s", (voucher_id,))
        conn.commit()
        flash('🗑️ Đã xóa mã giảm giá ra khỏi hệ thống thành công.', 'success')
    except Exception as e:
        print(f"Lỗi xóa voucher: {e}")
        flash('Mã này đã phát sinh dữ liệu giao dịch đơn hàng, không thể xóa bỏ hẳn!', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.create_voucher'))


@admin_bp.route('/customer/<int:user_id>/toggle-status', methods=['POST'])
def toggle_customer_status(user_id):
    """Hàm xử lý Khóa / Mở khóa tài khoản linh hoạt - Đã sửa lỗi tên bảng thành users"""
    if session.get('user_role') != 'ADMIN':
        return redirect(url_for('main.index'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Kiểm tra trạng thái hiện tại từ bảng 'users'
        cursor.execute("SELECT username, status FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            flash('Tài khoản không tồn tại!', 'warning')
            return redirect(url_for('admin.manage_customers'))

        # 2. Thực hiện đổi trạng thái ngược lại (Nếu ACTIVE -> BANNED và ngược lại)
        new_status = 'BANNED' if user['status'] != 'BANNED' else 'ACTIVE'

        # Đã cập nhật tên bảng thành 'users'
        cursor.execute("UPDATE users SET status = %s WHERE user_id = %s", (new_status, user_id))
        conn.commit()

        msg = f"🔒 Đã khóa tài khoản thành công: {user['username']}" if new_status == 'BANNED' else f"🔓 Đã mở khóa hoạt động lại cho tài khoản: {user['username']}"
        flash(msg, 'success')
    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi khi lật trạng thái tài khoản: {e}")
        flash('Lỗi hệ thống, không thể đổi trạng thái tài khoản.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin.manage_customers'))