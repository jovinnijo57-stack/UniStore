import sqlite3

def check_schema():
    conn = sqlite3.connect('unistore.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(orders)")
    columns = cursor.fetchall()
    print("Orders Table Columns:")
    for col in columns:
        print(f"Index: {col[0]}, Name: {col[1]}, Type: {col[2]}")
    conn.close()

if __name__ == '__main__':
    check_schema()
