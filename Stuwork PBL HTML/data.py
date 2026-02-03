import sqlite3
import os
from cryptography.fernet import Fernet

# --- 1. จัดการเรื่องกุญแจลับ (Key) ---
def load_or_create_key():
    if not os.path.exists("secret.key"):
        key = Fernet.generate_key()
        with open("secret.key", "wb") as key_file:
            key_file.write(key)
    return open("secret.key", "rb").read()

key = load_or_create_key()
cipher = Fernet(key)

# --- 2. จัดการฐานข้อมูล (Database) ---
def init_db():
    conn = sqlite3.connect("my_passwords.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    return conn

# --- 3. ฟังก์ชันหลัก: บันทึก และ อ่านข้อมูล ---
def add_password(service, username, password):
    conn = init_db()
    cursor = conn.cursor()
    # เข้ารหัสผ่านก่อนบันทึก
    encrypted_pw = cipher.encrypt(password.encode()).decode()
    cursor.execute("INSERT INTO accounts (service, username, password) VALUES (?, ?, ?)", 
                   (service, username, encrypted_pw))
    conn.commit()
    conn.close()
    print(f"✅ บันทึกข้อมูลสำหรับ {service} เรียบร้อยแล้ว!")

def view_passwords():
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT service, username, password FROM accounts")
    rows = cursor.fetchall()
    
    print("\n--- รายการรหัสผ่านของคุณ ---")
    for row in rows:
        service, user, encrypted_pw = row
        # ถอดรหัสเพื่อแสดงผล
        decrypted_pw = cipher.decrypt(encrypted_pw.encode()).decode()
        print(f"บริการ: {service} | Username/Gmail: {user} | Password: {decrypted_pw}")
    conn.close()

# --- 4. ทดลองใช้งาน ---
# บันทึกข้อมูลใหม่
add_password("Gmail", "example@gmail.com", "my-very-secret-123")
add_password("Facebook", "thailand_user", "fb-password-456")

# เรียกดูข้อมูลทั้งหมด
view_passwords()