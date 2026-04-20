# File: app/routes/auth_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.controllers.auth_controller import verify_login, register_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        success, result = verify_login(email, password)
        if success:
            user = result
            # Lưu thông tin vào phiên làm việc (Session)
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = user['role']

            flash(f"Chào mừng {user['full_name']} trở lại!", "success")

            # --- ĐIỀU HƯỚNG DỰA TRÊN QUYỀN (ROLE) ---
            if user['role'] == 'admin':
                # Nếu là admin, đẩy thẳng vào trang Dashboard
                return redirect(url_for('admin.dashboard'))
            else:
                # Nếu là khách hàng, đẩy về trang chủ mua sắm
                return redirect(url_for('main.index'))

        else:
            error_msg = result
            flash(error_msg, "danger")

    return render_template('login.html')


@auth_bp.route('/register', methods=['POST'])
def register():
    """Xử lý luồng đăng ký tài khoản mới từ Form"""
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password')

    success, message = register_user(full_name, email, password)
    if success:
        flash(message, "success")
        # Đăng ký xong chuyển hướng về trang đăng nhập để người dùng tự đăng nhập
        return redirect(url_for('auth.login'))
    else:
        flash(message, "danger")
        return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
def logout():
    session.clear()  # Xóa toàn bộ giỏ hàng, thông tin user và role khi đăng xuất
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for('main.index'))