import os
import uuid
import hmac
import hashlib
from werkzeug.utils import secure_filename
from datetime import datetime
from config.db_connection import get_mysql_connection, get_mongo_db

# Thêm cấu hình thư mục lưu ảnh upload (Nếu dự án của bạn có cấu hình khác thì đổi lại đường dẫn nhé)
UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads', 'returns')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

from flask import Blueprint, render_template, session, redirect, url_for, flash, request
import requests
import math
# Tạo Blueprint riêng cho Quản lý Đơn hàng
order_bp = Blueprint('order', __name__)

import math


@order_bp.route('/orders')
def view_orders():
    """Trang hiển thị danh sách đơn hàng đã đặt của CHÍNH NGƯỜI DÙNG ĐÓ (Có phân trang & bộ lọc trạng thái)"""
    user_id = session.get('user_id')

    # Bảo mật: Nếu chưa đăng nhập thì đá về trang login
    if not user_id:
        flash('Vui lòng đăng nhập để xem lịch sử đơn hàng của bạn.', 'warning')
        return redirect(url_for('auth.login', next='/orders'))

    # 1. LẤY SỐ TRANG VÀ TRẠNG THÁI CẦN LỌC TỪ URL
    page = request.args.get('page', 1, type=int)
    per_page = 5  # Số lượng đơn hàng hiển thị trên một trang
    status_filter = request.args.get('status', '').strip()

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 2. XÂY DỰNG CÂU LỆNH ĐẾM TỔNG SỐ ĐƠN (CÓ ĐIỀU KIỆN LỌC)
        count_query = "SELECT COUNT(*) as total FROM ORDERS WHERE user_id = %s"
        count_params = [user_id]

        if status_filter:
            count_query += " AND status = %s"
            count_params.append(status_filter)

        cursor.execute(count_query, tuple(count_params))
        total_orders = cursor.fetchone()['total']

        # Tính toán tổng số trang dựa trên kết quả lọc
        total_pages = math.ceil(total_orders / per_page)
        if total_pages == 0:
            total_pages = 1

        # Đảm bảo biến page nằm trong phạm vi hợp lệ
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1

        offset = (page - 1) * per_page

        # 3. TRUY VẤN DỮ LIỆU ĐƠN HÀNG CÓ PHÂN TRANG VÀ BỘ LỌC
        data_query = """
            SELECT order_id, total_amount, status, payment_method, shipping_address, created_at 
            FROM ORDERS 
            WHERE user_id = %s
        """
        data_params = [user_id]

        if status_filter:
            data_query += " AND status = %s"
            data_params.append(status_filter)

        data_query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        data_params.extend([per_page, offset])

        cursor.execute(data_query, tuple(data_params))
        orders = cursor.fetchall()

        # 4. TRUY VẤN SẢN PHẨM VÀ GÁN VÀO KHÓA KHÔNG TRÙNG LẶP 'order_items'
        for order in orders:
            cursor.execute("""
                SELECT oi.product_id, oi.quantity, p.price, p.name as product_name, p.image_url
                FROM ORDER_ITEM oi
                JOIN PRODUCT p ON oi.product_id = p.product_id
                WHERE oi.order_id = %s
            """, (order['order_id'],))
            order['order_items'] = cursor.fetchall()

        page_range = range(1, total_pages + 1)

        # Truyền thêm biến status_filter sang HTML để giữ trạng thái đã chọn trên Dropdown
        return render_template('orders.html',
                               orders=orders,
                               current_page=page,
                               total_pages=total_pages,
                               page_range=page_range,
                               status_filter=status_filter)

    except Exception as e:
        print(f"Lỗi truy vấn đơn hàng: {e}")
        flash('Không thể tải lịch sử đơn hàng.', 'error')
        return redirect(url_for('main.index'))
    finally:
        cursor.close()
        conn.close()
        conn.close()
