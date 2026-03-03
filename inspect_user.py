import sqlite3

def inspect_user(email):
    try:
        conn = sqlite3.connect('unistore.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print(f"Searching for user: {email}...")
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if user:
            print("✅ User found!")
            print(f"ID: {user['id']}")
            print(f"Name: {user['name']}")
            print(f"Email: {user['email']}")
            print(f"Password Hash (first 20 chars): {user['password'][:20]}...")
            
            # Check profile too
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user['id'],))
            profile = cursor.fetchone()
            if profile:
                print("✅ Profile found:")
                print(dict(profile))
            else:
                print("❌ Profile MISSING")
        else:
            print("❌ User NOT found in database.")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_user("nijojesvin98@gmail.com")
