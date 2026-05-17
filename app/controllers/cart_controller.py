# File: app/controllers/cart_controller.py
from flask import session
from config.db_connection import get_mysql_connection


class CartController:
    @staticmethod
    def _get_or_create_db_cart(cursor, user_id):
        """Hàm helper nội bộ: Lấy cart_id của user, nếu chưa có thì tạo mới"""
        cursor.execute("SELECT cart_id FROM CART WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row:
            return row['cart_id']
        cursor.execute("INSERT INTO CART (user_id) VALUES (%s)", (user_id,))
        return cursor.lastrowid

    @staticmethod
    def add_to_cart(product_id, quantity):
        """Thêm sản phẩm vào Session và đồng bộ ngay xuống MySQL nếu đã đăng nhập"""
        # 1. Cập nhật Session (Áp dụng cho cả Khách và User)
        if 'cart' not in session:
            session['cart'] = {}

        cart = session['cart']
        if product_id in cart:
            cart[product_id] += quantity
        else:
            cart[product_id] = quantity

        session['cart'] = cart
        session.modified = True

        # 2. Cập nhật MySQL (Chỉ áp dụng khi đã đăng nhập)
        user_id = session.get('user_id')
        if user_id:
            conn = get_mysql_connection()
            if conn:
                try:
                    cursor = conn.cursor(dictionary=True)
                    cart_id = CartController._get_or_create_db_cart(cursor, user_id)

                    cursor.execute(
                        "SELECT cart_item_id, quantity FROM CART_ITEM WHERE cart_id = %s AND product_id = %s",
                        (cart_id, product_id)
                    )
                    item = cursor.fetchone()

                    if item:
                        # Cộng dồn trên DB
                        new_qty = item['quantity'] + quantity
                        cursor.execute(
                            "UPDATE CART_ITEM SET quantity = %s WHERE cart_item_id = %s",
                            (new_qty, item['cart_item_id'])
                        )
                    else:
                        # Thêm mới vào DB
                        cursor.execute(
                            "INSERT INTO CART_ITEM (cart_id, product_id, quantity) VALUES (%s, %s, %s)",
                            (cart_id, product_id, quantity)
                        )
                    conn.commit()
                except Exception as e:
                    print(f"❌ Lỗi đồng bộ DB (add_to_cart): {e}")
                finally:
                    cursor.close()
                    conn.close()
        return True

    @staticmethod
    def get_cart_details():
        """Lấy thông tin chi tiết các sản phẩm đang có trong giỏ hàng từ MySQL"""
        cart = session.get('cart', {})
        if not cart:
            return [], 0.0

        product_ids = list(cart.keys())
        conn = get_mysql_connection()
        if not conn:
            return [], 0.0

        cursor = conn.cursor(dictionary=True)
        try:
            format_strings = ','.join(['%s'] * len(product_ids))
            query = f"""
                SELECT product_id, name as title, price, image_url 
                FROM PRODUCT 
                WHERE product_id IN ({format_strings})
            """
            cursor.execute(query, tuple(product_ids))
            products = cursor.fetchall()

            cart_items = []
            total_amount = 0.0

            for p in products:
                pid = p['product_id']
                qty = cart.get(pid, 1)
                subtotal = float(p['price']) * qty
                total_amount += subtotal

                p['quantity'] = qty
                p['subtotal'] = subtotal
                p['_id'] = pid
                p['images'] = [p['image_url']]
                cart_items.append(p)

            return cart_items, total_amount
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_quantity(product_id, quantity):
        """Cập nhật số lượng trong Session và đồng bộ xuống MySQL"""
        if 'cart' in session and product_id in session['cart']:
            # 1. Cập nhật Session
            if quantity <= 0:
                session['cart'].pop(product_id)
            else:
                session['cart'][product_id] = quantity
            session.modified = True

            # 2. Cập nhật MySQL
            user_id = session.get('user_id')
            if user_id:
                conn = get_mysql_connection()
                if conn:
                    try:
                        cursor = conn.cursor(dictionary=True)
                        cart_id = CartController._get_or_create_db_cart(cursor, user_id)

                        if quantity <= 0:
                            cursor.execute(
                                "DELETE FROM CART_ITEM WHERE cart_id = %s AND product_id = %s",
                                (cart_id, product_id)
                            )
                        else:
                            # Đảm bảo record có tồn tại trước khi update
                            cursor.execute(
                                "SELECT cart_item_id FROM CART_ITEM WHERE cart_id = %s AND product_id = %s",
                                (cart_id, product_id)
                            )
                            if cursor.fetchone():
                                cursor.execute(
                                    "UPDATE CART_ITEM SET quantity = %s WHERE cart_id = %s AND product_id = %s",
                                    (quantity, cart_id, product_id)
                                )
                            else:
                                cursor.execute(
                                    "INSERT INTO CART_ITEM (cart_id, product_id, quantity) VALUES (%s, %s, %s)",
                                    (cart_id, product_id, quantity)
                                )
                        conn.commit()
                    except Exception as e:
                        print(f"❌ Lỗi đồng bộ DB (update_quantity): {e}")
                    finally:
                        cursor.close()
                        conn.close()
            return True
        return False

    @staticmethod
    def remove_from_cart(product_id):
        """Xóa mặt hàng khỏi Session và đồng bộ lệnh xóa xuống MySQL"""
        if 'cart' in session and product_id in session['cart']:
            # 1. Xóa trong Session
            session['cart'].pop(product_id)
            session.modified = True

            # 2. Xóa trong MySQL
            user_id = session.get('user_id')
            if user_id:
                conn = get_mysql_connection()
                if conn:
                    try:
                        cursor = conn.cursor(dictionary=True)
                        cart_id = CartController._get_or_create_db_cart(cursor, user_id)
                        cursor.execute(
                            "DELETE FROM CART_ITEM WHERE cart_id = %s AND product_id = %s",
                            (cart_id, product_id)
                        )
                        conn.commit()
                    except Exception as e:
                        print(f"❌ Lỗi đồng bộ DB (remove_from_cart): {e}")
                    finally:
                        cursor.close()
                        conn.close()
            return True
        return False