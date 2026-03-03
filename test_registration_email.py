import requests
import random
import string

BASE_URL = "http://127.0.0.1:5000"

def test_registration_email():
    # Generate random user
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"test_welcome_{rand_suffix}@test.com"
    name = f"Welcome User {rand_suffix}"
    password = "password123"
    
    print(f"1. Registering new user: {email}")
    
    resp = requests.post(f"{BASE_URL}/user/register", json={
        "name": name,
        "email": email,
        "password": password
    })
    
    print(f"Response: {resp.status_code}")
    print(f"Body: {resp.text}")
    
    if resp.status_code == 200:
        print("✅ Registration successful. Email thread should have started.")
    else:
        print("❌ Registration failed.")

if __name__ == "__main__":
    try:
        test_registration_email()
    except Exception as e:
        print(f"Error: {e}")
