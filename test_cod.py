import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_cod():
    s = requests.Session()
    
    # Login
    print("1. Logging in...")
    s.post(f"{BASE_URL}/user/login", json={"email": "test@test.com", "password": "password"})
    
    # Attempt COD payment
    print("2. Attempting COD payment...")
    cart = [{"id": 1, "name": "Notebook", "price": 40, "quantity": 1}]
    
    resp = s.post(f"{BASE_URL}/api/process-payment", json={"cart": cart, "method": "Cash on Delivery"})
    print(f"Response: {resp.status_code}")
    print(f"Body: {resp.text}")
    
    if resp.status_code == 404:
        print("❌ Endpoint /api/process-payment NOT FOUND")
    elif resp.status_code == 500:
        print("❌ Internal Server Error")
    elif resp.status_code == 200:
        print("✅ Success")

if __name__ == "__main__":
    try:
        test_cod()
    except Exception as e:
        print(f"Error: {e}")
