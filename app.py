from flask import Flask, jsonify, g, render_template, request, session, redirect, url_for, send_from_directory
from functools import wraps
import os
import sys
import requests

# Ensure the project root is in the Python path so local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
import json
try:
    import razorpay
except ImportError:
    print("\nERROR: 'razorpay' library is missing.")
    print("Please run: pip install -r requirements.txt\n")
    # We re-raise the error so the app stops, but user saw the message
    raise
from database import (
    init_database, create_user, verify_user, get_user_by_email, 
    get_order_by_id, update_order_status, get_all_orders,
    get_all_users, update_user_password,
    get_coupon, record_coupon_usage, get_user_active_token,
    get_db_connection, get_user_stats, get_user_orders,
    delete_coupon, update_coupon, has_user_used_coupon, 
    get_max_token, add_review, get_product_reviews, create_coupon, get_all_coupons,
    update_wallet_balance
)

# Global Token Management
TOKEN_COUNTER = 100
try:
    TOKEN_COUNTER = get_max_token()
    print(f"Token Counter Initialized: {TOKEN_COUNTER}")
except:
    pass

def get_next_token():
    global TOKEN_COUNTER
    TOKEN_COUNTER += 1
    return TOKEN_COUNTER

def get_token_for_user(user_email):
    """Reuse active token if exists, else generate new one"""
    # 1. Check DB for active order token
    active_token = get_user_active_token(user_email)
    if active_token:
        return active_token
    
    # 2. Check Memory PRINT_JOBS for active/pending job token
    # Active = status not 'Completed'
    for job in reversed(PRINT_JOBS):
        if job['user'] == user_email and job['status'] != 'Completed':
            if 'token' in job and job['token']:
                return job['token']

    # 3. New token
    return get_next_token()
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time

# Email Configuration (Placeholder - User must update this!)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "unistore153@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "bfqp ipxb kfsq teps")

def send_notification_email(recipient_email, order_id, status_msg):
    """Send email notification to user"""
    if "your-email" in SENDER_EMAIL and "unistore" not in SENDER_EMAIL:
         # print(f"By-passing email for {recipient_email}: Config not set.")
         return False
        
    subject = f"UniStore Order Update: {order_id}"
    body = f"""
    Hello,
    
    Update for your order {order_id}:
    {status_msg}
    
    Please check your dashboard for more details.
    
    Thank you,
    UniStore Team
    """
    
    return send_email(recipient_email, subject, body)

def refund_to_wallet(order):
    """Refund order amount to user's wallet if paid via Razorpay or Wallet"""
    try:
        method = order.get('method', '')
        if method in ('Razorpay', 'Wallet'):
            user_email = order.get('user_email') or order.get('user')
            amount = float(order.get('total', 0))
            order_id = order.get('id', 'N/A')
            if user_email and amount > 0:
                if user_email not in USER_PROFILES:
                    USER_PROFILES[user_email] = {}
                current_bal = USER_PROFILES[user_email].get('wallet_balance', 0.0)
                new_bal = current_bal + amount
                USER_PROFILES[user_email]['wallet_balance'] = new_bal
                update_wallet_balance(user_email, new_bal)
                print(f"Refunded ₹{amount} to {user_email}'s wallet (was {method}). New balance: ₹{new_bal}")
                
                # Extract user name from email (part before @)
                user_name = user_email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
                
                # Send refund email notification
                try:
                    subject = f"UniStore Order #{order_id} – Cancellation & Wallet Refund"
                    body = f"""Hello {user_name},

Your order #{order_id} has been successfully cancelled.

The paid amount of ₹{amount:.2f} has been credited to your wallet. You can use this balance for your next purchase.

If you did not request this cancellation or need assistance, please contact support.

Thank you for using UniStore."""
                    send_email(user_email, subject, body)
                except Exception as email_err:
                    print(f"Refund email error: {email_err}")
                    
                add_audit_log("Wallet Refund", user_email, f"Refunded ₹{amount} for cancelled order {order_id}")
                return True
    except Exception as e:
        print(f"Refund error: {e}")
    return False

def auto_handle_timeout(order_id):
    """Background task to handle order timeout after 1 minute (60 seconds)"""
    # Wait 60 seconds (1 minute collection window)
    time.sleep(60)
    
    # Check current status
    order = get_order_by_id(order_id)
    if not order: 
        print(f"Error: Order {order_id} not found during timeout check")
        return
    
    print(f"Timeout check for {order_id}: current status is '{order['status']}', attempts: {order.get('collection_attempts')}")
    
    # Logic: If still 'Ready for Collection', it means the user missed the window
    if order['status'] == 'Ready for Collection':
        # Check attempts
        current_attempts = order.get('collection_attempts', 0)
        
        # Determine new status based on attempts
        if current_attempts >= 2:
            new_status = "Cancelled"
            notification = "Order cancelled automatically after 2 missed collection windows."
        else:
            new_status = "Pending" # Revert to Pending for one more re-assignment
            notification = f"Collection attempt {current_attempts} missed. Order can be re-assigned ONE more time."
        
        # Update Database
        update_result = update_order_status(order_id, new_status, is_ready=False)
        print(f"Updated status of {order_id} to '{new_status}' (Attempt {current_attempts}). Result: {update_result}")
    
        # Update Memory (ORDER list)
        for o in ORDERS:
            if o['id'] == order_id:
                o['status'] = new_status
                o['is_ready'] = False
                o['notification'] = notification
                break
        
        # Refund if cancelled
        if new_status == "Cancelled":
            refund_to_wallet(order)
                
        # Send Email notification
        send_notification_email(order['user_email'], order_id, notification)
    elif order['status'] == 'Scheduled':
        # This shouldn't happen if everything is synced, but if it's still 'Scheduled',
        # it might mean the window hasn't effectively started or status didn't update.
        print(f"Warning: Order {order_id} is still in 'Scheduled' state at timeout. No action taken.")

def process_scheduled_pickup(order_id, pickup_time_str, current_attempts, is_reassignment):
    """Background task: Wait until pickup_time, then trigger collection window"""
    try:
        # Import timezone explicitly inside function to stay clean
        from datetime import timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        
        # Get Current API / Server time but force it to look like India Local Time 
        current_ist_time = datetime.now(IST).replace(tzinfo=None)

        # 1. Parse Date and Time provided by Frontend (which is assuming India Time)
        try:
            # New format: "YYYY-MM-DD HH:MM"
            target_dt = datetime.strptime(pickup_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            # Fallback for old format: "Today, HH:MM"
            clean_time = pickup_time_str.replace("Today, ", "").strip()
            time_obj = datetime.strptime(clean_time, "%H:%M")
            target_dt = current_ist_time.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
        
        # 2. Calculate true seconds between now and target time
        # Both target_dt and current_ist_time are naive, representing India standard time
        sleep_seconds = (target_dt - current_ist_time).total_seconds()
        
        if sleep_seconds > 0:
             time.sleep(sleep_seconds)

        # 3. Trigger "Ready" State in DB
        update_order_status(order_id, "Ready for Collection", is_ready=True)
        
        # Update Memory
        notification_msg = f"COLLECTION WINDOW START! Attempt {current_attempts}/2. 1 minute remaining."
        for o in ORDERS:
            if o['id'] == order_id:
                o['status'] = "Ready for Collection"
                o['is_ready'] = True
                o['notification'] = notification_msg
                break
        
        # 4. Trigger the 1-minute window timeout
        auto_handle_timeout(order_id)

    except Exception as e:
        print(f"Scheduling thread error for {order_id}: {e}")

app = Flask(__name__)
app.secret_key = 'super-secret-unistore-key'

# Session Configuration
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True


# Initialize database on startup
print("Initializing database...")
if init_database():
    print("✓ Database ready")
else:
    print("⚠ Database initialization failed - check your MySQL connection")


# ==============================
# Razorpay Configuration
# ==============================
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    print("⚠️ RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET not set. Payment features will fail.")

# Initialize Razorpay Client
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ==============================
# File Serving (For Staff)
# ==============================
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if 'staff' not in session:
        return "Unauthorized", 403
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ==============================
# Auth Decorator
# ==============================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def send_email(to_email, subject, message):
    """Universal email sender with Brevo API attempt and SMTP fallback"""
    
    # 1. Try Brevo API first if configured
    api_key = os.environ.get("BREVO_API_KEY")
    if api_key:
        try:
            url = "https://api.brevo.com/v3/smtp/email"
            payload = {
                "sender": {"name": "UniStore", "email": SENDER_EMAIL},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": message
            }
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": api_key
            }
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code in (200, 201):
                print(f"✅ [Brevo API] Email sent to {to_email}")
                return True
            else:
                print(f"⚠️ [Brevo API] Failed (Status {response.status_code}). Trying SMTP fallback...")
        except Exception as e:
            print(f"⚠️ [Brevo API] Connection error: {e}. Trying SMTP fallback...")

    # 2. Fallback to Gmail SMTP
    try:
        if not SENDER_PASSWORD or "your-generated-app-password" in SENDER_PASSWORD:
            print("❌ [SMTP] Configuration error: Credentials missing.")
            return False

        msg = MIMEMultipart()
        msg['From'] = f"UniStore <{SENDER_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))

        # Standard Gmail SMTP connection (Port 587 + TLS)
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.set_debuglevel(0)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ [SMTP] Email sent to {to_email} successfully!")
        return True
    except Exception as e:
        print(f"❌ [SMTP] Error sending email: {e}")
        return False

