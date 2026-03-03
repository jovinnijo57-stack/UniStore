import requests
import sys

BASE_URL = "http://127.0.0.1:5000"
EMAIL = "test@test.com"
PASSWORD = "password"

def run_test():
    s = requests.Session()
    
    # 0. Ensure user exists (register if needed)
    print("0. Registering user to ensure existence...")
    reg_data = {"name": "Test", "email": EMAIL, "password": PASSWORD}
    s.post(f"{BASE_URL}/user/register", json=reg_data)
    
    # 1. Login
    print("\n1. Logging in...")
    login_data = {"email": EMAIL, "password": PASSWORD}
    resp = s.post(f"{BASE_URL}/user/login", json=login_data)
    print(f"Login Status: {resp.status_code}")
    print(f"Login Response: {resp.text}")
    
    if not resp.json().get("success"):
        print("Initial login failed!")
        return
        
    # 2. Access Dashboard
    print("\n2. Accessing Dashboard...")
    resp = s.get(f"{BASE_URL}/user/dashboard")
    print(f"Dashboard Status: {resp.status_code}")
    # Check if we got redirected to login
    if "/login" in resp.url and "/user/dashboard" not in resp.url:
        print("FAILED: Redirected to login page instead of dashboard")
    else:
        print("SUCCESS: Accessed dashboard")

    # 3. Logout
    print("\n3. Logging out...")
    resp = s.get(f"{BASE_URL}/logout")
    print(f"Logout Status: {resp.status_code}")
    
    # 4. Login again
    print("\n4. Logging in AGAIN...")
    resp = s.post(f"{BASE_URL}/user/login", json=login_data)
    print(f"Login #2 Status: {resp.status_code}")
    print(f"Login #2 Response: {resp.text}")
    
    if not resp.json().get("success"):
        print("Second login failed!")
        return

    # 5. Access Dashboard again
    print("\n5. Accessing Dashboard AGAIN...")
    resp = s.get(f"{BASE_URL}/user/dashboard")
    print(f"Dashboard #2 Status: {resp.status_code}")
    
    if "/login" in resp.url and "/user/dashboard" not in resp.url:
         print("FAILED: Redirected to login page on second attempt")
    else:
         print("SUCCESS: Accessed dashboard on second attempt")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"Error: {e}")
