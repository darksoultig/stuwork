"""
Stuwork Backend API Server
Secure AI Grading System with Gemini API
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import base64
import hashlib
import secrets
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, origins=["*"])  # Allow all origins for development
app.secret_key = os.getenv('SECRET_KEY', 'stuwork-fallback-key')

# Configure Gemini API
GEMINI_API_KEY = os.getenv('AIzaSyAHHhUePjYMEh70320VU-1dxNQj72WqrkE')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    model = None
    print("WARNING: GEMINI_API_KEY not set!")

# Database functions
def get_db():
    conn = sqlite3.connect('stuwork.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table with roles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'teacher', 'admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Work submissions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            teacher_id INTEGER,
            subject TEXT NOT NULL,
            image_data TEXT,
            full_score INTEGER DEFAULT 100,
            ai_score INTEGER,
            final_score INTEGER,
            ai_feedback TEXT,
            teacher_notes TEXT,
            graded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized!")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# API Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'gemini_configured': model is not None})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'student')
    
    if not all([name, email, password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if role not in ['student', 'teacher', 'admin']:
        return jsonify({'error': 'Invalid role'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
            (name, email, hash_password(password), role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'success': True,
            'user': {'id': user_id, 'name': name, 'email': email, 'role': role}
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Email already exists'}), 409

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    
    if not all([email, password, role]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, email, role FROM users WHERE email = ? AND password_hash = ? AND role = ?',
        (email, hash_password(password), role)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'success': True,
            'user': {'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role']}
        })
    else:
        return jsonify({'error': 'Invalid credentials or role'}), 401

@app.route('/api/grade', methods=['POST'])
def grade_work():
    """AI Grading endpoint - only for teachers"""
    if not model:
        return jsonify({'error': 'AI service not configured'}), 503
    
    data = request.json
    image_base64 = data.get('image')
    subject = data.get('subject', 'General')
    full_score = data.get('fullScore', 100)
    
    if not image_base64:
        return jsonify({'error': 'No image provided'}), 400
    
    try:
        # Build grading prompt
        logic_instruction = ""
        if subject in ["Math", "Physics"]:
            logic_instruction = f"""เงื่อนไขสำคัญมาก: สำหรับวิชา {subject} หากโจทย์ต้องการการคำนวณ แต่ในภาพ 'ไม่มีการแสดงวิธีทำ' หรือมีแค่ 'คำตอบสุดท้าย' 
            ให้คะแนนไม่เกิน 25/{full_score} และระบุเหตุผลว่า 'โปรดแสดงวิธีทำเพื่อให้ได้คะแนนเต็ม'  
            แต่ถ้าโจทย์ไม่ได้ต้องการการคำนวณ ให้ตรวจตามปกติ และใช้ LaTeX สำหรับสมการ"""
        
        prompt = f"""คุณคืออาจารย์ผู้เชี่ยวชาญวิชา {subject} ตรวจงานอย่างละเอียดและซื่อตรง {logic_instruction}
        คะแนนเต็มคือ {full_score} คะแนน
        โปรดตรวจงานในภาพและตอบกลับตามโครงสร้างนี้:
        1. คะแนนที่ได้: (X/{full_score})
        2. จุดที่ทำได้ดี:
        3. ข้อผิดพลาดที่ควรแก้ไข:
        4. สรุปคำแนะนำ:
        5. เฉลยและวิธีทำ: (ใช้ LaTeX)"""
        
        # Decode image and call Gemini
        image_data = base64.b64decode(image_base64)
        
        response = model.generate_content([
            prompt,
            {'mime_type': 'image/jpeg', 'data': image_data}
        ])
        
        response_text = response.text
        
        # Extract score from response
        import re
        score_match = re.search(r'(\d+)\s*/\s*' + str(full_score), response_text)
        score = int(score_match.group(1)) if score_match else int(full_score * 0.8)
        
        return jsonify({
            'success': True,
            'score': score,
            'fullScore': full_score,
            'feedback': response_text
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submissions', methods=['GET'])
def get_submissions():
    """Get all submissions (for admin/teacher)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, u.name as student_name 
        FROM submissions s 
        JOIN users u ON s.student_id = u.id 
        ORDER BY s.created_at DESC
    ''')
    submissions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'submissions': submissions})

@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users (for admin)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'users': users})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user (for admin)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    print("Starting Stuwork Backend Server...")
    print("API running at http://localhost:5000")
    app.run(debug=True, port=5000)