# Mock Data
PRODUCTS = [
    {"id": 1, "name": "Premium Notebook (200 pgs)", "price": 40.00, "cost_price": 25.0, "category": "Stationery", "image": "https://encrypted-tbn3.gstatic.com/shopping?q=tbn:ANd9GcQvbH1F4cd1pxaVasyHLf0Ph2OznuBpI4JGenrSHSqVYtEbPeWcgUaXIrQ7l3XjnERkI0vcmBIMNOeS0LqVvscb8wMZ6qFu", "stock": 50, "description": "High-quality 200-page notebook with premium ivory paper, perfect for notes and sketches."},
    {"id": 2, "name": "Ballpoint Pen (Blue)", "price": 5.00, "cost_price": 2.0, "category": "Stationery", "image": "https://encrypted-tbn3.gstatic.com/shopping?q=tbn:ANd9GcSmTYwvxtE1p_hnATRtrGq0rZQaSQ4DlOW5wbYrIdVpKRyD8eM8KBpdIKyKWKpfMGjY9CMqb564aE321-TNRTYQ6PO5Opu_DRQ1OAi_2i4PoHaES9nr8xaoTw", "stock": 100, "description": "Smooth-writing blue ballpoint pen with a comfortable grip for long writing sessions."},
    {"id": 3, "name": "A4 Size Paper (500 Sheets)", "price": 350.00, "cost_price": 250.0, "category": "Stationery", "image": "https://encrypted-tbn3.gstatic.com/shopping?q=tbn:ANd9GcR1W05ymEb5xwAUQC8s9g5cay0PHDx4SA8dusoEkww1q1rjSjP-k3VEzWxSA61tNVzuOf1W37X6GyPKSjAEq45nLElu8vMzBg", "stock": 40, "description": "Standard 80GSM A4 white paper, ideal for laser and inkjet printers. Pack of 500 sheets."},
    {"id": 4, "name": "Scientific Calculator", "price": 450.00, "cost_price": 300.0, "category": "Electronics", "image": "https://encrypted-tbn1.gstatic.com/shopping?q=tbn:ANd9GcQE4OVnu0r50sggoc9gOrx8nFymppbOZsPkqyNqHuMplOG5CCPFpT7wu11FjKRFUMgmptrl807zJOSI2qesK4lK1I6yo6PQJEQsR8OjNBYuUUeOOrpP20G_", "stock": 10, "description": "Advanced scientific calculator with over 240 functions. Essential for engineering and math students."},
    {"id": 5, "name": " Highlighters", "price": 85.00, "cost_price": 50.0, "category": "Stationery", "image": "https://encrypted-tbn2.gstatic.com/shopping?q=tbn:ANd9GcSPCWPa-U5XsFUCjF8k5WmYpjl3G93raP9RBM8aAwndL1rpBe4B6M2B_JVnv9Wu-o7VdoakxJ0l4tiNxSRgiiRpQicGdm7utreURahUDrIJhBBujAgtIGfpvQ", "stock": 25, "description": "Neon highlighter set featuring vibrant colors and smudge-proof ink for highlighting important notes."},
    {"id": 6, "name": "Geometry Set", "price": 65.00, "cost_price": 40.0, "category": "Stationery", "image": "https://encrypted-tbn2.gstatic.com/shopping?q=tbn:ANd9GcToAfSR40Cz515_otYv6ID9qEEZ-w2Q-6JSkw1gzMHYFVCspnskMhAMZLTzwkAXUH9m6oPavab-gE1Kk8sAu9_73PqWV__EO4XM1iIwJBm-OtIEmV4JUTSz", "stock": 25, "description": "Complete 8-piece geometry box containing compass, divider, ruler, and set squares."},
    {"id": 8, "name": "Whiteboard Markers ", "price": 95.00, "cost_price": 60.0, "category": "Stationery", "image": "https://encrypted-tbn2.gstatic.com/shopping?q=tbn:ANd9GcQi2HpO9TGAtck4ZTS1ZVZEccEugpLxxQm5OGyssW9ftzlD1y1UNUBxKPUR1kqoeIU75wqOuvaaC3KAVRm4Cp6d3thD8lrIWWMn0KhiBMFgdAlmtxN74Ydv", "stock": 30, "description": "Pack of 4 high-visibility whiteboard markers in primary colors. Easy-wipe ink formulas."},
    {"id": 9, "name": "Metal Ruler (30cm)", "price": 25.00, "cost_price": 10.0, "category": "Stationery", "image": "https://encrypted-tbn1.gstatic.com/shopping?q=tbn:ANd9GcRSc7NYP79N5Phs8PfaLHzcqwUiQGOLu3RX8UxwlOemZClmJfIue46Z0bpflD7gs47N7XgZOjt406ENI30e4odG0VsI-EvvifkuKLma5V5FbhclYVfkuNMf", "stock": 60, "description": "Durable stainless steel 30cm ruler with clear metric and imperial markings."},
    {"id": 99, "name": " Print Service", "price": 1.00, "cost_price": 0.2, "category": "Service", "image": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:ANd9GcSP1Q8eiENqHxmnpnOrqUcwdnC--bLqG3fLMmO1PSoK8MIb5GpHVV0mpZBxxi5fhebW_0seOoxDp8guV0zZEMYfhQDwdLn9nT9PXNvkvAqbkY1Nxe3k2ht8aQ", "stock": 9999, "is_service": True, "description": ""},
]

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

# In-memory storage for print jobs (In production use DB)
PRINT_JOBS = []

# Global Store State
STORE_CONFIG = {
    "is_open": True,
    "maintenance_mode": False,
    "upi_id": "unistore@upi",
    "gpay_qr_url": "https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=GPay-User-QR-Coming-Soon",
    "announcement": "Welcome to UniStore! We are open for your needs.",
    "hero_banners": [
        "https://images.unsplash.com/photo-1456735190827-d1262f71b8a3?w=1200",
        "https://images.unsplash.com/photo-1544411047-c4915837bc71?w=1200"
    ]
}
ORDERS = [] # Paid orders
FEEDBACK = [] # User feedback storage
AUDIT_LOGS = [] # Tracking admin/staff changes
STAFF_PERFORMANCE = {} # {email: {fulfilled_orders: 0, print_jobs: 0}}

# New Feature Stores
STAFF_TODOS = []  # [{id, text, completed, created_by, created_at}]
SHIFT_LOG = {}    # {staff_email: {clocked_in: bool, clock_in_time: str, history: []}}
CHAT_MESSAGES = [] # [{id, sender, sender_role, message, timestamp}]
LOW_STOCK_THRESHOLD = 5  # Alert when stock drops below this

def add_audit_log(action, user, details=""):
    AUDIT_LOGS.append({
        "action": action,
        "user": user,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "details": details
    })
    if len(AUDIT_LOGS) > 1000: AUDIT_LOGS.pop(0) # Keep last 1000 logs

# ==============================
# NEW: Enhanced User Features
# ==============================

# User Profiles with Loyalty Points
USER_PROFILES = {}  # {username: {points: 0, tier: 'Bronze', total_spent: 0, referral_code: '', referred_by: ''}}

# Loyalty Tiers Configuration
LOYALTY_TIERS = {
    'Bronze': {'min_points': 0, 'benefits': 'Welcome bonus', 'color': '#cd7f32'},
    'Silver': {'min_points': 500, 'benefits': '5% discount on all orders', 'color': '#c0c0c0'},
    'Gold': {'min_points': 1500, 'benefits': '10% discount + Free prints', 'color': '#ffd700'},
    'Platinum': {'min_points': 3000, 'benefits': '15% discount + Priority support', 'color': '#e5e4e2'}
}

# Notifications System
NOTIFICATIONS = []  # [{id, user, type, title, message, read, timestamp, icon}]

# Wishlist System
WISHLISTS = {}  # {username: [product_ids]}

# Referral System
REFERRALS = []  # [{referrer, referee, status, reward_claimed, timestamp}]

# Support Tickets
SUPPORT_TICKETS = []  # [{id, user, subject, message, status, priority, created_at, responses}]


# ==============================
# Page Routes
# ==============================
@app.route("/")
def home():
    return render_template("intro.html")

@app.route("/shop")
@login_required
def shop_page():
    if not STORE_CONFIG["is_open"]:
        return render_template("store_closed.html")
    return render_template("shop.html")

@app.route("/print-service")
@login_required
def print_page():
    if not STORE_CONFIG["is_open"]:
        return render_template("store_closed.html")
    return render_template("print_upload.html")

@app.route("/cart")
@login_required
def cart_page():
    return render_template("cart.html")

@app.route("/payment")
@login_required
def payment_page():
    user_email = session['user']
    # Ensure profile exists
    if user_email not in USER_PROFILES: USER_PROFILES[user_email] = {}
    if 'wallet_balance' not in USER_PROFILES[user_email]:
         USER_PROFILES[user_email]['wallet_balance'] = 0.00
            
    balance = USER_PROFILES[user_email]['wallet_balance']
    return render_template("payment.html", 
                         store_config=STORE_CONFIG,
                         razorpay_key_id=RAZORPAY_KEY_ID,
                         wallet_balance=balance)

@app.route("/retrieval/<order_id>")
@login_required
def retrieval_page(order_id):
    # Fetch from DB to ensure persistence
    order = get_order_by_id(order_id)
    
    if not order:
        # Fallback to memory if DB fail (legacy)
        order = next((o for o in ORDERS if o['id'] == order_id), None)
        
    if not order:
        return redirect(url_for('user_dashboard'))
        
    # Check ownership
    user = session['user']
    if order.get('user_email') != user and order.get('user') != user:
        return redirect(url_for('user_dashboard'))
        
    return render_template("retrieval.html", order=order)

@app.route("/login")
def login_page():
    return render_template("user_login.html")

@app.route("/register")
def reg_page():
    return render_template("user_register.html")

@app.route("/staff")
def staff_page():
    return render_template("staff_login.html")

@app.route("/user/dashboard")
@login_required
def user_dashboard():
    if STORE_CONFIG.get("maintenance_mode", False):
        return render_template("maintenance.html")
    try:
        user_email = session.get('user')
        if not user_email: return redirect(url_for('login_page'))
        
        # 1. Get Stats from DB
        stats = get_user_stats(user_email)
        
        if not stats:
            stats = {'points': 0, 'tier': 'Bronze', 'total_spent': 0, 'total_orders': 0}
            
        # 2. Get Recent Orders
        all_orders = get_user_orders(user_email)
        
        # DEBUG: Sanitize orders to prevent "builtin_function_or_method" error
        sanitized_orders: list = []
        for o in all_orders:
            # We no longer filter by is_archived here because users should see their history.
            # Archiving only hides orders from the Staff/Admin Task List.
            if 'items' not in o:
                print(f"WARNING: Order {o.get('id')} missing 'items' key. Fixing.")
                o['items'] = []
            sanitized_orders.append(o)
            
        # IMPORTANT: Use sanitized list for both recent and all orders
        all_orders = sanitized_orders 
        recent_orders = sanitized_orders[:5] # Top 5 recent
        
        # 3. Get Print Jobs (In Memory)
        user_prints = [p for p in PRINT_JOBS if p['user'] == user_email]
        
        # 4. Next Tier Logic
        points = stats['points']
        tier = stats['tier']
        next_tier_points = 500
        if tier == 'Silver': next_tier_points = 1500
        if tier == 'Gold': next_tier_points = 3000
        if tier == 'Platinum': next_tier_points = points # Cap it
        
        # 5. Populate Profile for Template
        temp_user = get_user_by_email(user_email)
        profile = {
            'name': session.get('user_name', user_email.split('@')[0]),
            'email': user_email,
            'college': temp_user.get('college', 'N/A') if temp_user else 'N/A',
            'points': points,
            'tier': tier,
            'total_spent': stats['total_spent'],
            'total_orders': stats['total_orders'],
            'referral_code': stats.get('referral_code', ''),
            'referral_count': stats.get('referral_count', 0),
            'referred_by': stats.get('referred_by', '')
        }
        
        # 6. Notifications (In Memory for this demo)
        user_notifications = [n for n in NOTIFICATIONS if n.get('user') == user_email]
        
        # 7. Wishlist Items
        wishlist_ids = WISHLISTS.get(user_email, [])
        wishlist_items = [p for p in PRODUCTS if p['id'] in wishlist_ids]
        wishlist_count = len(wishlist_items)
        
        # 8. Tier Color
        tier_color = LOYALTY_TIERS.get(tier, {}).get('color', '#6b7280') # Default gray
        profile['tier_color'] = tier_color

        # ==========================================
        # NEW FEATURES: Wallet, Recommendations, Avatar
        # ==========================================
        
        # A. Wallet Balance
        if user_email not in USER_PROFILES: USER_PROFILES[user_email] = {}
        # Sync from DB stats
        USER_PROFILES[user_email]['wallet_balance'] = stats.get('wallet_balance', 0.0)
        profile['wallet_balance'] = USER_PROFILES[user_email]['wallet_balance']
        
        # B. Avatar
        # Default avatar or user selected
        if 'avatar' not in USER_PROFILES.get(user_email, {}):
            USER_PROFILES[user_email]['avatar'] = profile['name'][0].upper() # Default to initial
        
        current_avatar = USER_PROFILES[user_email]['avatar']
        
        # C. Recommendations Logic
        # Simple Logic: potential recommendations based on categories of recent orders
        purchased_categories = set()
        for o in all_orders:
            for item in o.get('items', []):
                 # Find product category (mock logic as order items might not have category, so we look up in PRODUCTS)
                 prod_def = next((p for p in PRODUCTS if p['name'] == item.get('name')), None)
                 if prod_def:
                     purchased_categories.add(prod_def['category'])
        
        # If no purchases, show popular items (Stationery)
        if not purchased_categories:
            purchased_categories.add('Stationery')
            
        # Get products from these categories, excluding ones already bought (logic simplified for demo)
        recommendations = [p for p in PRODUCTS if p['category'] in purchased_categories][:4]
        
        # Preset Avatars for UI
        preset_avatars = [
            {'name': 'The Coder', 'emoji': '👨‍💻'},
            {'name': 'The Artist', 'emoji': '🎨'},
            {'name': 'The Athlete', 'emoji': '🏃'},
            {'name': 'The Scholar', 'emoji': '🎓'},
            {'name': 'The Musician', 'emoji': '🎧'},
            {'name': 'The Gamer', 'emoji': '🎮'}
        ]

        return render_template(
            "user_dashboard.html", 
            user=session['user'],
            profile=profile,
            current_avatar=current_avatar,
            preset_avatars=preset_avatars,
            recommendations=recommendations,
            orders=all_orders, 
            print_jobs=user_prints, 
            next_tier_points=next_tier_points,
            notifications=user_notifications,
            wishlist_count=wishlist_count,
            wishlist_items=wishlist_items,
            datetime_now=datetime.now().strftime("%A, %d %B %Y"),
            support_tickets=[t for t in SUPPORT_TICKETS if t['user'] == user_email]
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Dashboard Error: {e}")
        return redirect(url_for('login_page'))

# ==============================
# NEW API ENDPOINTS FOR DASHBOARD FEATURES
# ==============================

@app.route("/api/user/wallet/topup", methods=["POST"])
@login_required
def wallet_topup():
    amount = float(request.json.get('amount', 0))
    user_email = session['user']
    
    if user_email not in USER_PROFILES: USER_PROFILES[user_email] = {}
    current_bal = USER_PROFILES[user_email].get('wallet_balance', 0.0)
    
    new_bal = current_bal + amount
    USER_PROFILES[user_email]['wallet_balance'] = new_bal
    update_wallet_balance(user_email, new_bal)
    
    # Add notification
    NOTIFICATIONS.append({
        "id": len(NOTIFICATIONS) + 1,
        "user": user_email,
        "message": f"Wallet topped up with ₹{amount}. New Balance: ₹{new_bal}",
        "read": False,
        "timestamp": "Just now"
    })
    
    return jsonify({"success": True, "new_balance": new_bal})

@app.route("/api/user/update-avatar", methods=["POST"])
@login_required
def update_avatar():
    avatar = request.json.get('avatar')
    user_email = session['user']
    
    if user_email not in USER_PROFILES: USER_PROFILES[user_email] = {}
    USER_PROFILES[user_email]['avatar'] = avatar
    
    return jsonify({"success": True, "avatar": avatar})


@app.route("/feedback/<order_id>")
@login_required
def feedback_page(order_id):
    # Try DB first
    order = get_order_by_id(order_id)
    
    # Fallback to memory
    if not order:
        order = next((o for o in ORDERS if o['id'] == order_id), None)
        
    if not order: return redirect(url_for('user_dashboard'))
    return render_template("feedback.html", order_id=order_id)

@app.route("/order-success/<order_id>")
@login_required
def order_success(order_id):
    return render_template("order_success.html", order_id=order_id)

@app.route("/order-receipt/<order_id>")
@login_required
def order_receipt(order_id):
    from database import get_order_by_id
    order = get_order_by_id(order_id)
    if not order:
        # Fallback to in-memory for safety during dev
        order = next((o for o in ORDERS if o['id'] == order_id), None)
        
    if not order or (order.get('user_email') != session['user'] and order.get('user') != session['user']):
        return redirect(url_for('user_dashboard'))
        
    # Sanitize order items for template (ensure brackets work)
    if 'items' not in order or not isinstance(order['items'], list):
        order['items'] = []
        
    return render_template("order_receipt.html", order=order)


@app.route("/staff/dashboard")
def staff_dashboard():
    if STORE_CONFIG.get("maintenance_mode", False):
        return render_template("maintenance.html")
    if 'staff' not in session:
        return redirect(url_for('staff_page'))
        
    # Get Orders from DB + Memory (Merged view, prioritizing DB)
    db_orders = get_all_orders()
    
    # We might still want some memory-only orders if they exist and aren't in DB (though everything saves to DB now)
    # But for simplicity and consistency, let's use DB as source of truth
    # If db_orders is empty, we might check memory (legacy fallback)
    all_orders = db_orders if db_orders else ORDERS
    
    # NEW: Filter out archived orders (soft deleted) from the dashboard view
    visible_orders = [o for o in all_orders if not o.get('is_archived')]
    
    # Process visible orders to add display times for scheduled orders
    for order in visible_orders:
        if order.get('status') == 'Scheduled' and order.get('pickup_time'):
             try:
                 pickup_time = order['pickup_time']
                 if " " in pickup_time and len(pickup_time) > 10:
                      # Full format: "YYYY-MM-DD HH:MM"
                      dt_obj = datetime.strptime(pickup_time, "%Y-%m-%d %H:%M")
                      end_time_obj = dt_obj + timedelta(minutes=1)
                      # Format: 10 Feb, 14:30
                      order['display_start'] = dt_obj.strftime("%d %b, %H:%M")
                      order['display_end'] = end_time_obj.strftime("%H:%M") 
                 else:
                      # Legacy/Today format
                      clean_time = pickup_time.replace("Today, ", "").strip()
                      pt_obj = datetime.strptime(clean_time, "%H:%M")
                      end_time_obj = pt_obj + timedelta(minutes=1)
                      order['display_start'] = pickup_time
                      order['display_end'] = end_time_obj.strftime("%H:%M")
             except Exception as e:
                 print(f"Error parsing time for order {order.get('id')}: {e}")
                 order['display_start'] = order.get('pickup_time')
                 order['display_end'] = "?"

    # Calculate stats on ALL historical orders (including archived)
    total_revenue = sum(float(o.get('total', 0) or 0) for o in all_orders if o.get('status') == 'Delivered')
    total_orders_count = len(all_orders)

    return render_template("staff_dashboard.html", 
                         print_jobs=PRINT_JOBS, 
                         orders=visible_orders,
                         all_orders_for_stats=all_orders,
                         staff_revenue=total_revenue,
                         staff_total_orders=total_orders_count,
                         store_config=STORE_CONFIG,
                         products=PRODUCTS,
                         feedbacks=FEEDBACK)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route("/api/products")
def get_products_api():
    # Enrich products with reviews
    products_with_reviews = []
    for p in PRODUCTS:
        reviews = get_product_reviews(p['id'])
        avg_rating = sum([r['rating'] for r in reviews]) / len(reviews) if reviews else 0
        p_data = p.copy()
        p_data['rating'] = round(avg_rating, 1)
        p_data['reviews_count'] = len(reviews)
        products_with_reviews.append(p_data)
    return jsonify(products_with_reviews)

# API Endpoints
# ==============================

@app.route("/api/order/status/<order_id>")
@login_required
def get_order_status(order_id):
    # Try DB first
    order = get_order_by_id(order_id)
    
    # Fallback to memory
    if not order:
        order = next((o for o in ORDERS if o['id'] == order_id), None)
        
    if not order: return jsonify({"message": "Not found"}), 404
    
    return jsonify({
        "status": order['status'],
        "is_ready": bool(order['is_ready']),
        "attempts": order.get('collection_attempts', 0),
        "notification": order.get('notification', ''),
        "pickup_time": order.get('pickup_time', '')
    })

@app.route("/api/order/timeout", methods=["POST"])
@login_required
def order_timeout():
    order_id = request.json.get('id')
    new_status = ""
    notification = ""
    
    # Update Memory
    for o in ORDERS:
        if o['id'] == order_id:
            o['is_ready'] = False
            if o['collection_attempts'] >= 2:
                o['status'] = "Cancelled"
                o['notification'] = "Order cancelled due to non-collection after 2 attempts."
                new_status = "Cancelled"
                notification = o['notification']
                # Refund to wallet if paid via Razorpay or Wallet
                refund_to_wallet(o)
            else:
                o['status'] = "Pending"
                o['notification'] = f"Attempt {o['collection_attempts']} missed. Staff must re-assign time."
                new_status = "Pending"
                notification = o['notification']
            break
    
    # Update Database
    if new_status:
        update_order_status(order_id, new_status, is_ready=False)
        return jsonify({"message": "success", "status": new_status})
        
    return jsonify({"message": "Order not found"}), 404

@app.route("/api/staff/ready-collection", methods=["POST"])
def ready_collection():
    if 'staff' not in session: return jsonify({"message": "Unauthorized"}), 403
    order_id = request.json.get('id')
    
    # Update Memory (Legacy) and Check Logic
    target_order = None
    for o in ORDERS:
        if o['id'] == order_id:
            target_order = o
            break
            
    if not target_order:
        # Check DB if not in memory
        target_order = get_order_by_id(order_id)
        if not target_order:
            return jsonify({"message": "Order not found"}), 404
            
    if target_order.get('status') == "Cancelled":
         return jsonify({"message": "Cannot ready a cancelled order"}), 400
         
    # Increment attempts
    current_attempts = target_order.get('collection_attempts', 0) + 1
    target_order['collection_attempts'] = current_attempts
    target_order['is_ready'] = True
    target_order['status'] = "Ready for Collection"
    target_order['notification'] = f"Time Assigned! Attempt {current_attempts}/2. Collect in 1 minute!"
    
    # Update DB
    update_order_status(order_id, "Ready for Collection", collection_attempts=current_attempts, is_ready=True)
    
    # Send Email
    user_email = target_order.get('user_email') or target_order.get('user') # DB uses user_email, Memory uses user
    if user_email:
        threading.Thread(target=send_notification_email, args=(
            user_email, 
            order_id, 
            f"Your order is READY for collection! You have 1 minute (60 seconds) to collect it. Attempt {current_attempts}/2."
        )).start()
        
    # Start Auto-Timeout Timer
    threading.Thread(target=auto_handle_timeout, args=(order_id,)).start()
    
    return jsonify({"message": "success", "attempts": current_attempts})

@app.route("/api/staff/schedule-order", methods=["POST"])
def schedule_order():
    if 'staff' not in session: return jsonify({"message": "Unauthorized"}), 403
    
    data = request.json
    order_id = data.get('id')
    pickup_time = data.get('time') # Should be string
    
    # Validation
    if not order_id or not pickup_time:
        return jsonify({"message": "Missing ID or Time"}), 400
        
    # Update logic
    target_order = None
    for o in ORDERS:
        if o['id'] == order_id:
            target_order = o
            break
            
    if not target_order:
        target_order = get_order_by_id(order_id)
        if not target_order:
            return jsonify({"message": "Order not found"}), 404
            
    attempts = target_order.get('collection_attempts', 0)
    if attempts >= 2:
         return jsonify({"message": "Maximum reassignment attempts reached (2/2). Order is cancelled."}), 400
         
    # Set to 'Scheduled' - Countdown only starts at the specified time
    is_reassignment = attempts > 0
    current_attempts = attempts + 1
    target_order['collection_attempts'] = current_attempts
    target_order['status'] = "Scheduled"
    target_order['pickup_time'] = pickup_time
    target_order['is_ready'] = False
    target_order['notification'] = f"Scheduled for {pickup_time}. Attempt {current_attempts}/2."
    
    # Update DB
    update_order_status(order_id, "Scheduled", collection_attempts=current_attempts, is_ready=False, pickup_time=pickup_time)
    
    # Start the delay thread
    threading.Thread(target=process_scheduled_pickup, args=(order_id, pickup_time, current_attempts, is_reassignment)).start()
    
    # Calculate End Time (Start + 1 min window)
    try:
        if " " in pickup_time and len(pickup_time) > 10:
             # Full format: "YYYY-MM-DD HH:MM"
             dt_obj = datetime.strptime(pickup_time, "%Y-%m-%d %H:%M")
             end_time_obj = dt_obj + timedelta(minutes=1)
             pickup_end = end_time_obj.strftime("%H:%M")
             display_time = dt_obj.strftime("%d %b, %H:%M")
        else:
             # Legacy/Today format
             clean_time = pickup_time.replace("Today, ", "").strip()
             pt_obj = datetime.strptime(clean_time, "%H:%M")
             end_time_obj = pt_obj + timedelta(minutes=1)
             pickup_end = end_time_obj.strftime("%H:%M")
             display_time = pickup_time
    except Exception:
        pickup_end = "1 minute later"
        display_time = pickup_time

    # Send Email
    user_email = target_order.get('user_email') or target_order.get('user')
    if user_email:
        email_subject = f"Order Pickup {'REASSIGNED' if is_reassignment else 'Scheduled'}"
        title_text = f"Your order pickup has been {'REASSIGNED' if is_reassignment else 'Scheduled'}"
        email_body = f"""
Hello,

{title_text} ✅

Token: #{target_order.get('token', '-')}

Pickup Window:
Start: {display_time}
End: {pickup_end}

Attempt: {current_attempts}/2

Important: Your collection window will only begin at {display_time}. You will have exactly 1 minute to collect your items from that time.

Thank you,
College Store
"""
        threading.Thread(target=send_email, args=(user_email, email_subject, email_body)).start()
        
    return jsonify({"message": "success"})

@app.route("/api/staff/deliver-order", methods=["POST"])
def deliver_order():
    if 'staff' not in session: return jsonify({"message": "Unauthorized"}), 403
    order_id = request.json.get('id')
    
    # Update Memory (Legacy)
    found_in_memory = False
    for o in ORDERS:
        if o['id'] == order_id:
            found_in_memory = True
            if o['status'] == "Cancelled":
                return jsonify({"message": "Cannot deliver a cancelled order"}), 400
            o['status'] = "Delivered"
            break
            
    # Update Database
    success = update_order_status(order_id, "Delivered")
    
    if found_in_memory or success:
        # Send Email Notification
        # Get order details for email
        order = get_order_by_id(order_id)
        if not order:
            order = next((o for o in ORDERS if o['id'] == order_id), None)
            
        if order:
            user_email = order.get('user_email') or order.get('user')
            if user_email:
                email_subject = "Order Delivered Successfully!"
                email_body = """
🎉 Order Delivered Successfully!
Your order has been collected from the college store.
We hope you enjoy your purchase. Have a great day!
"""
                threading.Thread(target=send_email, args=(user_email, email_subject, email_body)).start()

        return jsonify({"message": "success"})
    return jsonify({"message": "Order not found"}), 404

@app.route("/api/staff/complete-print", methods=["POST"])
def complete_print():
    if 'staff' not in session: return jsonify({"message": "Unauthorized"}), 403
    job_id = int(request.json.get('id'))
    for j in PRINT_JOBS:
        if j['id'] == job_id:
            j['status'] = "Completed"
            return jsonify({"message": "success"})
    return jsonify({"message": "Job not found"}), 404

@app.route("/api/staff/update-config", methods=["POST"])
def update_config():
    if 'staff' not in session: return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    STORE_CONFIG["upi_id"] = data.get("upi_id", STORE_CONFIG["upi_id"])
    STORE_CONFIG["gpay_qr_url"] = data.get("gpay_qr_url", STORE_CONFIG["gpay_qr_url"])
    return jsonify({"message": "success"})

@app.route("/api/submit-feedback", methods=["POST"])
@login_required
def submit_feedback():
    data = request.json
    order_id = data.get("order_id")
    rating = int(data.get("rating", 0))
    comment = data.get("comment")
    user_email = session['user']
    
    # Save to memory (Legacy)
    FEEDBACK.append({
        "order_id": order_id,
        "user": user_email,
        "rating": rating,
        "comment": comment,
        "date": "Just now"
    })
    
    # Save to Database for Product Reviews
    # Fetch order to get items
    order = get_order_by_id(order_id)
    if not order:
        # Check memory
        for o in ORDERS:
            if o['id'] == order_id:
                order = o
                break
                
    if order and "items" in order:
        try:
            items = order['items']
            # items is already a list of dicts from get_order_by_id or memory
            for item in items:
                # Need product ID. Cart items usually have 'id'.
                if 'id' in item:
                    # Persist review for this product
                    # Note: This applies the SAME rating to all products in the order.
                    # Ideally we should ask for individual ratings, but this bridges the gap.
                    add_review(user_email, item['id'], rating, comment)
        except Exception as e:
            print(f"Error saving reviews to DB: {e}")
            
    return jsonify({"message": "success"})

@app.route("/api/staff/update-item", methods=["POST"])
def update_item():
    if 'staff' not in session and 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    p_id = int(data.get('id'))
    new_qty = data.get('stock', data.get('quantity'))
    new_price = data.get('price')
    for p in PRODUCTS:
        if p['id'] == p_id:
            try:
                user = session.get('admin', session.get('staff'))
                old_stock = p['stock']
                old_price = p['price']
                
                if new_qty is not None and str(new_qty).strip(): p['stock'] = int(new_qty)
                if new_price is not None and str(new_price).strip(): p['price'] = float(new_price)
                if data.get('cost_price') is not None and str(data.get('cost_price')).strip(): 
                    p['cost_price'] = float(data.get('cost_price'))
                if 'description' in data:
                    p['description'] = data['description']
                
                add_audit_log("Update Item", user, f"Changed {p['name']} (ID:{p_id}): Stock {old_stock}->{p['stock']}, Price {old_price}->{p['price']}")
                return jsonify({"message": "success"})
            except ValueError:
                return jsonify({"message": "Invalid input values"}), 400
@app.route("/api/staff/delete-item", methods=["POST"])
def delete_item():
    if 'staff' not in session and 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    p_id = int(request.json.get('id'))
    global PRODUCTS
    p_to_del = next((p for p in PRODUCTS if p['id'] == p_id), None)
    if p_to_del:
        user = session.get('admin', session.get('staff'))
        add_audit_log("Delete Item", user, f"Deleted product: {p_to_del['name']} (ID: {p_id})")
        PRODUCTS = [p for p in PRODUCTS if p['id'] != p_id]
    return jsonify({"message": "success"})

@app.route("/api/staff/add-item", methods=["POST"])
def add_item():
    if 'staff' not in session and 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    new_id = max([p['id'] for p in PRODUCTS]) + 1 if PRODUCTS else 1
    new_product = {
        "id": new_id,
        "name": data.get("name"),
        "price": float(data.get("price")),
        "cost_price": float(data.get("cost_price", data.get("price") * 0.7)), # Default 30% margin if not provided
        "category": data.get("category"),
        "image": data.get("image", "https://images.unsplash.com/photo-1586075010633-24703276633d?w=500&q=80"),
        "stock": int(data.get("stock", 0)),
        "description": data.get("description", ""),
        "is_service": False
    }
    user = session.get('admin', session.get('staff'))
    add_audit_log("Add Item", user, f"Added new product: {new_product['name']} (ID: {new_id}) at price ₹{new_product['price']}")
    PRODUCTS.append(new_product)
    return jsonify({"message": "success", "product": new_product})

@app.route("/api/staff/toggle-store", methods=["POST"])
def toggle_store():
    if 'staff' not in session and 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    STORE_CONFIG["is_open"] = not STORE_CONFIG["is_open"]
    return jsonify({"message": "success", "is_open": STORE_CONFIG["is_open"]})

@app.route("/api/admin/toggle-maintenance", methods=["POST"])
def toggle_maintenance():
    if 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    STORE_CONFIG["maintenance_mode"] = not STORE_CONFIG.get("maintenance_mode", False)
    add_audit_log("Toggle Maintenance", session['admin'], f"Maintenance mode set to {STORE_CONFIG['maintenance_mode']}")
    return jsonify({"message": "success", "maintenance_mode": STORE_CONFIG["maintenance_mode"]})

@app.route("/api/staff/create-coupon", methods=["POST"])
def staff_create_coupon():
    if 'staff' not in session and 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    success = create_coupon(
        data.get('code'),
        data.get('type'),
        float(data.get('value')),
        float(data.get('min_spend', 0)),
        data.get('expiry_date'),
        int(data.get('max_uses', -1))
    )
    return jsonify({"message": "success" if success else "failed"})
    
@app.route("/api/admin/delete-coupon", methods=["POST"])
def admin_delete_coupon():
    if 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    code = request.json.get('code')
    if delete_coupon(code):
        add_audit_log("Delete Coupon", session['admin'], f"Deleted coupon: {code}")
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/admin/update-coupon", methods=["POST"])
def admin_update_coupon():
    if 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    success = update_coupon(
        data.get('code'),
        data.get('type'),
        float(data.get('value')),
        float(data.get('min_spend', 0)),
        data.get('expiry_date'),
        int(data.get('max_uses', -1))
    )
    if success:
        add_audit_log("Update Coupon", session['admin'], f"Updated coupon: {data.get('code')}")
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/upload-print", methods=["POST"])
@login_required
def upload_print():
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400
    
    file = request.files['file']
    pages = int(request.form.get('pages', 1))
    
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        config = {
            "color": request.form.get('color', 'Black & White'),
            "sides": request.form.get('sides', 'Single-sided'),
            "paper": request.form.get('paper', 'Standard')
        }
        
        # Calculate cost multiplier
        multiplier = 1
        if config['color'] == 'Color': multiplier *= 3
        if config['paper'] == 'Glossy': multiplier *= 2
        
        final_cost = pages * multiplier * 1 # Base rate Rs 1
        
        job = {
            "id": len(PRINT_JOBS) + 1,
            "filename": filename,
            "user": session['user'],
            "pages": pages,
            "config": config,
            "cost": final_cost,
            "status": "Pending",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().timestamp(),
            "token": get_token_for_user(session['user'])
        }
        PRINT_JOBS.append(job)
        return jsonify({"message": "success", "cost": job['cost'], "job_id": job['id']})

@app.route("/user/register", methods=["POST"])
def user_register_api():
    data = request.json
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    college = data.get("college", "").strip()
    referral_code = data.get("referral_code", "").strip().upper()
    
    # Validation
    if not name or not email or not password or not college:
        return jsonify({"success": False, "message": "All fields are required"}), 400
    
    if len(password) < 8:
        return jsonify({"success": False, "message": "Password must be at least 8 characters"}), 400
    
    if "@" not in email or "." not in email:
        return jsonify({"success": False, "message": "Please enter a valid email address"}), 400
    
    # Create user in database (with referral code if provided)
    result = create_user(name, email, password, college, referred_by_code=referral_code if referral_code else None)
    
    if result["success"]:
        # Send Welcome Email
        email_subject = "Welcome to UniStore! 🎉"
        email_body = f"""
Hello {name},

🎉 **You have been registered successfully!**

Welcome to the **UniStore**.

Your account has been created using this email address ({email}). You can now:

* Log in to your account
* Browse products
* Place orders
* Receive pickup time notifications after approval

If you did not create this account, please contact the store admin immediately.

We’re happy to have you with us!

Best regards,
**UniStore**
"""
        threading.Thread(target=send_email, args=(email, email_subject, email_body)).start()

        # Auto-login the user
        try:
            # Need to get user ID for session. create_user only returns success/message.
            # We can fetch it or modify create_user. Let's fetch it for minimal impact.
            user_data = get_user_by_email(email)
            if user_data:
                session.clear()
                session.permanent = True
                session['user'] = email
                session['user_id'] = user_data['id']
                session['user_name'] = name
        except Exception as e:
            print(f"Auto-login error: {e}")

        # Use relative URL to prevent domain mismatch
        return jsonify({"success": True, "message": f"Welcome {name}, your account is ready!", "redirect": url_for("user_dashboard")})
    else:
        return jsonify({"success": False, "message": result["message"]}), 400

@app.route("/user/login", methods=["POST"])
def user_login_api():
    data = request.json
    email = data.get("email", "").strip()
    password = data.get("password", "")
    
    # Log attempt
    with open("login_debug.log", "a") as f:
        f.write(f"Login attempt for: {email}\n")
    
    # Validation
    if not email or not password:
        with open("login_debug.log", "a") as f:
            f.write("Missing email or password\n")
        return jsonify({"success": False, "message": "Email and password are required"}), 400
    
    # Verify credentials
    result = verify_user(email, password)
    
    with open("login_debug.log", "a") as f:
        f.write(f"Verify result: {result}\n")
    
    if result["success"]:
        # Check if banned
        if email in USER_PROFILES and USER_PROFILES[email].get('banned'):
            return jsonify({"success": False, "message": "Your account has been suspended due to policy violations."}), 403
            
        # Agam's Fix: Aggressively clear old session to prevent contamination
        session.clear()
        
        # Re-establish session
        session.permanent = True
        session['user'] = email
        session['user_id'] = result['user']['id']
        session['user_name'] = result['user']['name']
        
        # Force session save (sometimes needed in Flask)
        session.modified = True
        
        with open("login_debug.log", "a") as f:
            f.write(f"Session set for: {session.get('user')}\n")
        
        return jsonify({
            "success": True, 
            "message": "success", 
            "redirect": url_for("user_dashboard")
        })
    else:
        return jsonify({"success": False, "message": result["message"]}), 401


# ==============================
# Forgot Password Logic
# ==============================
RESET_CODES = {} # {email: {'code': '123456', 'expires': timestamp}}

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password_api():
    email = request.json.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "message": "Email is required"}), 400
    
    user = get_user_by_email(email)
    if not user:
        # For security, we still say success but check if we want to be explicit
        return jsonify({"success": True, "message": "If this email exists, a code has been sent."})
    
    # Generate 6-digit code
    import random
    code = ''.join(random.choices("0123456789", k=6))
    
    # Store with expiration (15 mins)
    RESET_CODES[email] = {
        'code': code,
        'expires': time.time() + 900
    }
    
    # Send Email
    subject = "UniStore Password Reset Code"
    message = f"""
    Hello {user['name']},
    
    You requested a password reset for your UniStore account.
    
    Your reset code is: {code}
    
    This code will expire in 15 minutes. 
    If you did not request this, please ignore this email.
    
    Best regards,
    UniStore Team
    """
    
    threading.Thread(target=send_email, args=(email, subject, message)).start()
    
    return jsonify({"success": True, "message": "Reset code sent to your email."})

