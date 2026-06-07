# File: app/routes/cart_routes.py
from flask import Blueprint, request, redirect, url_for, render_template, flash, jsonify
from app.controllers.cart_controller import CartController
from flask import session # Đảm bảo bạn đã import session ở đầu file
from config.db_connection import get_mysql_connection
from flask import jsonify

cart_bp = Blueprint('cart', __name__)


@cart_bp.route('/add_to_cart/<string:product_id>', methods=['POST'])
@cart_bp.route('/add_to_cart', methods=['POST'])
def add_to_cart(product_id=None):
    """Endpoint xử lý khi người dùng bấm nút Thêm vào giỏ hàng hoặc Mua ngay"""

    # 1. Bắt Product ID từ URL hoặc từ Form (tương thích ngược với cả 2 bản HTML)
    if not product_id:
        product_id = request.form.get('product_id')

    quantity = int(request.form.get('quantity', 1))

    # Bắt hành động xem khách bấm Thêm giỏ (add_cart) hay Mua ngay (buy_now)
    action = request.form.get('action')

    # Lưu vào giỏ hàng qua Controller của bạn
    if product_id:
        CartController.add_to_cart(product_id, quantity)

    # 2. XỬ LÝ LUỒNG "MUA NGAY"
    if action == 'buy_now':
        # Bỏ qua mọi xử lý AJAX, tốc biến thẳng sang trang Thanh toán
        # (Lưu ý: Bạn sửa lại 'order.checkout' cho đúng với tên hàm thanh toán của bạn nhé)
        return redirect(url_for('cart.checkout'))

    # 3. XỬ LÝ LUỒNG "THÊM VÀO GIỎ" BẰNG AJAX (Không load trang)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Tính lại tổng số lượng trong giỏ
        total_items = sum(session.get('cart', {}).values())
        return jsonify({"status": "success", "total_items": total_items})

    # 4. Fallback: Nếu trình duyệt cũ không có JS
    flash('Sản phẩm đã được thêm vào giỏ hàng thành công!', 'success')
    return redirect(request.referrer or url_for('main.index'))
@cart_bp.route('/cart')
def view_cart():
    """Endpoint hiển thị trang chi tiết giỏ hàng"""
    cart_items, total_amount = CartController.get_cart_details()
    return render_template('cart.html', cart_items=cart_items, total_amount=total_amount)


@cart_bp.route('/cart/update/<product_id>', methods=['POST'])
def update_cart(product_id):
    """Endpoint xử lý cập nhật số lượng tại trang giỏ hàng"""
    quantity = int(request.form.get('quantity', 1))
    CartController.update_quantity(product_id, quantity)
    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/cart/delete/<product_id>', methods=['POST'])
def delete_item(product_id):
    """Endpoint xử lý xóa sản phẩm tại trang giỏ hàng"""
    CartController.remove_from_cart(product_id)
    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """Trang điền thông tin giao hàng và xác nhận đơn"""
    # 1. BẮT BUỘC ĐĂNG NHẬP ĐỂ ĐẶT HÀNG
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập tài khoản để tiến hành đặt hàng!', 'warning')
        return redirect(url_for('auth.login', next='/checkout'))

    # 2. Nhận danh sách sản phẩm được tick từ trang Giỏ hàng
    selected_items = request.form.getlist('selected_items')

    # Nếu người dùng vô tình reload trang (GET request), lấy lại từ session tạm nếu có
    if request.method == 'GET':
        selected_items = session.get('temp_checkout_items', [])
    else:
        # Lưu tạm vào session để lỡ người dùng f5 không bị mất
        session['temp_checkout_items'] = selected_items

    if not selected_items:
        flash('Bạn chưa chọn sản phẩm nào để thanh toán!', 'error')
        return redirect(url_for('cart.view_cart'))

    # 3. Truy vấn thông tin các món hàng này từ MySQL
    cart = session.get('cart', {})
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        format_strings = ','.join(['%s'] * len(selected_items))
        query = f"SELECT product_id, name as title, price, image_url FROM PRODUCT WHERE product_id IN ({format_strings})"
        cursor.execute(query, tuple(selected_items))
        products = cursor.fetchall()

        checkout_items = []
        total_amount = 0.0

        for p in products:
            pid = p['product_id']
            qty = cart.get(pid, 1)  # Lấy số lượng từ Giỏ hàng
            subtotal = float(p['price']) * qty
            total_amount += subtotal

            p['quantity'] = qty
            p['subtotal'] = subtotal
            checkout_items.append(p)

        return render_template('checkout.html', checkout_items=checkout_items, total_amount=total_amount)
    finally:
        cursor.close()
        conn.close()
