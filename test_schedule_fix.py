import requests
import time

BASE_URL = "http://127.0.0.1:5000"

def test_schedule_fix():
    s = requests.Session()
    
    # 1. Login as Staff
    print("1. Logging in as Staff...")
    s.post(f"{BASE_URL}/staff/login", json={"email": "staff@in", "password": "staff123"})
    
    # 2. Schedule Order (Simulated ID)
    # We need a valid order ID. Let's use the one from test_cod.py if it exists, or create one.
    # Actually, let's just use a fake ID and see if we get past the parsing error.
    # If the parsing logic is before "Order not found", it might crash.
    # But looking at the code:
    # 1. Validation (ID/Time present?)
    # 2. Find Order (If not found -> 404)
    # 3. Update Status
    # 4. Calculate End Time (This is where it crashed)
    
    # So we MUST have a valid order to reach the crashing line.
    
    # Let's create a user and order first.
    user_email = "test_sched_fix@test.com"
    requests.post(f"{BASE_URL}/user/register", json={"name": "Test Sched", "email": user_email, "password": "password"})
    s_user = requests.Session()
    s_user.post(f"{BASE_URL}/user/login", json={"email": user_email, "password": "password"})
    
    # Create COD Order
    print("2. Creating a new COD order...")
    cart = [{"id": 1, "name": "Notebook", "price": 40, "quantity": 1}]
    resp = s_user.post(f"{BASE_URL}/api/process-payment", json={
        "cart": cart,
        "total": 40,
        "method": "Cash on Delivery"
    })
    
    if resp.status_code != 200:
        print(f"Failed to create order: {resp.text}")
        return
        
    order_id = resp.json().get('order_id')
    print(f"   Order ID: {order_id}")
    
    # 3. Schedule Order with "Today, " prefix
    print("3. Attempting to schedule with 'Today, 14:30'...")
    resp = s.post(f"{BASE_URL}/api/staff/schedule-order", json={
        "id": order_id,
        "time": "Today, 14:30"
    })
    
    print(f"Response: {resp.status_code} - {resp.text}")
    
    if resp.status_code == 200:
        print("✅ Success! Date parsing works.")
    else:
        print("❌ Failed.")

if __name__ == "__main__":
    try:
        test_schedule_fix()
    except Exception as e:
        print(f"Error: {e}")