@app.route("/reset-password")
def reset_password_page():
    email = request.args.get("email")
    if not email:
        return redirect(url_for("forgot_password_page"))
    return render_template("reset_password.html", email=email)

@app.route("/api/reset-password", methods=["POST"])
def reset_password_api():
    data = request.json
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("password")
    
    if not all([email, code, new_password]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    if email not in RESET_CODES:
        return jsonify({"success": False, "message": "No reset request found for this email"}), 400
    
    reset_data = RESET_CODES[email]
    
    # Verify expiration
    if time.time() > reset_data['expires']:
        del RESET_CODES[email]
        return jsonify({"success": False, "message": "Reset code has expired"}), 400
    
    # Verify code
    if reset_data['code'] != code:
        return jsonify({"success": False, "message": "Invalid reset code"}), 400
    
    # Update Password in DB
    from database import update_user_password
    if update_user_password(email, new_password):
        # Clear reset code
        del RESET_CODES[email]
        return jsonify({"success": True, "message": "Password updated successfully!"})
    else:
        return jsonify({"success": False, "message": "Error updating password. Please try again."}), 500

@app.route("/admin/dashboard")
# Admin Dashboard Route
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('staff_page'))
        
    # Get overall stats from DB
    db_orders = get_all_orders()
    
    # Safer revenue calculation
    total_revenue = sum(float(o.get('total', 0) or 0) for o in db_orders if o.get('status') == 'Delivered')
    total_orders = len(db_orders)
    
    # Get all users for Customers section
    from database import get_all_users
    all_users = get_all_users()
    
    # Enrich user data with order stats
    customers_map = {u['email']: u for u in all_users}
    for u in customers_map.values():
        u['total_orders'] = 0
        u['total_spent'] = 0
        u['last_order'] = 'Never'
        
    for o in db_orders:
        email = o.get('user_email') or o.get('user')
        if not email: continue
        
        if email not in customers_map:
            # Create temp entry if user not in DB (legacy/guest)
            customers_map[email] = {
                'name': email.split('@')[0], 
                'email': email,
                'college': 'N/A',
                'created_at': 'N/A',
                'total_orders': 0,
                'total_spent': 0,
                'last_order': 'N/A'
            }
            
        customers_map[email]['total_orders'] += 1
        customers_map[email]['total_spent'] += float(o.get('total', 0) or 0)
        
        # Track last order date (handle None dates safely)
        order_date = o.get('date')
        if order_date:
            current_last = customers_map[email]['last_order']
            if current_last == 'Never' or current_last == 'N/A' or order_date > current_last:
                customers_map[email]['last_order'] = order_date

    customers_list = list(customers_map.values())
    total_customers = len(customers_list)
    
    # Status distribution
    status_counts = {'Pending': 0, 'Processing': 0, 'Delivered': 0, 'Cancelled': 0}
    for o in db_orders:
        s = o.get('status', 'Pending')
        if s == 'Pending': status_counts['Pending'] += 1
        elif s == 'Delivered': status_counts['Delivered'] += 1
        elif s == 'Cancelled': status_counts['Cancelled'] += 1
        else: status_counts['Processing'] += 1
        
    chart_status_data = [status_counts['Pending'], status_counts['Processing'], status_counts['Delivered'], status_counts['Cancelled']]
    
    # Calculate daily revenue for last 7 days
    today = datetime.now()
    sales_labels = []
    sales_data = []
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        label = day.strftime("%d %b") # e.g. "25 Feb"
        
        # Sum revenue for this day
        day_revenue = 0
        for o in db_orders:
            if o.get('status') == 'Delivered' and o.get('date', '').startswith(day_str):
                day_revenue += float(o.get('total', 0) or 0)
        
        sales_labels.append(label)
        sales_data.append(day_revenue)
    
    
    # Get all reviews if possible (mock for now or derive)
    all_reviews = []
    for p in PRODUCTS:
        reviews = get_product_reviews(p['id'])
        for r in reviews:
            r['product_name'] = p['name']
            all_reviews.append(r)
    
    # fetch all coupons
    all_coupons = get_all_coupons()
    
    # Calculate Profits & Staff performance
    total_cost = 0.0
    
    for o in db_orders:
        if o.get('status') == 'Delivered':
            # Calculate cost
            order_items = o.get('items', [])
            if isinstance(order_items, list):
                for item in order_items:
                    # Look up product for cost_price
                    prod_name = item.get('name')
                    prod = next((p for p in PRODUCTS if p['name'] == prod_name), None)
                    item_qty = int(item.get('quantity', 1))
                    if prod:
                        total_cost += float(prod.get('cost_price', float(prod['price']) * 0.7)) * item_qty
            
    total_profit = float(total_revenue) - total_cost
    
    # Enrichment of customers with banned status
    for u in customers_list:
        u_email = u.get('email')
        u['banned'] = USER_PROFILES.get(u_email, {}).get('banned', False) if u_email else False

    # Filter out archived orders for the UI table
    visible_admin_orders = [o for o in db_orders if not o.get('is_archived')]

    return render_template("admin_dashboard.html", 
                         total_revenue=total_revenue,
                         total_cost=total_cost,
                         total_profit=total_profit,
                         total_orders=total_orders,
                         total_customers=total_customers,
                         orders=visible_admin_orders,
                         all_orders=db_orders,
                         products=PRODUCTS,
                         customers=customers_list,
                         reviews=all_reviews,
                         coupons=all_coupons,
                         support_tickets=SUPPORT_TICKETS,
                         notifications=NOTIFICATIONS,
                         store_config=STORE_CONFIG,
                         sales_data=sales_data,
                         sales_labels=sales_labels,
                         chart_status_data=chart_status_data,
                         audit_logs=AUDIT_LOGS[::-1], # Newest first
                         staff_perf=STAFF_PERFORMANCE)

