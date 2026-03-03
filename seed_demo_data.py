"""
Demo Data Seeding Script for UniStore Enhanced Dashboard
Run this after starting the app to populate with sample data
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:5000"

def seed_demo_data():
    print("🌱 Seeding demo data for UniStore Dashboard...")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # 1. Register and login a demo user
    print("\n1️⃣ Creating demo user...")
    try:
        # Login to create session
        login_data = {
            "email": "demo@unistore.com",
            "password": "demo123"
        }
        response = session.post(f"{BASE_URL}/user/login", json=login_data)
        print(f"   ✓ Demo user logged in: demo@unistore.com")
    except Exception as e:
        print(f"   ⚠️ Login: {e}")
    
    # 2. Create sample orders with different statuses
    print("\n2️⃣ Creating sample orders...")
    sample_orders = [
        {
            "cart": [
                {"name": "Premium Notebook (200 pgs)", "price": 40.00, "quantity": 2},
                {"name": "Ballpoint Pen (Blue)", "price": 5.00, "quantity": 5}
            ],
            "method": "UPI"
        },
        {
            "cart": [
                {"name": "Scientific Calculator", "price": 450.00, "quantity": 1}
            ],
            "method": "Card"
        },
        {
            "cart": [
                {"name": "A4 Size Paper (500 Sheets)", "price": 350.00, "quantity": 1},
                {"name": "Pastel Highlighters (Set of 6)", "price": 85.00, "quantity": 3}
            ],
            "method": "UPI"
        },
        {
            "cart": [
                {"name": "Geometry Set", "price": 65.00, "quantity": 1},
                {"name": "Metal Ruler (30cm)", "price": 25.00, "quantity": 2}
            ],
            "method": "Cash on Delivery"
        },
        {
            "cart": [
                {"name": "Desk Organizer", "price": 220.00, "quantity": 1}
            ],
            "method": "UPI"
        }
    ]
    
    for idx, order_data in enumerate(sample_orders, 1):
        try:
            response = session.post(f"{BASE_URL}/api/process-payment", json=order_data)
            if response.status_code == 200:
                print(f"   ✓ Order {idx} created: ₹{sum(item['price'] * item['quantity'] for item in order_data['cart'])}")
        except Exception as e:
            print(f"   ⚠️ Order {idx}: {e}")
    
    # 3. Create sample wishlist items
    print("\n3️⃣ Adding items to wishlist...")
    wishlist_items = [1, 4, 7, 10]  # Product IDs
    for product_id in wishlist_items:
        try:
            response = session.post(f"{BASE_URL}/api/wishlist/add", json={"product_id": product_id})
            if response.status_code == 200:
                print(f"   ✓ Added product #{product_id} to wishlist")
        except Exception as e:
            print(f"   ⚠️ Wishlist item {product_id}: {e}")
    
    # 4. Create sample support ticket
    print("\n4️⃣ Creating sample support ticket...")
    try:
        ticket_data = {
            "subject": "Question about print service",
            "message": "Hi, I'd like to know the turnaround time for print jobs during exam season. Thanks!",
            "priority": "Medium"
        }
        response = session.post(f"{BASE_URL}/api/support/create-ticket", json=ticket_data)
        if response.status_code == 200:
            print(f"   ✓ Support ticket created")
    except Exception as e:
        print(f"   ⚠️ Support ticket: {e}")
    
    # 5. Submit sample feedback
    print("\n5️⃣ Submitting sample feedback...")
    try:
        feedback_data = {
            "order_id": "ORD-1001",
            "rating": 5,
            "comment": "Excellent service! Fast delivery and great quality products."
        }
        response = session.post(f"{BASE_URL}/api/submit-feedback", json=feedback_data)
        if response.status_code == 200:
            print(f"   ✓ Feedback submitted")
    except Exception as e:
        print(f"   ⚠️ Feedback: {e}")
    
    print("\n✅ Demo data seeding complete!")
    print("\n📱 Now open your browser and navigate to:")
    print("   http://127.0.0.1:5000")
    print("\n🔐 Login credentials:")
    print("   Email: demo@unistore.com")
    print("   Password: demo123")
    print("\n🎉 Explore the enhanced dashboard with all the sample data!")

if __name__ == "__main__":
    print("=" * 60)
    print("  UniStore Enhanced Dashboard - Demo Data Seeder")
    print("=" * 60)
    seed_demo_data()
