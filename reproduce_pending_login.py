import requests
import random
import string
import json

BASE_URL = "http://127.0.0.1:5000"

def test_purchase_pending_flow():
    s = requests.Session()
    
    # 1. Register
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"pending_user_{rand_suffix}@test.com"
    password = "password123"
    
    print(f"1. Registering: {email}")
    s.post(f"{BASE_URL}/user/register", json={
        "name": "Pending User", "email": email, "password": password
    })
    
    # 2. Login to be sure (though register auto-logs in now)
    s.post(f"{BASE_URL}/user/login", json={"email": email, "password": password})

    # 3. Place Order (COD -> Pending)
    print("3. Placing COD Order...")
    # Complex cart to test JSON serialization
    cart = [
        { "id": 1, "name": "Item A", "price": 50.5, "quantity": 2 },
        { "id": 2, "name": "Item B", "price": 100, "quantity": 1 }
    ]
    resp = s.post(f"{BASE_URL}/api/process-payment", json={
        "cart": cart, 
        "method": "Cash on Delivery"
    })
    
    if resp.status_code != 200:
        print(f"❌ Order placement failed: {resp.text}")
        return
    print("✅ Order placed")
    
    # 4. Logout
    print("4. Logging out...")
    s.get(f"{BASE_URL}/user/logout")
    
    # 5. Attempt Re-Login
    print("5. Attempting Re-Login...")
    resp = s.post(f"{BASE_URL}/user/login", json={
        "email": email, "password": password
    })
    
    print(f"Login Response: {resp.status_code}")
    
    if resp.status_code == 200 and resp.json().get("success"):
        print("✅ Login successful after COD purchase")
    else:
        print(f"❌ Login FAILED after COD purchase: {resp.text}")

if __name__ == "__main__":
    try:
        test_purchase_pending_flow()
    except Exception as e:
        print(f"Error: {e}")