@app.route("/staff/login", methods=["POST"])
def staff_login_api():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    # Admin Credentials
    if email == "admin@instore.com" and password == "admin123":
        session.clear()
        session['admin'] = email
        return jsonify({"message": "success", "redirect": "/admin/dashboard"})
        
    # Staff credentials
    if email == "staff@instore.com" and password == "staff123":
        session.clear()
        session['staff'] = email
        return jsonify({"message": "success", "redirect": "/staff/dashboard"})
        
    return jsonify({"message": "Invalid Credentials"}), 401

# ==============================
# Enhanced Dashboard API Endpoints
# ==============================

@app.route("/api/coupons/validate", methods=["POST"])
@login_required
def validate_coupon():
    code = request.json.get('code')
    total = request.json.get('total')
    coupon = get_coupon(code)
    
    if not coupon:
        return jsonify({"success": False, "message": "Invalid coupon code"})
    
    if has_user_used_coupon(session['user'], code):
        return jsonify({"success": False, "message": "You have already used this coupon"})
        
    if total < coupon.get('min_spend', 0):
        return jsonify({"success": False, "message": f"Minimum spend of ₹{coupon['min_spend']} required"})
        
    discount = 0
    if coupon['discount_type'] == 'percentage':
        discount = (total * coupon['value']) / 100
    else:
        discount = coupon['value']
        
    return jsonify({
        "success": True, 
        "discount": discount, 
        "new_total": total - discount,
        "message": "Coupon applied!"
    })

