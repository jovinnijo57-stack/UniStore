import requests
import random
import string

BASE_URL = "http://127.0.0.1:5000"

def test_purchase_login_flow():
    s = requests.Session()
    
    # 1. Register & Auto-Login
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"buyer_{rand_suffix}@test.com"
    name = f"Buyer {rand_suffix}"
    password = "password123"
    
    print(f"1. Registering: {email}")
    resp = s.post(f"{BASE_URL}/user/register", json={
        "name": name, "email": email, "password": password
    })
    
    if resp.status_code != 200:
        print("❌ Registration failed")
        return

    # 2. Place Order (COD)
    print("2. Placing Order...")
    cart = [{ "id": 1, "name": "Test Item", "price": 100, "quantity": 1 }]
    resp = s.post(f"{BASE_URL}/api/process-payment", json={
        "cart": cart, "method": "Cash on Delivery"
    })
    
    if resp.status_code != 200:
        print(f"❌ Order placement failed: {resp.text}")
        return
    print("✅ Order placed successfully")
    
    # 3. Logout
    print("3. Logging out...")
    s.get(f"{BASE_URL}/user/logout")
    
    # 4. Attempt Re-Login
    print("4. Attempting Re-Login...")
    resp = s.post(f"{BASE_URL}/user/login", json={
        "email": email, "password": password
    })
    
    print(f"Login Response: {resp.status_code}")
    print(f"Login Body: {resp.text}")
    
    if resp.status_code == 200 and resp.json().get("success"):
        print("✅ Login successful after purchase")
    else:
        print("❌ Login FAILED after purchase")

if __name__ == "__main__":
    try:
        test_purchase_login_flow()
    except Exception as e:
        print(f"Error: {e}")
