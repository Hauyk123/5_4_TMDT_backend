# File: app/routes/auth_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.controllers.auth_controller import verify_login, register_user
from config.db_connection import get_mysql_connection

auth_bp = Blueprint('auth', __name__)


def sync_cart_after_login(user_id):
    """Thuật toán đồng bộ và gộp giỏ hàng từ Session vào MySQL DB"""
    session_cart = session.get('cart', {})
    conn = get_mysql_connection()
    if not conn:
        return

    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Kiểm tra hoặc tạo mới bảng CART cho user này
        cursor.execute("SELECT cart_id FROM CART WHERE user_id = %s", (user_id,))
        cart_row = cursor.fetchone()
        if not cart_row:
            cursor.execute("INSERT INTO CART (user_id) VALUES (%s)", (user_id,))
            cart_id = cursor.lastrowid
        else:
            cart_id = cart_row['cart_id']

        # 2. Nếu session có hàng (khách vãng lai đã thêm đồ), tiến hành gộp vào DB
        if session_cart:
            for product_id, qty in session_cart.items():
                cursor.execute(
                    "SELECT cart_item_id, quantity FROM CART_ITEM WHERE cart_id = %s AND product_id = %s",
                    (cart_id, product_id)
                )
                item_row = cursor.fetchone()
                if item_row:
                    # Đã có trong DB -> Cộng dồn số lượng (giới hạn tối đa 10)
                    new_qty = min(item_row['quantity'] + qty, 10)
                    cursor.execute(
                        "UPDATE CART_ITEM SET quantity = %s WHERE cart_item_id = %s",
                        (new_qty, item_row['cart_item_id'])
                    )
                else:
                    # Chưa có trong DB -> Thêm mới bản ghi
                    cursor.execute(
                        "INSERT INTO CART_ITEM (cart_id, product_id, quantity) VALUES (%s, %s, %s)",
                        (cart_id, product_id, qty)
                    )
            conn.commit()

        # 3. Đồng bộ ngược từ DB về Session để Navbar hiển thị đúng tổng số lượng
        cursor.execute("SELECT product_id, quantity FROM CART_ITEM WHERE cart_id = %s", (cart_id,))
        db_items = cursor.fetchall()

        updated_session_cart = {}
        for item in db_items:
            updated_session_cart[item['product_id']] = item['quantity']

        session['cart'] = updated_session_cart
        session.modified = True
    except Exception as e:
        print(f"❌ Lỗi đồng bộ giỏ hàng: {e}")
    finally:
        cursor.close()
        conn.close()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Bắt tham số 'next' trên URL
    next_url = request.args.get('next') or request.form.get('next')

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        success, result = verify_login(email, password)
        if success:
            user = result

            # ĐÃ TÍCH HỢP: Kiểm tra xem tài khoản có đang bị Admin khóa (BANNED) hay không
            # Hỗ trợ check cả dạng chữ hoa lẫn chữ thường phòng trường hợp database lưu hoa/thường
            user_status = user.get('status', 'ACTIVE')
            if user_status and str(user_status).upper() == 'BANNED':
                flash('⛔ Tài khoản của bạn đã bị khóa do vi phạm chính sách hệ thống! Vui lòng liên hệ Admin.',
                      'danger')
                return render_template('login.html', next=next_url)

            user_id = user.get('user_id', user.get('id'))
            user_name = user.get('full_name', user.get('username'))
            user_role = user.get('role', 'CUSTOMER')  # Lấy role, mặc định là CUSTOMER

            # Lưu thông tin vào phiên làm việc (Session)
            session['user_id'] = user_id
            session['user_name'] = user_name
            session['user_role'] = user_role  # Lưu thêm role vào session

            # Đồng bộ giỏ hàng
            sync_cart_after_login(user_id)

            flash(f"Chào mừng {user_name} trở lại!", "success")

            # BẺ LÁI ĐIỀU HƯỚNG TẠI ĐÂY
            if user_role == 'ADMIN':
                # Nếu là Admin, bất chấp có tham số next hay không, ưu tiên đưa về trang quản trị
                return redirect(url_for('admin.dashboard'))
            else:
                # Nếu là Khách hàng, đưa về trang bị chặn (ví dụ /checkout) hoặc trang chủ
                return redirect(next_url or url_for('main.index'))
        else:
            error_msg = result
            flash(error_msg, "danger")

    return render_template('login.html', next=next_url)
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Gom dữ liệu từ form
        user_data = {
            'username': request.form.get('username'),
            'email': request.form.get('email'),
            'password': request.form.get('password'),
            'full_name': request.form.get('full_name'),
            'phone': request.form.get('phone')
        }

        success, message = register_user(user_data)
        if success:
            flash(message, "success")
            return redirect(url_for('auth.login'))
        else:
            flash(message, "danger")

    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()  # Xóa toàn bộ giỏ hàng và trạng thái đăng nhập
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('main.index'))


@auth_bp.route('/profile')
def profile():
    """Trang hiển thị thông tin hồ sơ cá nhân"""
    user_id = session.get('user_id')

    # Chặn nếu chưa đăng nhập
    if not user_id:
        flash("Vui lòng đăng nhập để xem thông tin tài khoản.", "warning")
        return redirect(url_for('auth.login', next='/profile'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Lấy thông tin user
        cursor.execute("""
            SELECT username, full_name, email, phone, role, created_at 
            FROM USERS 
            WHERE user_id = %s
        """, (user_id,))
        user_info = cursor.fetchone()

        # 2. Lấy 5 đơn hàng mới nhất
        cursor.execute("""
            SELECT order_id, total_amount, status, created_at 
            FROM ORDERS 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 5
        """, (user_id,))
        recent_orders = cursor.fetchall()

        # 3. LẤY SẢN PHẨM GỢI Ý (Giả lập bằng cách lấy 4 sản phẩm ngẫu nhiên)
        cursor.execute("""
            SELECT product_id, name, price, image_url 
            FROM PRODUCT 
            WHERE status = 'ACTIVE'
            ORDER BY RAND() 
            LIMIT 4
        """)
        recommended_products = cursor.fetchall()

        # Truyền cả 3 biến sang cho giao diện
        return render_template('profile.html', user=user_info, recent_orders=recent_orders, recommended_products=recommended_products)
    except Exception as e:
        print(f"Lỗi tải hồ sơ: {e}")
        flash("Có lỗi xảy ra khi tải thông tin hồ sơ.", "danger")
        return redirect(url_for('main.index'))
    finally:
        cursor.close()
        conn.close()