@app.route("/api/reviews/add", methods=["POST"])
@login_required
def add_product_review():
    data = request.json
    success = add_review(
        session['user'],
        data.get('product_id'),
        data.get('rating'),
        data.get('comment')
    )
    return jsonify({"success": success})

@app.route("/api/wishlist/add", methods=["POST"])
@login_required
def add_to_wishlist():
    username = session.get('user')
    product_id = request.json.get('product_id')
    
    if username not in WISHLISTS:
        WISHLISTS[username] = []
    
    if product_id not in WISHLISTS[username]:
        WISHLISTS[username].append(product_id)
        return jsonify({"message": "Added to wishlist", "success": True})
    else:
        return jsonify({"message": "Already in wishlist", "success": False})

@app.route("/api/wishlist/remove", methods=["POST"])
@login_required
def remove_from_wishlist():
    username = session.get('user')
    product_id = request.json.get('product_id')
    
    if username in WISHLISTS and product_id in WISHLISTS[username]:
        WISHLISTS[username].remove(product_id)
        return jsonify({"message": "Removed from wishlist", "success": True})
    return jsonify({"message": "Not found", "success": False})

@app.route("/api/notifications/mark-read", methods=["POST"])
@login_required
def mark_notification_read():
    notification_id = request.json.get('notification_id')
    for notification in NOTIFICATIONS:
        if notification['id'] == notification_id and notification['user'] == session.get('user'):
            notification['read'] = True
            return jsonify({"message": "Marked as read", "success": True})
    return jsonify({"message": "Not found", "success": False})

