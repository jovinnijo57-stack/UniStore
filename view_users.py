"""
Script to view users in the database
"""
import sqlite3

def view_users():
    """Display all users in the database"""
    try:
        conn = sqlite3.connect('unistore.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, email, created_at FROM users")
        users = cursor.fetchall()
        
        print("\n" + "="*70)
        print("📋 REGISTERED USERS")
        print("="*70)
        
        if not users:
            print("\nNo users found in database.")
        else:
            print(f"\nTotal Users: {len(users)}\n")
            print(f"{'ID':<5} {'Name':<25} {'Email':<30} {'Created At':<20}")
            print("-"*70)
            
            for user in users:
                user_id, name, email, created_at = user
                print(f"{user_id:<5} {name:<25} {email:<30} {created_at:<20}")
        
        print("="*70 + "\n")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    view_users()
