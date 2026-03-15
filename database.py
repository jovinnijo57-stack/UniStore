import sqlite3
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "unistore.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            college TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'Bronze',
            total_spent REAL DEFAULT 0.0,
            referral_code TEXT,
            referred_by TEXT,
            is_banned BOOLEAN DEFAULT 0,
            is_vip BOOLEAN DEFAULT 0,
            wallet_balance REAL DEFAULT 0.0,
            avatar TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            items TEXT NOT NULL, -- JSON string
            total REAL NOT NULL,
            status TEXT DEFAULT 'Pending',
            method TEXT NOT NULL,
            date TEXT NOT NULL,
            timestamp REAL NOT NULL,
            collection_attempts INTEGER DEFAULT 0,
            is_ready BOOLEAN DEFAULT 0,
            notification TEXT,
            pickup_time TEXT,
            token INTEGER DEFAULT 0,
            is_archived BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
        ''')

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN token INTEGER DEFAULT 0")
        except:
            pass

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN is_archived BOOLEAN DEFAULT 0")
        except:
            pass

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY,
            discount_type TEXT NOT NULL,
            value REAL NOT NULL,
            min_spend REAL DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            expiry_date TEXT,
            max_uses INTEGER DEFAULT -1
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_email TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'Open',
            priority TEXT DEFAULT 'Medium',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_coupons (
            user_email TEXT,
            coupon_code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_email, coupon_code),
            FOREIGN KEY (user_email) REFERENCES users (email),
            FOREIGN KEY (coupon_code) REFERENCES coupons (code)
        )
        ''')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Database initialization error: ", e)
        return False


def create_user(name, email, password, college=None, referred_by_code=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (name, email, password, college) VALUES (?, ?, ?, ?)",
                        (name, email, hashed_password, college))
        user_id = cursor.lastrowid
        
        # Generate unique referral code: UNI-<first3 of name><user_id><random2>
        import random, string
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
        referral_code = f"UNI-{name[:3].upper()}{user_id}{random_part}"
        
        cursor.execute("INSERT INTO user_profiles (user_id, referral_code) VALUES (?, ?)", (user_id, referral_code))
        
        # Process referral if a code was provided
        if referred_by_code:
            cursor.execute("""
                SELECT up.user_id, u.email FROM user_profiles up
                JOIN users u ON u.id = up.user_id
                WHERE up.referral_code = ?
            """, (referred_by_code,))
            referrer = cursor.fetchone()
            if referrer and referrer['email'] != email:
                # Store who referred this user
                cursor.execute("UPDATE user_profiles SET referred_by = ? WHERE user_id = ?",
                               (referred_by_code, user_id))
                # Award 100 bonus points to the referrer
                cursor.execute("UPDATE user_profiles SET points = points + 100 WHERE user_id = ?",
                               (referrer['user_id'],))
                # Award 50 bonus points to the new user (referee)
                cursor.execute("UPDATE user_profiles SET points = points + 50 WHERE user_id = ?",
                               (user_id,))
        
        conn.commit()
        conn.close()
        return {"success": True, "message": "User created successfully"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "An account with this email already exists"}
    except Exception as e:
        print("Error creating user: ", e)
        return {"success": False, "message": str(e)}


