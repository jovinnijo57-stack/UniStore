"""
Detailed test to find template error
"""
from flask import Flask, render_template
import traceback

app = Flask(__name__)
app.secret_key = 'test-key'

# Mock data
ORDERS = [{
    "id": "ORD-1001",
    "user": "test@user.com",
    "items": [{"name": "Notebook", "quantity": 2, "price": 40}],
    "total": 80,
    "status": "Paid",
    "method": "UPI",
    "date": "2026-02-07",
    "collection_attempts": 0,
    "is_ready": False,
    "notification": None
}]

PRINT_JOBS = []
STORE_CONFIG = {"is_open": True, "upi_id": "test@upi", "gpay_qr_url": "http://example.com"}
PRODUCTS = []
FEEDBACK = []

@app.route('/test')
def test_staff():
    try:
        return render_template("staff_dashboard.html", 
                             print_jobs=PRINT_JOBS,
                             orders=ORDERS,
                             store_config=STORE_CONFIG,
                             products=PRODUCTS,
                             feedbacks=FEEDBACK)
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return f"Error rendering template: {str(e)}", 500

if __name__ == '__main__':
    print("Testing staff dashboard template...")
    with app.test_client() as client:
        response = client.get('/test')
        if response.status_code == 200:
            print("✓ Template renders successfully!")
        else:
            print(f"✗ Error: {response.status_code}")
