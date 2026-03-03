import requests
from app import app
from database import create_user, verify_user, init_database
import json

def test_login_logic():
    print("--- Testing Internal Logic ---")
    # Ensure DB is ready
    init_database()
    
    email = "test_login@example.com"
    password = "password123"
    name = "Test User"
    
    # 1. Create User
    print(f"Creating user: {email}")
    result = create_user(name, email, password)
    print(f"Create Result: {result}")
    
    # 2. Verify User
    print(f"Verifying user: {email}")
    verify_result = verify_user(email, password)
    print(f"Verify Result: {verify_result}")
    
    if verify_result['success']:
        print("✅ Internal logic works")
    else:
        print("❌ Internal logic failed")

def test_api_login():
    print("\n--- Testing API Logic ---")
    with app.test_client() as client:
        email = "api_test@example.com"
        password = "password123"
        
        # Register via API (optional, but good to test)
        client.post('/user/register', json={
            "name": "API Tester",
            "email": email,
            "password": password
        })
        
        # Login
        response = client.post('/user/login', json={
            "email": email,
            "password": password
        })
        
        print(f"Login Status: {response.status_code}")
        print(f"Login Response: {response.json}")
        
        if response.status_code == 200 and response.json.get('success'):
            print("✅ API Login works")
            # Check session cookies
            print(f"Cookies: {client.cookie_jar}")
        else:
            print("❌ API Login failed")

if __name__ == "__main__":
    test_login_logic()
    test_api_login()
