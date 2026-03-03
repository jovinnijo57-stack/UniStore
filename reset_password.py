import sqlite3
from werkzeug.security import generate_password_hash

def reset_password(email, new_password):
    try:
        conn = sqlite3.connect('unistore.db')
        cursor = conn.cursor()
        
        print(f"Resetting password for: {email}...")
        
        # Generate new hash
        hashed_pw = generate_password_hash(new_password)
        
        cursor.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_pw, email))
        
        if cursor.rowcount > 0:
            print(f"✅ Password successfully updated for {email}")
            conn.commit()
        else:
            print("❌ User not found, no changes made.")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_password("nijojesvin98@gmail.com", "12345678")
