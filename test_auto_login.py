import requests
import random
import string

BASE_URL = "http://127.0.0.1:5000"

def test_auto_login():
    # Generate random user
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"auto_login_{rand_suffix}@test.com"
    name = f"Auto Login User {rand_suffix}"
    password = "password123"
    
    print(f"1. Registering new user: {email}")
    
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/user/register", json={
        "name": name,
        "email": email,
        "password": password
    })
    
    print(f"Response: {resp.status_code}")
    print(f"Body: {resp.text}")
    
    if resp.status_code != 200:
        print("❌ Registration failed")
        return

    data = resp.json()
    
    # Check for redirect
    if data.get("redirect"):
        print(f"✅ Redirect URL present: {data['redirect']}")
    else:
        print("❌ Redirect URL MISSING (Auto-login likely failed)")
        
    # Check for session cookie
    if s.cookies.get("session"):
        print("✅ Session cookie present")
    else:
        print("❌ Session cookie MISSING")

    # Try accessing dashboard
    dashboard_resp = s.get(f"{BASE_URL}/user/dashboard")
    if dashboard_resp.status_code == 200:
        print("✅ Dashboard access successful")
    else:
        print(f"❌ Dashboard access failed: {dashboard_resp.status_code}")

if __name__ == "__main__":
    try:
        test_auto_login()
    except Exception as e:
        print(f"Error: {e}")
