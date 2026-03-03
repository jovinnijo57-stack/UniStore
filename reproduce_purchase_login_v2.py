import requests
import random
import string

BASE_URL = "http://127.0.0.1:5000"

def test_purchase_email_mismatch():
    s = requests.Session()
    
    # 1. Register & Login as User A
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email_a = f"user_a_{rand_suffix}@test.com"
    password = "password123"
    
    print(f"1. Registering User A: {email_a}")
    s.post(f"{BASE_URL}/user/register", json={
        "name": "User A", "email": email_a, "password": password
    })
    
    # 2. Place Order using User B's email (Simulating checkout override)
    # Note: The API currently takes 'user' from session, but let's see if 
    # passing 'user_email' in the cart or payload affects anything if the backend logic uses it.
    
    # Actually, looking at the code, process_payment uses session['user']. 
    # But maybe the frontend allows changing contact info?
    # Let's try to find if there's any flow where email is passed in payload.
    
    print("2. Placing Order...")
    # Attempting to inject a different email if the API accepts it (e.g. legacy fields)
    cart = [{ "id": 1, "name": "Test Item", "price": 100, "quantity": 1 }]
    resp = s.post(f"{BASE_URL}/api/process-payment", json={
        "cart": cart, 
        "method": "Cash on Delivery",
        "email": "different_email@test.com", # Trying to confuse the system
        "user_email": "different_email@test.com"
    })
    
    if resp.status_code != 200:
        print(f"❌ Order placement failed: {resp.text}")
        return
    print("✅ Order placed")
    
    # 3. Logout
    print("3. Logging out...")
    s.get(f"{BASE_URL}/user/logout")
    
    # 4. Attempt Re-Login as User A
    print(f"4. Attempting Re-Login as {email_a}...")
    resp = s.post(f"{BASE_URL}/user/login", json={
        "email": email_a, "password": password
    })
    
    print(f"Login Response: {resp.status_code}")
    print(f"Login Body: {resp.text}")
    
    if resp.status_code == 200 and resp.json().get("success"):
        print("✅ Login successful after purchase with potential email mismatch")
    else:
        print("❌ Login FAILED after purchase")

if __name__ == "__main__":
    try:
        test_purchase_email_mismatch()
    except Exception as e:
        print(f"Error: {e}")
