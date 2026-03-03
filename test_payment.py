"""
Quick test script to verify Razorpay integration is working
"""

import requests
import json

BASE_URL = "http://127.0.0.1:5000"

print("🧪 Testing UniStore Payment Integration...\n")

# Test 1: Check if server is running
print("1️⃣ Testing server connection...")
try:
    response = requests.get(BASE_URL)
    if response.status_code == 200:
        print("   ✅ Server is running!")
    else:
        print(f"   ❌ Server returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Cannot connect to server: {e}")
    print("   💡 Make sure the server is running: python app.py")
    exit(1)

# Test 2: Check if shop page loads
print("\n2️⃣ Testing shop page...")
try:
    response = requests.get(f"{BASE_URL}/shop")
    if response.status_code == 200:
        print("   ✅ Shop page loads!")
    else:
        print(f"   ⚠️ Shop returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Check if cart page loads
print("\n3️⃣ Testing cart page...")
try:
    response = requests.get(f"{BASE_URL}/cart")
    if response.status_code in [200, 302]:  # 302 might redirect to login
        print("   ✅ Cart page accessible!")
    else:
        print(f"   ⚠️ Cart returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 4: Check if payment page loads (might need login)
print("\n4️⃣ Testing payment page...")
try:
    response = requests.get(f"{BASE_URL}/payment")
    if response.status_code in [200, 302]:  # 302 redirects to login (expected)
        if response.status_code == 302:
            print("   ✅ Payment page exists (requires login)")
        else:
            print("   ✅ Payment page loads!")
    else:
        print(f"   ⚠️ Payment returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 5: Check if products API works
print("\n5️⃣ Testing products API...")
try:
    response = requests.get(f"{BASE_URL}/api/products")
    if response.status_code == 200:
        products = response.json()
        print(f"   ✅ Products API works! Found {len(products)} products")
    else:
        print(f"   ❌ Products API returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 6: Verify Razorpay configuration
print("\n6️⃣ Checking Razorpay configuration...")
try:
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
        if 'rzp_test_SDJuJnLmddAF0C' in content:
            print("   ✅ Razorpay Test Key ID found in app.py")
        else:
            print("   ❌ Razorpay Key ID not found!")
        
        if 'import razorpay' in content:
            print("   ✅ Razorpay SDK imported")
        else:
            print("   ❌ Razorpay SDK not imported!")
        
        if 'razorpay_client' in content:
            print("   ✅ Razorpay client initialized")
        else:
            print("   ❌ Razorpay client not initialized!")
            
        if '/api/create-razorpay-order' in content:
            print("   ✅ Razorpay order creation endpoint exists")
        else:
            print("   ❌ Order creation endpoint missing!")
            
        if '/api/verify-payment' in content:
            print("   ✅ Payment verification endpoint exists")
        else:
            print("   ❌ Verification endpoint missing!")
except Exception as e:
    print(f"   ❌ Error reading app.py: {e}")

# Test 7: Check if payment.html template exists
print("\n7️⃣ Checking payment template...")
try:
    with open('templates/payment.html', 'r', encoding='utf-8') as f:
        content = f.read()
        if 'razorpay' in content.lower():
            print("   ✅ Payment template exists with Razorpay integration")
        else:
            print("   ⚠️ Payment template exists but no Razorpay found")
        
        if 'checkout.razorpay.com' in content:
            print("   ✅ Razorpay checkout script included")
        else:
            print("   ❌ Razorpay checkout script missing!")
except FileNotFoundError:
    print("   ❌ Payment template not found!")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "="*50)
print("✅ All tests completed!")
print("="*50)

print("\n📝 Next Steps:")
print("1. Open your browser: http://127.0.0.1:5000")
print("2. Go to shop and add items to cart")
print("3. Click 'Checkout Securely'")
print("4. Try Razorpay payment with test card:")
print("   Card: 4111 1111 1111 1111")
print("   CVV: 123")
print("   Expiry: 12/28")
print("\n🎉 Happy testing!")