@cart_bp.route('/api/apply_voucher', methods=['POST'])
def apply_voucher():
    """API kiểm tra và tính toán giảm giá dựa trên mã Voucher"""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Vui lòng đăng nhập!"})

    data = request.get_json()
    code = data.get('code', '').strip().upper()
    cart_total = float(data.get('cart_total', 0))

    if not code:
        return jsonify({"status": "error", "message": "Vui lòng nhập mã giảm giá"})

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Truy vấn mã Voucher trong MySQL
        cursor.execute("""
            SELECT * FROM VOUCHER 
            WHERE code = %s 
              AND status = 'ACTIVE' 
              AND NOW() BETWEEN start_date AND end_date
        """, (code,))
        voucher = cursor.fetchone()

        if not voucher:
            return jsonify({"status": "error", "message": "Mã không hợp lệ hoặc đã hết hạn"})

        # 2. Kiểm tra điều kiện tối thiểu và số lượt sử dụng
        if voucher['used_count'] >= voucher['usage_limit']:
            return jsonify({"status": "error", "message": "Mã giảm giá đã hết lượt sử dụng"})

        if cart_total < float(voucher['min_order_value']):
            return jsonify({
                "status": "error",
                "message": f"Đơn hàng tối thiểu để áp dụng là ${voucher['min_order_value']}"
            })

        # 3. Tính toán số tiền được giảm
        discount_amount = 0.0
        if voucher['discount_type'] == 'FIXED':
            discount_amount = float(voucher['discount_value'])
        elif voucher['discount_type'] == 'PERCENT':
            discount_amount = cart_total * (float(voucher['discount_value']) / 100)
            # Giới hạn mức giảm tối đa nếu có
            if voucher['max_discount'] and discount_amount > float(voucher['max_discount']):
                discount_amount = float(voucher['max_discount'])

        # Lưu mã voucher vào session để trừ số lượng sau khi thanh toán thành công
        session['applied_voucher'] = {
            'voucher_id': voucher['voucher_id'],
            'code': voucher['code'],
            'discount_amount': round(discount_amount, 2)
        }
        session.modified = True

        return jsonify({
            "status": "success",
            "message": "Áp dụng mã thành công!",
            "discount_amount": round(discount_amount, 2)
        })

    except Exception as e:
        print(f"Lỗi API Voucher: {e}")
        return jsonify({"status": "error", "message": "Lỗi hệ thống khi áp dụng mã"})
    finally:
        cursor.close()
        conn.close()


