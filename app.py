import os
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime
from functools import wraps

# Muat environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rahasia_dapur_bor") # Ganti dengan key acak di Vercel

# --- KONFIGURASI SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FRIEND_API_URL = "https://yudhriz-api-absensi.hf.space/verify"

# --- LOGIN ADMIN ---
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")

if not all([SUPABASE_URL, SUPABASE_KEY]):
    print("WARNING: Kredensial Supabase tidak ditemukan.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DEKORATOR KEAMANAN ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- HALAMAN WEB (ROUTES) ---

@app.route('/')
def login_page():
    """Halaman Utama sekarang adalah Login Admin."""
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login_process():
    username = request.form.get('username')
    password = request.form.get('password')
    if username == ADMIN_USER and password == ADMIN_PASS:
        session['logged_in'] = True
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', error="Username atau Password salah!")

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login_page'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Menu utama Admin."""
    return render_template('dashboard.html')

@app.route('/absen')
def absen_page():
    """Halaman Publik untuk Absensi Karyawan."""
    return render_template('absen.html')

@app.route('/register')
@login_required
def register_page():
    return render_template('register.html')

@app.route('/report')
@login_required
def report_page():
    try:
        response = supabase.table('attendance_records').select(
            'timestamp, type, employees(name, status)'
        ).order('timestamp', desc=True).execute()
        return render_template('report.html', records=response.data)
    except Exception as e:
        return render_template('report.html', records=[], error="Gagal memuat data.")

# --- API ENDPOINTS ---

@app.route('/api/register-employee', methods=['POST'])
@login_required
def register_employee():
    try:
        name = request.form['name']
        status = request.form['status']
        rfid_uid = request.form['rfid_uid']
        photo = request.files['photo']

        file_extension = os.path.splitext(photo.filename)[1]
        file_path = f"photos/{rfid_uid}{file_extension}"
        
        photo.seek(0)
        supabase.storage.from_('employee_photos').upload(
            file_path, photo.read(), {"content-type": photo.mimetype}
        )
        image_url = supabase.storage.from_('employee_photos').get_public_url(file_path)

        data = {'name': name, 'status': status, 'rfid_uid': rfid_uid, 'image_url': image_url}
        supabase.table('employees').insert(data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-employee-data', methods=['POST'])
def get_employee_data():
    rfid_uid = request.get_json().get('rfid')
    try:
        response = supabase.table('employees').select('*').eq('rfid_uid', rfid_uid).single().execute()
        if not response.data:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/record-attendance', methods=['POST'])
def record_attendance():
    try:
        rfid_uid = request.form.get('rfid')
        live_image = request.files.get('live_image')

        if not rfid_uid or not live_image:
            return jsonify({"error": "Data tidak lengkap"}), 400

        # 1. Cek Karyawan
        emp_response = supabase.table('employees').select('id, name').eq('rfid_uid', rfid_uid).single().execute()
        if not emp_response.data:
             return jsonify({"error": "ID Karyawan tidak ditemukan."}), 404
        
        employee = emp_response.data

        # 2. Kirim ke API Teman
        files = {'file': (live_image.filename, live_image.stream, live_image.mimetype)}
        data = {'user_id': rfid_uid}

        try:
            api_response = requests.post(FRIEND_API_URL, files=files, data=data, timeout=30)
            api_result = {}
            try:
                api_result = api_response.json()
            except:
                pass
        except Exception as api_err:
            return jsonify({"error": "Gagal menghubungi server AI."}), 502

        # 3. Cek Hasil AI
        if api_response.status_code != 200:
             return jsonify({
                 "error": "Wajah tidak cocok", 
                 "details": api_result 
             }), 401
        
        # 4. Catat Absensi
        today = datetime.now().strftime('%Y-%m-%d')
        rec_response = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today}T00:00:00").execute()
        att_type = 'check_out' if rec_response.data else 'check_in'
        
        supabase.table('attendance_records').insert({
            'employee_id': employee['id'], 'type': att_type
        }).execute()

        return jsonify({
            "success": True, 
            "message": f"Absensi '{att_type}' Berhasil!",
            "details": api_result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)