def verify_user(email, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        return {"success": True, "user": dict(user)}
    return {"success": False, "message": "Invalid email or password"}


def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return dict(user)
    return None


def save_order(order_data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Serialize items to JSON if it's a list
        if isinstance(order_data.get('items'), list):
            items_json = json.dumps(order_data['items'])
        else:
            items_json = order_data.get('items')

        user_email = order_data.get('user_email') or order_data.get('user')

        cursor.execute('''
            INSERT OR REPLACE INTO orders 
            (id, user_email, items, total, status, method, date, timestamp, collection_attempts, is_ready, notification, pickup_time, razorpay_order_id, payment_id, payment_ref, token) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_data.get('id'),
            user_email,
            items_json,
            order_data.get('total'),
            order_data.get('status'),
            order_data.get('method'),
            order_data.get('date'),
            order_data.get('timestamp'),
            int(order_data.get('collection_attempts', 0)),
            order_data.get('is_ready'),
            order_data.get('notification'),
            order_data.get('pickup_time'),
            order_data.get('razorpay_order_id'),
            order_data.get('payment_id'),
            order_data.get('payment_ref'),
            order_data.get('token', 0)
        ))

        # Update loyalty points if order is Paid or Delivered
        if order_data.get('status') in ('Paid', 'Delivered'):
            points_earned = int(order_data.get('total', 0)) // 10
            # user_profiles uses user_id, so we need to look up the user first
            cursor.execute("SELECT id FROM users WHERE email = ?", (user_email,))
            user_row = cursor.fetchone()
            if user_row:
                uid = user_row['id']
                cursor.execute('''
                    UPDATE user_profiles 
                    SET points = points + ?, 
                        total_spent = total_spent + ? 
                    WHERE user_id = ?
                ''', (points_earned, order_data.get('total'), uid))

                # Check and update tier
                cursor.execute("SELECT points FROM user_profiles WHERE user_id = ?", (uid,))
                row = cursor.fetchone()
                if row:
                    pts = row['points']
                    if pts >= 3000:
                        new_tier = 'Platinum'
                    elif pts >= 1500:
                        new_tier = 'Gold'
                    elif pts >= 500:
                        new_tier = 'Silver'
                    else:
                        new_tier = 'Bronze'
                    cursor.execute("UPDATE user_profiles SET tier = ? WHERE user_id = ?",
                                   (new_tier, uid))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error saving order: ", e)
        return False


def get_order_by_id(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    if order:
        order_dict = dict(order)
        order_dict['items'] = json.loads(order_dict['items'])
        return order_dict
    return None


def get_order_by_razorpay_id(razorpay_order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE razorpay_order_id = ?", (razorpay_order_id,))
    order = cursor.fetchone()
    conn.close()
    if order:
        order_dict = dict(order)
        order_dict['items'] = json.loads(order_dict['items'])
        return order_dict
    return None


def update_order_status(order_id, status, is_ready=None, collection_attempts=None, pickup_time=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check current status to avoid double-crediting
        cursor.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        old_status = row['status'] if row else None
        
        updates = ['status = ?']
        params = [status]

        if is_ready is not None:
            updates.append('is_ready = ?')
            params.append(is_ready)

        if collection_attempts is not None:
            updates.append('collection_attempts = ?')
            params.append(collection_attempts)

        if pickup_time is not None:
            updates.append('pickup_time = ?')
            params.append(pickup_time)

        query = 'UPDATE orders SET ' + ', '.join(updates) + ' WHERE id = ?'
        params.append(order_id)

        cursor.execute(query, tuple(params))

        # Update user's points and total spent only if transitioning to Delivered for the first time
        if status == 'Delivered' and old_status != 'Delivered':
            cursor.execute("SELECT user_email, total FROM orders WHERE id = ?", (order_id,))
            order_row = cursor.fetchone()
            if order_row:
                user_email = order_row['user_email']
                total = float(order_row['total'] or 0)
                points_earned = int(total) // 10

                # Get user_id
                cursor.execute("SELECT id FROM users WHERE email = ?", (user_email,))
                user_res = cursor.fetchone()
                if user_res:
                    uid = user_res['id']
                    cursor.execute("""
                        UPDATE user_profiles 
                        SET points = points + ?, 
                            total_spent = total_spent + ? 
                        WHERE user_id = ?
                    """, (points_earned, total, uid))
                    
                    # Update Tier
                    cursor.execute("SELECT points FROM user_profiles WHERE user_id = ?", (uid,))
                    prof_row = cursor.fetchone()
                    if prof_row:
                        pts = prof_row['points']
                        if pts >= 3000: new_tier = 'Platinum'
                        elif pts >= 1500: new_tier = 'Gold'
                        elif pts >= 500: new_tier = 'Silver'
                        else: new_tier = 'Bronze'
                        cursor.execute("UPDATE user_profiles SET tier = ? WHERE user_id = ?", (new_tier, uid))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error updating order status: ", e)
        return False


def delete_order_db(order_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Soft delete: mark as archived instead of physically deleting
        cursor.execute("UPDATE orders SET is_archived = 1 WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error archiving order: ", e)
        return False


def get_all_orders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.*, u.college as user_college, u.name as user_name
        FROM orders o
        LEFT JOIN users u ON o.user_email = u.email
        ORDER BY o.timestamp DESC
    ''')
    orders = cursor.fetchall()
    conn.close()
    result = []
    for o in orders:
        o_dict = dict(o)
        o_dict['items'] = json.loads(o_dict['items'])
        result.append(o_dict)
    return result


def create_coupon(code, discount_type, value, min_spend=0, expiry_date=None, max_uses=-1):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO coupons (code, discount_type, value, min_spend, expiry_date, max_uses) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (code, discount_type, value, min_spend, expiry_date, max_uses))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error creating coupon: ", e)
        return False


def get_coupon(code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM coupons WHERE code = ? AND active = 1", (code,))
    coupon = cursor.fetchone()
    conn.close()
    if coupon:
        return dict(coupon)
    return None


def get_all_coupons():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM coupons")
    coupons = cursor.fetchall()
    conn.close()
    return [dict(c) for c in coupons]


def delete_coupon(code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM coupons WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error deleting coupon: ", e)
        return False


def toggle_coupon_status(code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE coupons SET active = NOT active WHERE code = ?", (code,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error toggling coupon status: ", e)
        return False


def update_coupon(code, discount_type, value, min_spend, expiry_date, max_uses):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE coupons 
            SET discount_type = ?, value = ?, min_spend = ?, expiry_date = ?, max_uses = ?
            WHERE code = ?
        ''', (discount_type, value, min_spend, expiry_date, max_uses, code))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error updating coupon: ", e)
        return False


def has_user_used_coupon(email, code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_coupons WHERE user_email = ? AND coupon_code = ?", (email, code))
    used = cursor.fetchone() is not None
    conn.close()
    return used


def record_coupon_usage(email, code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_coupons (user_email, coupon_code) VALUES (?, ?)", (email, code))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error recording coupon usage: ", e)
        return False


def add_review(product_id, user_email, rating, comment):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reviews (product_id, user_email, rating, comment) 
            VALUES (?, ?, ?, ?)
        ''', (product_id, user_email, rating, comment))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error adding review: ", e)
        return False


def get_product_reviews(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, u.name as user_name 
        FROM reviews r 
        JOIN users u ON r.user_email = u.email 
        WHERE r.product_id = ? 
        ORDER BY r.created_at DESC
    ''', (product_id,))
    reviews = cursor.fetchall()
    conn.close()
    return [dict(r) for r in reviews]


def get_user_stats(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT up.points, up.tier, up.total_spent, up.wallet_balance,
               up.referral_code, up.referred_by
        FROM user_profiles up 
        JOIN users u ON u.id = up.user_id 
        WHERE u.email = ?
    """, (email,))
    profile = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as count FROM orders WHERE user_email = ?", (email,))
    order_count = cursor.fetchone()
    
    # Count how many people this user has referred
    referral_count = 0
    if profile and profile['referral_code']:
        cursor.execute("SELECT COUNT(*) as count FROM user_profiles WHERE referred_by = ?",
                       (profile['referral_code'],))
        ref_row = cursor.fetchone()
        referral_count = ref_row['count'] if ref_row else 0
    
    conn.close()
    if profile:
        return {
            'points': profile['points'],
            'tier': profile['tier'],
            'total_spent': profile['total_spent'],
            'wallet_balance': profile['wallet_balance'],
            'total_orders': order_count['count'] if order_count else 0,
            'referral_code': profile['referral_code'] or '',
            'referred_by': profile['referred_by'] or '',
            'referral_count': referral_count
        }
    return None


def get_user_orders(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE user_email = ? ORDER BY timestamp DESC", (email,))
    orders = cursor.fetchall()
    conn.close()
    result = []
    for o in orders:
        o_dict = dict(o)
        o_dict['items'] = json.loads(o_dict['items'])
        result.append(o_dict)
    return result


def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, college, created_at FROM users")
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]


def update_user_password(email, new_password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_password, email))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error updating password: ", e)
        return False

def get_max_token():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(token) FROM orders")
        result = cursor.fetchone()[0]
        conn.close()
        # If result is None or 0 (default), start at 100
        if result is not None:
            result = int(result)
        return result if (result is not None and result > 0) else 100
    except Exception as e:
        print("Error getting max token: ", e)
        return 100

def get_user_active_token(email):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM orders WHERE user_email = ? AND status NOT IN ('Delivered', 'Cancelled') ORDER BY id DESC LIMIT 1", (email,))
        result = cursor.fetchone()
        conn.close()
        return int(result[0]) if result and result[0] is not None else None
    except Exception as e:
        print("Error checking user active token: ", e)
        return None


def update_wallet_balance(email, new_balance):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_profiles 
            SET wallet_balance = ? 
            WHERE user_id = (SELECT id FROM users WHERE email = ?)
        """, (new_balance, email))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating wallet: {e}")
        return False