@cart_bp.route('/place_order', methods=['POST'])
def place_order():
    """Logic xử lý ghi đơn hàng xuống Database (Chốt đơn) - Đã tích hợp GHN, MoMo & Voucher"""

    # 1. KIỂM TRA QUYỀN TRUY CẬP (USER THẬT)
    user_id = session.get('user_id')
    if not user_id:
        flash('Phiên đăng nhập đã hết hạn hoặc bạn chưa đăng nhập. Vui lòng thử lại!', 'warning')
        return redirect(url_for('auth.login', next='/cart'))

    # 2. LẤY THÔNG TIN TỪ FORM
    receiver_name = request.form.get('receiver_name')
    receiver_phone = request.form.get('receiver_phone')
    payment_method = request.form.get('payment_method', 'COD')

    address_detail = request.form.get('address_detail', '')
    ward_name = request.form.get('ward_name', '')
    district_name = request.form.get('district_name', '')
    province_name = request.form.get('province_name', '')

    # --- BẮT PHÍ VẬN CHUYỂN TỪ GHN GỬI LÊN ---
    try:
        shipping_fee = float(request.form.get('shipping_fee', 0))
    except ValueError:
        shipping_fee = 0.0

    shipping_address = f"{address_detail}, {ward_name}, {district_name}, {province_name}"

    selected_items = session.get('temp_checkout_items', [])
    cart = session.get('cart', {})

    if not selected_items or not receiver_name or not address_detail or not province_name:
        flash('Lỗi dữ liệu đặt hàng. Vui lòng kiểm tra lại thông tin địa chỉ!', 'error')
        return redirect(url_for('cart.view_cart'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Lấy giá tiền chuẩn từ MySQL để tránh user sửa HTML can thiệp giá
        format_strings = ','.join(['%s'] * len(selected_items))
        cursor.execute(f"SELECT product_id, price FROM PRODUCT WHERE product_id IN ({format_strings})",
                       tuple(selected_items))
        products = cursor.fetchall()

        # Tính tiền hàng
        product_total_amount = sum([float(p['price']) * cart.get(p['product_id'], 1) for p in products])

        # --- ĐÃ BỔ SUNG: XỬ LÝ VOUCHER TỪ SESSION ---
        applied_voucher = session.get('applied_voucher')
        discount_amount = 0.0
        voucher_id = None

        if applied_voucher:
            discount_amount = float(applied_voucher['discount_amount'])
            voucher_id = applied_voucher['voucher_id']

        # --- TỔNG TIỀN CUỐI = TIỀN HÀNG + PHÍ SHIP - TIỀN VOUCHER ---
        final_total_amount = product_total_amount + shipping_fee - discount_amount
        if final_total_amount < 0:
            final_total_amount = 0.0

        # 3. GHI VÀO BẢNG ORDERS (Đã thêm biến discount_amount)
        order_query = """
            INSERT INTO ORDERS (user_id, total_amount, shipping_fee, discount_amount, payment_method, shipping_address, receiver_name, receiver_phone, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
        """
        cursor.execute(order_query,
                       (user_id, final_total_amount, shipping_fee, discount_amount, payment_method, shipping_address,
                        receiver_name,
                        receiver_phone))
        order_id = cursor.lastrowid

        # 4. GHI TỪNG MÓN VÀO BẢNG ORDER_ITEM VÀ TRỪ TỒN KHO
        item_query = """
            INSERT INTO ORDER_ITEM (order_id, product_id, quantity, price_at_purchase) 
            VALUES (%s, %s, %s, %s)
        """
        for p in products:
            pid = p['product_id']
            qty = cart.get(pid, 1)
            price = p['price']

            cursor.execute(item_query, (order_id, pid, qty, price))

            # Trừ số lượng tồn kho của sản phẩm (Bảo vệ dữ liệu không bị âm)
            cursor.execute("UPDATE PRODUCT SET stock = stock - %s WHERE product_id = %s", (qty, pid))

            # Xóa mặt hàng này khỏi Giỏ (Session)
            if pid in cart:
                cart.pop(pid)

        # --- ĐÃ BỔ SUNG: CẬP NHẬT SỐ LƯỢT SỬ DỤNG VOUCHER ---
        if voucher_id:
            cursor.execute("UPDATE VOUCHER SET used_count = used_count + 1 WHERE voucher_id = %s", (voucher_id,))

        # 5. DỌN DẸP GIỎ HÀNG TRONG DATABASE
        cursor.execute("SELECT cart_id FROM CART WHERE user_id = %s", (user_id,))
        cart_row = cursor.fetchone()
        if cart_row:
            cart_id = cart_row['cart_id']
            # Xóa đúng những mặt hàng đã chốt đơn khỏi bảng CART_ITEM
            delete_params = [cart_id] + selected_items
            delete_query = f"DELETE FROM CART_ITEM WHERE cart_id = %s AND product_id IN ({format_strings})"
            cursor.execute(delete_query, tuple(delete_params))

        # 6. HOÀN TẤT GIAO DỊCH DATABASE & SESSION
        conn.commit()
        session['cart'] = cart
        session.pop('temp_checkout_items', None)
        session.pop('applied_voucher', None)  # Dọn dẹp session voucher sau khi dùng
        session.modified = True

        # 7. RẼ NHÁNH THANH TOÁN MOMO / COD
        if payment_method == 'MOMO':
            return redirect(url_for('order.pay_with_momo', order_id=order_id))
        else:
            flash(f'🎉 Đặt hàng thành công! Mã đơn hàng của bạn là #{order_id}.', 'success')
            return redirect(url_for('order.view_orders'))

    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi khi chốt đơn: {e}")
        flash('Có lỗi hệ thống khi xử lý đơn hàng. Vui lòng thử lại!', 'error')
        return redirect(url_for('cart.view_cart'))
    finally:
        cursor.close()
        conn.close()


@cart_bp.route('/process_order', methods=['POST'])
def process_order():
    """Hàm chốt đơn hàng: Áp dụng Transaction & Pessimistic Locking chống bán âm kho"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # Nhận thông tin giao hàng từ form
    receiver_name = request.form.get('receiver_name')
    phone = request.form.get('phone')
    address = request.form.get('address')
    payment_method = request.form.get('payment_method', 'COD')

    checkout_items = session.get('final_checkout_items')
    total_amount = session.get('final_total_amount')

    if not checkout_items:
        flash("Dữ liệu đơn hàng không hợp lệ, vui lòng thử lại.", "danger")
        return redirect(url_for('cart.view_cart'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. BẮT ĐẦU GIAO DỊCH BẢO VỆ
        conn.start_transaction()

        # 2. KIỂM TRA VÀ KHÓA KHO TỪNG MÓN HÀNG (Khóa bi quan)
        for item in checkout_items:
            cursor.execute("SELECT stock FROM PRODUCT WHERE product_id = %s FOR UPDATE", (item['product_id'],))
            product_db = cursor.fetchone()

            if not product_db or product_db['stock'] < item['quantity']:
                conn.rollback()  # Hủy ngay lập tức nếu có món hết hàng
                flash(f"Rất tiếc! Món hàng {item['title']} vừa bị khách khác mua hết.", "danger")
                return redirect(url_for('cart.view_cart'))

            # 3. TRỪ KHO AN TOÀN
            cursor.execute("UPDATE PRODUCT SET stock = stock - %s WHERE product_id = %s",
                           (item['quantity'], item['product_id']))

        # 4. TẠO ĐƠN HÀNG MỚI VÀO BẢNG ORDERS
        cursor.execute("""
            INSERT INTO ORDERS (user_id, receiver_name, phone, address, total_amount, payment_method, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', NOW())
        """, (session['user_id'], receiver_name, phone, address, total_amount, payment_method))

        order_id = cursor.lastrowid  # Lấy mã đơn hàng vừa tạo

        # 5. LƯU CHI TIẾT ĐƠN HÀNG VÀO BẢNG ORDER_ITEM
        for item in checkout_items:
            cursor.execute("""
                INSERT INTO ORDER_ITEM (order_id, product_id, quantity, price)
                VALUES (%s, %s, %s, %s)
            """, (order_id, item['product_id'], item['quantity'], item['price']))

        # 6. THÀNH CÔNG: LƯU TOÀN BỘ VÀ NHẢ KHÓA DATABASE
        conn.commit()

        # Dọn dẹp giỏ hàng
        session.pop('cart', None)
        session.pop('final_checkout_items', None)

        flash("🎉 Chúc mừng bạn đã đặt hàng thành công!", "success")
        # return redirect(url_for('main.order_success')) # Trỏ về trang báo thành công của bạn
        return redirect(url_for('main.index'))

    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi Race Condition hoặc Database: {e}")
        flash("Giao dịch bị gián đoạn, vui lòng thử lại.", "danger")
        return redirect(url_for('cart.view_cart'))
    finally:
        cursor.close()
        conn.close()