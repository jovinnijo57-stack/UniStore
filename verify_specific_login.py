import requests

BASE_URL = "http://127.0.0.1:5000"

def verify_specific_login():
    s = requests.Session()
    email = "nijojesvin98@gmail.com"
    password = "12345678"
    
    print(f"Attempting login for {email} with password '{password}'...")
    
    resp = s.post(f"{BASE_URL}/user/login", json={
        "email": email, "password": password
    })
    
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200 and resp.json().get("success"):
        print("✅ Login SUCCESSFUL!")
    else:
        print("❌ Login FAILED.")

if __name__ == "__main__":
    verify_specific_login()