@app.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    username = session.get('user')
    for notification in NOTIFICATIONS:
        if notification['user'] == username:
            notification['read'] = True
    return jsonify({"message": "All marked as read", "success": True})

@app.route("/api/support/create-ticket", methods=["POST"])
@login_required
def create_support_ticket():
    data = request.json
    username = session.get('user')
    
    ticket = {
        'id': len(SUPPORT_TICKETS) + 1,
        'user': username,
        'subject': data.get('subject'),
        'message': data.get('message'),
        'priority': data.get('priority', 'Medium'),
        'status': 'Open',
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'responses': []
    }
    
    SUPPORT_TICKETS.append(ticket)
    return jsonify({"message": "Ticket created successfully", "ticket_id": ticket['id'], "success": True})

@app.route("/api/referral/track", methods=["POST"])
@login_required
def track_referral():
    data = request.json
    referrer = session.get('user')
    referee_code = data.get('referee_code')
    
    # Find referrer by code
    referee = None
    for username, profile in USER_PROFILES.items():
        if profile.get('referral_code') == referee_code:
            referee = username
            break
    
    if referee and referee != referrer:
        referral = {
            'referrer': referee,
            'referee': referrer,
            'status': 'Pending',
            'reward_claimed': False,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        REFERRALS.append(referral)
        
        # Update referee's referred_by
        if referrer in USER_PROFILES:
            USER_PROFILES[referrer]['referred_by'] = referee
        
        return jsonify({"message": "Referral tracked successfully", "success": True})
    else:
        return jsonify({"message": "Invalid referral code", "success": False})

@app.route("/api/analytics/spending", methods=["GET"])
@login_required
def get_spending_analytics():
    username = session.get('user')
    user_orders = [o for o in ORDERS if o.get('user') == username and o['status'] == 'Delivered']
    
    total_spent = sum(o['total'] for o in user_orders)
    total_orders = len(user_orders)
    avg_order_value = total_spent / total_orders if total_orders > 0 else 0
    
    return jsonify({
        "total_spent": total_spent,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value,
        "success": True
    })

@app.route("/api/admin/reply-ticket", methods=["POST"])
def reply_ticket():
    if 'admin' not in session: return jsonify({"message": "Unauthorized"}), 403
    data = request.json
    ticket_id = int(data.get('ticket_id'))
    response_msg = data.get('response')
    
    for t in SUPPORT_TICKETS:
        if t['id'] == ticket_id:
            t['responses'].append({
                'user': 'Admin',
                'message': response_msg,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            t['status'] = 'Responded'
            # Send notification to user?
            NOTIFICATIONS.append({
                'id': len(NOTIFICATIONS) + 1,
                'user': t['user'],
                'type': 'support',
                'title': f'Support Reply: Ticket #{ticket_id}',
                'message': f"Admin replied: {response_msg[:50]}...",
                'read': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            return jsonify({"success": True})
    return jsonify({"success": False, "message": "Ticket not found"})

@app.route("/api/admin/delete-order", methods=["POST"])
def admin_delete_order():
    if 'admin' not in session and 'staff' not in session: 
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    order_id = request.json.get('id')
    if not order_id:
        return jsonify({"success": False, "message": "Missing order ID"}), 400

    # Delete from Database
    from database import delete_order_db
    db_success = delete_order_db(order_id)

    # Delete from Memory (Legacy fallback)
    global ORDERS
    original_len = len(ORDERS)
    ORDERS = [o for o in ORDERS if o['id'] != order_id]
    mem_success = len(ORDERS) < original_len

    if db_success or mem_success:
        user = session.get('admin', session.get('staff'))
        add_audit_log("Delete Order", user, f"Deleted order: {order_id}")
        return jsonify({"success": True})
        
    return jsonify({"success": False, "message": "Order not found"}), 404

# ==============================
# Admin API Endpoints
# ==============================

@app.route("/api/admin/shifts", methods=["GET"])
def admin_get_shifts():
    if 'admin' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    shifts_data = []
    for staff_email, shift in SHIFT_LOG.items():
        shifts_data.append({
            "staff": staff_email,
            "clocked_in": shift.get("clocked_in", False),
            "clock_in_time": shift.get("clock_in_time"),
            "history": shift.get("history", [])
        })
    return jsonify({"success": True, "shifts": shifts_data})

@app.route("/api/admin/toggle-ban", methods=["POST"])
def admin_toggle_ban():
    if 'admin' not in session: return jsonify({"success": False, "message": "Unauthorized"}), 403
    email = request.json.get('email')
    if not email: return jsonify({"success": False}), 400
    
    if email not in USER_PROFILES: USER_PROFILES[email] = {}
    is_banned = USER_PROFILES[email].get('banned', False)
    USER_PROFILES[email]['banned'] = not is_banned
    
    action = "Ban" if not is_banned else "Unban"
    add_audit_log(f"{action} User", session['admin'], f"{action}ned user: {email}")
    return jsonify({"success": True, "banned": not is_banned})

@app.route("/api/admin/export-sales")
def export_sales():
    if 'admin' not in session: return "Unauthorized", 403
    
    import csv
    import io
    from flask import Response
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    db_orders = get_all_orders()
    writer.writerow(['Order ID', 'User', 'Date', 'Total', 'Status', 'Method'])
    
    for o in db_orders:
        writer.writerow([
            o.get('id'),
            o.get('user_email') or o.get('user'),
            o.get('date'),
            o.get('total'),
            o.get('status'),
            o.get('method')
        ])
        
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=sales_report.csv"
    return response

# ==============================
# Razorpay Payment API Endpoints
# ==============================

@app.route("/api/create-razorpay-order", methods=["POST"])
@login_required
def create_razorpay_order():
    """Create Razorpay order for payment"""
    try:
        data = request.json
        amount = data.get('amount')  # This is the original total from frontend
        cart_items = data.get('cart', [])
        coupon_code = data.get('coupon_code')
        
        if not amount or not cart_items:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        # Calculate server-side total
        server_total = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
        
        # Apply Coupon if present
        discount = 0
        if coupon_code:
            coupon = get_coupon(coupon_code)
            if coupon and server_total >= coupon.get('min_spend', 0):
                if coupon['discount_type'] == 'percentage':
                    discount = (server_total * coupon['value']) / 100
                else:
                    discount = coupon['value']
        
        final_amount = max(0, server_total - discount)

        # Check Stock (skip print service items)
        for item in cart_items:
            if str(item['id']).startswith('PRINT-'):
                continue
            product = next((p for p in PRODUCTS if str(p['id']) == str(item['id'])), None)
            if not product:
                return jsonify({'success': False, 'error': f"Product {item['name']} no longer available"}), 400
            if product['stock'] < item['quantity']:
                return jsonify({'success': False, 'error': f"Insufficient stock for {product['name']}. Only {product['stock']} left."}), 400
        
        # Create Razorpay Order
        razorpay_order = razorpay_client.order.create({
            'amount': int(final_amount * 100),  # Convert to paise
            'currency': 'INR',
            'receipt': f'order_rcpt_{len(ORDERS) + 1}',
            'payment_capture': 1,  # Auto capture payment
            'notes': {
                'user_email': session['user'],
                'cart': json.dumps(cart_items),
                'coupon_code': coupon_code
            }
        })
        
        return jsonify({
            'success': True,
            'order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency']
        })
        
    except Exception as e:
        print(f"Razorpay order creation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route("/api/verify-payment", methods=["POST"])
@login_required
def verify_razorpay_payment():
    """Verify Razorpay payment and create order"""
    try:
        data = request.json
        
        # Razorpay payment details
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_signature = data.get('razorpay_signature')
        
        # Cart items
        cart_items = data.get('cart', [])
        
        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return jsonify({'success': False, 'error': 'Missing payment details'}), 400
        
        # Idempotency check: Check if order already exists (webhook might have already processed it)
        from database import get_order_by_razorpay_id, save_order
        existing_order = get_order_by_razorpay_id(razorpay_order_id)
        if existing_order:
            return jsonify({
                'success': True,
                'message': 'Payment already verified',
                'order_id': existing_order['id']
            })

        # Verify signature
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }
        
        # This will raise an exception if verification fails
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        # Payment verified successfully - Create order
        username = session['user']
        # Fix: Use timestamp for unique ID to avoid collisions on server restart
        import time
        
        # Calculate total safely with type casting
        try:
            cart_total = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
            
            # Apply Coupon
            coupon_code = data.get('coupon_code')
            discount = 0
            if coupon_code:
                coupon = get_coupon(coupon_code)
                if coupon and cart_total >= coupon.get('min_spend', 0):
                    if coupon['discount_type'] == 'percentage':
                        discount = (cart_total * coupon['value']) / 100
                    else:
                        discount = coupon['value']
            
            total_amount = max(0, cart_total - discount)
        except (KeyError, ValueError, TypeError) as e:
            print(f"Error calculating total in verification: {e}")
            total_amount = 0 # Fallback or handle error
            
        order = {
            "id": f"ORD-{int(time.time() * 1000)}", 
            "user": username,
            "user_email": username, # Clarify field name
            "items": cart_items,
            "total": total_amount,
            "status": "Pending",
            "method": "Razorpay",
            "payment_id": razorpay_payment_id,
            "razorpay_order_id": razorpay_order_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().timestamp(),
            "collection_attempts": 0,
            "is_ready": False,
            "notification": None,
            "token": get_token_for_user(username)
        }
        
        # Save to Memory (for legacy support)
        ORDERS.append(order)
        
        # Save to Database
        save_order(order)
        
        # Record Coupon Usage
        if coupon_code:
            record_coupon_usage(username, coupon_code)
        
        # Update user profile in memory (for legacy support)
        # IMPORTANT: USER_PROFILES[username] may already exist as {} from dashboard/wallet init
        # so we must ensure all required keys exist, not just check "if username not in"
        if username not in USER_PROFILES:
            USER_PROFILES[username] = {}
        
        import random
        import string
        profile_defaults = {
            'points': 0,
            'tier': 'Bronze',
            'total_spent': 0,
            'referral_code': ''.join(random.choices(string.ascii_uppercase + string.digits, k=6)),
            'referred_by': ''
        }
        for key, default_val in profile_defaults.items():
            if key not in USER_PROFILES[username]:
                USER_PROFILES[username][key] = default_val
        
        USER_PROFILES[username]['total_spent'] = USER_PROFILES[username].get('total_spent', 0) + order['total']
        USER_PROFILES[username]['points'] = int(USER_PROFILES[username]['total_spent'] / 10)
        
        # Deduct Stock
        for item in cart_items:
            try:
                item_id = str(item.get('id', ''))
                qty_to_deduct = int(item.get('quantity', 0))
                product = next((p for p in PRODUCTS if str(p['id']) == item_id), None)
                if product:
                    product['stock'] = max(0, int(product.get('stock', 0)) - qty_to_deduct)
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not deduct stock for item {item.get('name')}: {e}")
        
        # Create notification
        notification = {
            'id': f'notif_{len(NOTIFICATIONS) + 1}',
            'user': username,
            'type': 'order',
            'title': 'Order Confirmed!',
            'message': f'Your order {order["id"]} has been placed successfully. Payment received via Razorpay.',
            'read': False,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        NOTIFICATIONS.append(notification)

        # Send Confirmation Email for Razorpay Purchase
        email_subject = f"Payment Confirmed: {order['id']}"
        email_body = f"""
Hello,

🎉 Your payment for order {order['id']} was successful!

Order Details:
----------------
Order ID: {order['id']}
Method: Razorpay
Total Paid: ₹{total_amount}

Items:
{chr(10).join([f"- {i['quantity']}x {i.get('name', 'Item')}" for i in cart_items])}

You will receive another notification once your order is ready for collection.

Thank you for choosing UniStore!
"""
        threading.Thread(target=send_email, args=(username, email_subject, email_body)).start()
        
        return jsonify({
            'success': True,
            'message': 'Payment verified successfully',
            'order_id': order['id']
        })
        
    except razorpay.errors.SignatureVerificationError:
        print("Payment verification failed: Invalid signature")
        return jsonify({
            'success': False,
            'message': 'Payment verification failed: Invalid signature'
        }), 400
    except Exception as e:
        print(f"Payment verification error: {e}")
        return jsonify({
            'success': False,
            'message': f"Internal Error: {str(e)}"
        }), 500

@app.route("/api/razorpay-webhook", methods=["POST"])
def razorpay_webhook():
    """Handle Razorpay webhooks for order processing"""
    try:
        # Verify webhook signature
        webhook_signature = request.headers.get("X-Razorpay-Signature")
        webhook_body = request.data.decode("utf-8")
        
        if RAZORPAY_WEBHOOK_SECRET and RAZORPAY_WEBHOOK_SECRET != 'your_webhook_secret_here':
            try:
                razorpay_client.utility.verify_webhook_signature(webhook_body, webhook_signature, RAZORPAY_WEBHOOK_SECRET)
            except razorpay.errors.SignatureVerificationError:
                print("Webhook signature verification failed")
                return "Invalid signature", 400
        
        # Process the event
        payload = request.json
        event = payload.get("event")
        
        if event in ["order.paid", "payment.captured"]:
            entity = payload.get("payload", {}).get("order", {}).get("entity") or \
                     payload.get("payload", {}).get("payment", {}).get("entity")
            
            if not entity: return "No entity found", 200
            
            razorpay_order_id = entity.get("id") or entity.get("order_id")
            razorpay_payment_id = entity.get("id") if event == "payment.captured" else entity.get("payment_id")
            
            # Idempotency check
            from database import get_order_by_razorpay_id, save_order
            if get_order_by_razorpay_id(razorpay_order_id):
                return "Order already processed", 200
                
            # Get data from notes
            notes = entity.get("notes", {})
            user_email = notes.get("user_email")
            cart_json = notes.get("cart")
            
            if not user_email or not cart_json:
                print(f"Webhook error: Missing notes in Razorpay order {razorpay_order_id}")
                return "Missing order notes", 200
                
            cart_items = json.loads(cart_json)
            total_amount = float(entity.get("amount", 0)) / 100
            
            # Create Order
            import time
            order = {
                "id": f"ORD-{int(time.time() * 1000)}", 
                "user": user_email,
                "user_email": user_email,
                "items": cart_items,
                "total": total_amount,
                "status": "Pending",
                "method": "Razorpay",
                "payment_id": razorpay_payment_id,
                "razorpay_order_id": razorpay_order_id,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": datetime.now().timestamp(),
                "collection_attempts": 0,
                "is_ready": False,
                "notification": None,
                "token": get_token_for_user(user_email)
            }
            
            ORDERS.append(order)
            save_order(order)
            print(f"Webhook: Order {order['id']} created for {user_email}")
            
        return "Webhook processed", 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return str(e), 500

@app.route("/api/user/wallet/create-order", methods=["POST"])
@login_required
def wallet_create_order():
    try:
        amount = float(request.json.get('amount', 0))
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Invalid amount'}), 400
            
        # Create Razorpay Order
        data = {
            "amount": int(amount * 100), # Amount in paise
            "currency": "INR",
            "receipt": f"wallet_topup_{int(datetime.now().timestamp())}",
            "notes": {
                "user_email": session['user'],
                "type": "wallet_topup"
            }
        }
        order = razorpay_client.order.create(data=data)
        
        return jsonify({
            'success': True,
            'order_id': order['id'],
            'amount': order['amount'],
            'currency': order['currency'],
            'key_id': RAZORPAY_KEY_ID
        })
    except Exception as e:
        print(f"Wallet Order Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/user/wallet/verify-payment", methods=["POST"])
@login_required
def wallet_verify_payment():
    try:
        data = request.json
        user_email = session['user']
        
        # Verify Signature
        params_dict = {
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        }
        razorpay_client.utility.verify_payment_signature(params_dict)
        
        # Add to Wallet
        amount = float(data.get('amount', 0))
        if user_email not in USER_PROFILES: USER_PROFILES[user_email] = {}
        
        current_bal = USER_PROFILES[user_email].get('wallet_balance', 0.0)
        new_bal = current_bal + amount
        USER_PROFILES[user_email]['wallet_balance'] = new_bal
        update_wallet_balance(user_email, new_bal)
        
        # Notification
        NOTIFICATIONS.append({
            "id": len(NOTIFICATIONS) + 1,
            "user": user_email,
            "message": f"Wallet verification successful! Added ₹{amount}. New Balance: ₹{new_bal}",
            "read": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        
        return jsonify({"success": True, "new_balance": new_bal})
        
    except razorpay.errors.SignatureVerificationError:
        return jsonify({'success': False, 'error': 'Invalid signature'}), 400
    except Exception as e:
        print(f"Wallet Verify Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/process-payment", methods=["POST"])
@login_required
def process_payment():
    """Handle Cash on Delivery and Wallet orders"""
    try:
        data = request.json
        cart_items = data.get('cart', [])
        method = data.get('method', 'Cash on Delivery')
        
        if not cart_items:
            return jsonify({'success': False, 'message': 'Cart is empty'}), 400
            
        # Create Order
        username = session['user']
        cart_total = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
        
        # Apply Coupon
        coupon_code = data.get('coupon_code')
        discount = 0
        if coupon_code:
            coupon = get_coupon(coupon_code)
            if coupon and cart_total >= coupon.get('min_spend', 0):
                if coupon['discount_type'] == 'percentage':
                    discount = (cart_total * coupon['value']) / 100
                else:
                    discount = coupon['value']
        
        total_amount = max(0, cart_total - discount)
        
        # Check Stock (skip print service items)
        for item in cart_items:
            if str(item['id']).startswith('PRINT-'):
                continue
            product = next((p for p in PRODUCTS if str(p['id']) == str(item['id'])), None)
            if not product:
                return jsonify({'success': False, 'message': f"Product {item.get('name', 'Item')} no longer available"}), 400
            if product['stock'] < int(item['quantity']):
                return jsonify({'success': False, 'message': f"Insufficient stock for {product['name']}. Only {product['stock']} left."}), 400
        
        # Check Wallet Balance if method is Wallet
        payment_status = "Pending"
        if method == "Wallet":
            if username not in USER_PROFILES: USER_PROFILES[username] = {}
            current_bal = USER_PROFILES[username].get('wallet_balance', 0.0)
            
            if current_bal < total_amount:
                return jsonify({'success': False, 'message': 'Insufficient wallet balance'}), 400
                
            # Deduct Balance
            new_bal = current_bal - total_amount
            USER_PROFILES[username]['wallet_balance'] = new_bal
            update_wallet_balance(username, new_bal)
            payment_status = "Pending"
        
        # Fix: Use millisecond precision for ID to prevent collisions
        import time
        order_id = f"ORD-{int(time.time() * 1000)}"
        
        order = {
            "id": order_id,
            "user": username,
            "user_email": username, # Keep consistent with DB schema expectation
            "items": cart_items,
            "total": total_amount,
            "status": payment_status if method == "Wallet" else "Pending",
            "method": method,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().timestamp(),
            "collection_attempts": 0,
            "token": get_token_for_user(username),
            "is_ready": False,
            "notification": None
        }
        
        # Save to DB
        from database import save_order
        if save_order(order):
            # Record Coupon Usage
            if coupon_code:
                record_coupon_usage(username, coupon_code)
            
            # Also append to in-memory list for legacy support if needed
            ORDERS.append(order) 
            
            # Deduct Stock
            for item in cart_items:
                product = next((p for p in PRODUCTS if str(p['id']) == str(item.get('id'))), None)
                if product:
                    product['stock'] = max(0, product['stock'] - int(item.get('quantity', 1)))
            
            # Send Confirmation Email for COD via unistore153 account
            email_subject = f"Order Placed: {order['id']}"
            email_body = f"""
Hello,

Your order {order['id']} has been placed successfully via {method} 🚚

Items:
{chr(10).join([f"- {i['quantity']}x {i.get('name', 'Item')}" for i in cart_items])}

Total: ₹{total_amount}

{'Please pay at the counter when collecting your order.' if method == 'Cash on Delivery' else 'Payment deducted from your UniStore Wallet.'}

Thank you,
College Store
"""
            threading.Thread(target=send_email, args=(username, email_subject, email_body)).start()
            
            return jsonify({'success': True, 'message': 'success', 'order_id': order['id']})
        else:
            return jsonify({'success': False, 'message': 'Failed to save order'}), 500
            
    except Exception as e:
        print(f"Payment Error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# ==============================
# Staff Dashboard Features API
# ==============================

@app.route("/api/staff/todos", methods=["GET"])
def get_todos():
    if 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    return jsonify(STAFF_TODOS)

@app.route("/api/staff/todos/add", methods=["POST"])
def add_todo():
    if 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    data = request.json
    text = data.get('text', '').strip()
    if not text:
        return jsonify({"success": False, "message": "Empty task"}), 400
    todo = {
        "id": len(STAFF_TODOS) + 1,
        "text": text,
        "completed": False,
        "created_by": session.get('staff', session.get('admin')),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    STAFF_TODOS.append(todo)
    return jsonify({"success": True, "todo": todo})

@app.route("/api/staff/todos/toggle", methods=["POST"])
def toggle_todo():
    if 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    todo_id = request.json.get('id')
    for t in STAFF_TODOS:
        if t['id'] == todo_id:
            t['completed'] = not t['completed']
            return jsonify({"success": True, "completed": t['completed']})
    return jsonify({"success": False}), 404

@app.route("/api/staff/todos/delete", methods=["POST"])
def delete_todo():
    if 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    global STAFF_TODOS
    todo_id = request.json.get('id')
    STAFF_TODOS = [t for t in STAFF_TODOS if t['id'] != todo_id]
    return jsonify({"success": True})

# Shift Management
@app.route("/api/staff/shift/status", methods=["GET"])
def shift_status():
    if 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    user = session.get('staff', session.get('admin'))
    shift = SHIFT_LOG.get(user, {"clocked_in": False, "clock_in_time": None, "history": []})
    return jsonify({"success": True, "shift": shift})

@app.route("/api/staff/shift/toggle", methods=["POST"])
def shift_toggle():
    if 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    user = session.get('staff', session.get('admin'))
    if user not in SHIFT_LOG:
        SHIFT_LOG[user] = {"clocked_in": False, "clock_in_time": None, "history": []}

    shift = SHIFT_LOG[user]
    now = datetime.now()

    if shift['clocked_in']:
        # Clock Out
        clock_in = datetime.strptime(shift['clock_in_time'], "%Y-%m-%d %H:%M:%S")
        duration = str(now - clock_in).split('.')[0]  # Remove microseconds
        shift['history'].append({
            "date": now.strftime("%Y-%m-%d"),
            "clock_in": shift['clock_in_time'],
            "clock_out": now.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": duration
        })
        shift['clocked_in'] = False
        shift['clock_in_time'] = None
        add_audit_log("Clock Out", user, f"Shift duration: {duration}")
        return jsonify({"success": True, "action": "clocked_out", "duration": duration})
    else:
        # Clock In
        shift['clocked_in'] = True
        shift['clock_in_time'] = now.strftime("%Y-%m-%d %H:%M:%S")
        add_audit_log("Clock In", user)
        return jsonify({"success": True, "action": "clocked_in", "time": shift['clock_in_time']})

# Live Chat
@app.route("/api/chat/messages", methods=["GET"])
def get_chat_messages():
    if 'user' not in session and 'staff' not in session and 'admin' not in session:
        return jsonify([])
    # Return last 50 messages
    return jsonify(CHAT_MESSAGES[-50:])

@app.route("/api/chat/send", methods=["POST"])
def send_chat_message():
    if 'user' not in session and 'staff' not in session and 'admin' not in session:
        return jsonify({"success": False}), 403
    data = request.json
    msg_text = data.get('message', '').strip()
    if not msg_text:
        return jsonify({"success": False}), 400

    role = 'staff' if 'staff' in session else ('admin' if 'admin' in session else 'user')
    sender = session.get('staff', session.get('admin', session.get('user')))

    msg = {
        "id": len(CHAT_MESSAGES) + 1,
        "sender": sender,
        "sender_role": role,
        "message": msg_text,
        "timestamp": datetime.now().strftime("%H:%M")
    }
    CHAT_MESSAGES.append(msg)
    if len(CHAT_MESSAGES) > 200:
        CHAT_MESSAGES.pop(0)
    return jsonify({"success": True, "msg": msg})

# Low Stock
@app.route("/api/staff/low-stock", methods=["GET"])
def get_low_stock():
    if 'staff' not in session and 'admin' not in session:
        return jsonify([])
    low = [p for p in PRODUCTS if p.get('stock', 0) < LOW_STOCK_THRESHOLD and not p.get('is_service')]
    return jsonify(low)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Simple run - Gunicorn will handle production binding
    app.run(host="0.0.0.0", port=port, debug=True)
