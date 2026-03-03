import requests

BASE_URL = "http://127.0.0.1:5000"

def test_login_error():
    s = requests.Session()
    
    # 1. Try Invalid Login
    print("1. Attempting Invalid Login...")
    resp = s.post(f"{BASE_URL}/user/login", json={
        "email": "wrong@test.com", 
        "password": "wrongpassword"
    })
    print(f"Invalid Login Response: {resp.status_code}")
    print(f"Invalid Login Body: {resp.text}")
    
    # 2. Try Valid Login (using previously registered user)
    print("2. Attempting Valid Login...")
    # Register first to be sure
    requests.post(f"{BASE_URL}/user/register", json={
        "name": "Login Error Test", 
        "email": "test_login_error@test.com", 
        "password": "password"
    })
    
    resp = s.post(f"{BASE_URL}/user/login", json={
        "email": "test_login_error@test.com", 
        "password": "password"
    })
    print(f"Valid Login Response: {resp.status_code}")
    print(f"Valid Login Body: {resp.text}")
    
    if resp.status_code == 200:
        print("✅ Correctly received 200 OK for valid login")
        data = resp.json()
        if data.get("redirect"):
             print(f"✅ Redirect URL present: {data['redirect']}")
        else:
             print("❌ Redirect URL MISSING in success response")
    else:
        print(f"❌ Failed to login with valid credentials. Status: {resp.status_code}")

if __name__ == "__main__":
    try:
        test_login_error()
    except Exception as e:
        print(f"Error: {e}")
