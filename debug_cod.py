import sqlite3
import json
from datetime import datetime
from database import get_db_connection, save_order, init_database

def debug_db():
    print("1. Checking DB Schema...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(orders)")
    columns = [row['name'] for row in cursor.fetchall()]
    print(f"Columns in 'orders' table: {columns}")
    
    if 'pickup_time' not in columns:
        print("❌ 'pickup_time' column MISSING!")
    else:
        print("✅ 'pickup_time' column exists.")

    conn.close()
    
    print("\n2. Testing save_order with dummy data...")
    order = {
        "id": "DEBUG-001",
        "user": "test@debug.com", # Ensure this user exists or FK might fail? 
        # Schema: FOREIGN KEY (user_email) REFERENCES users (email)
        # So user MUST exist.
        "items": [{"name": "Test Item", "price": 100, "quantity": 1}],
        "total": 100.0,
        "status": "Pending",
        "method": "Cash on Delivery",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": datetime.now().timestamp(),
        "collection_attempts": 0,
        "is_ready": False,
        "notification": None,
        # pickup_time is optional, let's omit it to see if it defaults correctly
    }
    
    # We need a user first
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (name, email, password) VALUES (?, ?, ?)", ("Debug User", "test@debug.com", "hash"))
    conn.commit()
    conn.close()
    
    success = save_order(order)
    if success:
        print("✅ save_order succeeded!")
    else:
        print("❌ save_order FAILED!")
        # Since save_order catches exception and prints to stdout, we should see it.

if __name__ == "__main__":
    try:
        debug_db()
    except Exception as e:
        print(f"Debug script error: {e}")