@order_bp.route('/cancel/<int:order_id>', methods=['POST'])
def customer_cancel_order(order_id):
    """Xử lý khách hàng tự chọn Hủy đơn hàng từ trang cá nhân"""
    user_id = session.get('user_id')
    if not user_id:
        flash('Vui lòng đăng nhập để thực hiện thao tác.', 'warning')
        return redirect(url_for('auth.login'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # BẢO MẬT: Phải kiểm tra đúng đơn hàng của user đó và trạng thái bắt buộc phải là PENDING
        cursor.execute(
            "SELECT status FROM ORDERS WHERE order_id = %s AND user_id = %s",
            (order_id, user_id)
        )
        order = cursor.fetchone()

        if not order:
            flash('Không tìm thấy đơn hàng hợp lệ.', 'danger')
        elif order['status'] != 'PENDING':
            flash('⛔ Bạn không thể hủy đơn hàng này do hệ thống đã duyệt hoặc đang vận chuyển!', 'warning')
        else:
            # Tiến hành hủy đơn
            cursor.execute("UPDATE ORDERS SET status = 'CANCELLED' WHERE order_id = %s", (order_id,))

            # Hoàn trả số lượng tồn kho sản phẩm cho hệ thống
            cursor.execute("SELECT product_id, quantity FROM ORDER_ITEM WHERE order_id = %s", (order_id,))
            items = cursor.fetchall()
            for item in items:
                cursor.execute(
                    "UPDATE PRODUCT SET stock = stock + %s WHERE product_id = %s",
                    (item['quantity'], item['product_id'])
                )

            conn.commit()
            flash('🗑️ Đã hủy đơn hàng thành công theo yêu cầu của bạn.', 'success')
    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi khách hủy đơn: {e}")
        flash('Có lỗi xảy ra khi thực hiện hủy đơn.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('order.view_orders'))


@order_bp.route('/checkout/momo/<int:order_id>')
def pay_with_momo(order_id):
    """API: Gửi thông tin lên MoMo và lấy Link thanh toán"""
    user_id = session.get('user_id')
    if not user_id:
        flash("Vui lòng đăng nhập để thanh toán.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Lấy thông tin đơn hàng
        cursor.execute("SELECT total_amount FROM ORDERS WHERE order_id = %s AND user_id = %s AND status = 'PENDING'",
                       (order_id, user_id))
        order = cursor.fetchone()

        if not order:
            flash("Đơn hàng không hợp lệ hoặc đã được xử lý.", "danger")
            return redirect(url_for('order.view_orders'))

        # Quy đổi USD sang VNĐ (Giả sử 1 USD = 25,000 VNĐ)
        amount_vnd = int(float(order['total_amount']) * 25000)

        # 2. Tạo bản ghi trạng thái PENDING trong bảng PAYMENT_TRANSACTION
        cursor.execute("""
            INSERT INTO PAYMENT_TRANSACTION (order_id, provider, amount, status) 
            VALUES (%s, 'MOMO', %s, 'PENDING')
        """, (order_id, amount_vnd))
        conn.commit()

        # 3. CHUẨN BỊ PAYLOAD GỬI LÊN MOMO
        endpoint = "https://test-payment.momo.vn/v2/gateway/api/create"

        # BỘ KEY TEST CHUẨN ĐÃ ĐƯỢC CẬP NHẬT
        partnerCode = "MOMOBKUN20180529"
        accessKey = "klm05TvNBzhg7h7j"
        secretKey = "at67qH6mk8w5Y1nAyMoYKMWACiEi2bsa"

        # Bỏ dấu # đi để tránh lỗi mã hóa ký tự đặc biệt
        orderInfo = f"Thanh toan don hang Amazon AI {order_id}"

        redirectUrl = "http://127.0.0.1:5000/payment/momo_return"
        ipnUrl = "https://momo.vn"  # Thủ thuật lách luật localhost

        momo_order_id = f"{order_id}_{uuid.uuid4().hex[:6]}"
        requestId = str(uuid.uuid4())
        requestType = "captureWallet"
        extraData = ""

        # Chuỗi rawSignature yêu cầu amount là Chuỗi (String)
        amount_str = str(amount_vnd)
        rawSignature = f"accessKey={accessKey}&amount={amount_str}&extraData={extraData}&ipnUrl={ipnUrl}&orderId={momo_order_id}&orderInfo={orderInfo}&partnerCode={partnerCode}&redirectUrl={redirectUrl}&requestId={requestId}&requestType={requestType}"
        signature = hmac.new(secretKey.encode('utf-8'), rawSignature.encode('utf-8'), hashlib.sha256).hexdigest()

        # Trong cục data gửi đi (JSON), amount BẮT BUỘC phải là Số nguyên (Integer)
        data = {
            'partnerCode': partnerCode,
            'partnerName': "Amazon AI Test Store",
            'storeId': "MomoTestStore",
            'requestId': requestId,
            'amount': amount_vnd,  # <--- TRUYỀN SỐ NGUYÊN
            'orderId': momo_order_id,
            'orderInfo': orderInfo,
            'redirectUrl': redirectUrl,
            'ipnUrl': ipnUrl,
            'lang': 'vi',
            'extraData': extraData,
            'requestType': requestType,
            'signature': signature
        }

        response = requests.post(endpoint, json=data)
        result = response.json()

        # In ra console để debug nếu có lỗi
        print("======== PHẢN HỒI TỪ MOMO ========")
        print(result)
        print("==================================")

        # 6. Nhận Link thanh toán và chuyển hướng khách
        if result.get('resultCode') == 0:
            return redirect(result['payUrl'])
        else:
            flash(f"Lỗi khởi tạo MoMo: {result.get('message')}", "danger")
            return redirect(url_for('order.view_orders'))

    except Exception as e:
        conn.rollback()
        print(f"Lỗi API MoMo: {e}")
        flash('Lỗi kết nối cổng thanh toán.', 'danger')
        return redirect(url_for('order.view_orders'))
    finally:
        cursor.close()
        conn.close()
def momo_return():
    """API: Đón khách trở về từ trang thanh toán MoMo"""
    # Lấy mã lỗi từ MoMo trả về (0 là thành công, khác 0 là thất bại/hủy)
    resultCode = request.args.get('resultCode')
    momo_order_id = request.args.get('orderId')

    # Tách mã đơn hàng gốc của chúng ta ra (Vì lúc nãy ta ghép thêm UUID)
    order_id = momo_order_id.split('_')[0] if momo_order_id else None

    if not order_id:
        return redirect(url_for('order.view_orders'))

    conn = get_mysql_connection()
    cursor = conn.cursor()
    try:
        if str(resultCode) == '0':
            # THANH TOÁN THÀNH CÔNG
            cursor.execute("UPDATE PAYMENT_TRANSACTION SET status = 'SUCCESS' WHERE order_id = %s", (order_id,))
            cursor.execute("UPDATE ORDERS SET payment_method = 'MOMO', status = 'PROCESSING' WHERE order_id = %s",
                           (order_id,))
            conn.commit()
            flash('💖 Thanh toán qua ví MoMo thành công! Chúng tôi đang chuẩn bị hàng cho bạn.', 'success')
        else:
            # THANH TOÁN THẤT BẠI HOẶC HỦY
            cursor.execute("UPDATE PAYMENT_TRANSACTION SET status = 'FAILED' WHERE order_id = %s", (order_id,))
            conn.commit()
            flash('Giao dịch MoMo bị hủy hoặc thất bại.', 'danger')

    except Exception as e:
        conn.rollback()
        print(f"Lỗi update DB sau khi MoMo trả về: {e}")
        flash('Lỗi cập nhật trạng thái đơn hàng.', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('order.view_orders'))


@order_bp.route('/order/<string:order_id>/request_return', methods=['POST'])
def customer_request_return(order_id):
    """Xử lý yêu cầu trả hàng từ khách, lưu file vào static và thông tin vào MongoDB"""
    user_id = session.get('user_id')
    if not user_id:
        flash('Vui lòng đăng nhập!', 'warning')
        return redirect(url_for('auth.login'))

    reason = request.form.get('reason')
    description = request.form.get('description')
    file = request.files.get('proof_file')

    if not file or file.filename == '':
        flash('Vui lòng tải lên ảnh hoặc video minh chứng tình trạng sản phẩm!', 'warning')
        return redirect(url_for('order.view_orders'))

    try:
        # 1. Xử lý lưu File minh chứng vào static/uploads/returns/
        filename = secure_filename(f"{order_id}_{int(datetime.now().timestamp())}_{file.filename}")
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        # Đường dẫn tương đối để hiển thị thẻ <img src="..."> trên giao diện HTML
        relative_web_path = f"/static/uploads/returns/{filename}"

        # 2. GHI THÔNG TIN CHI TIẾT HOÀN HÀNG VÀO MONGODB
        mongo_db = get_mongo_db()
        if mongo_db is not None:
            col_returns = mongo_db['return_requests']
            col_returns.update_one(
                {"order_id": order_id},
                {"$set": {
                    "order_id": order_id,
                    "user_id": user_id,
                    "reason": reason,
                    "description": description,
                    "proof_url": relative_web_path,
                    "file_type": "video" if "video" in file.content_type else "image",
                    "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M')
                }},
                upsert=True
            )

        # 3. CẬP NHẬT TRẠNG THÁI ĐƠN HÀNG SANG 'RETURN_REQUESTED' BÊN MYSQL
        mysql_conn = get_mysql_connection()
        with mysql_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE ORDERS 
                SET status = 'RETURN_REQUESTED' 
                WHERE order_id = %s AND user_id = %s
            """, (order_id, user_id))
        mysql_conn.commit()
        mysql_conn.close()

        flash('✅ Gửi yêu cầu hoàn hàng thành công! Vui lòng chờ Admin thẩm định chứng cứ.', 'success')
    except Exception as e:
        print(f"❌ Lỗi xử lý hoàn hàng: {e}")
        flash('Có lỗi xảy ra trong quá trình xử lý hồ sơ hoàn hàng.', 'danger')

    return redirect(url_for('order.view_orders'))

