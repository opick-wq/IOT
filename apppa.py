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
app.secret_key = os.environ.get("SECRET_KEY") # Ganti dengan key acak di Vercel

# --- KONFIGURASI SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FRIEND_API_URL = "https://yudhriz-api-absensi.hf.space/verify"

# --- LOGIN ADMIN ---
ADMIN_USER = os.environ.get("ADMIN_USERNAME")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD")

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
@login_required
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
            'id, employee_id, timestamp, type, employees(name, status)'
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

@app.route('/api/attendance/manual', methods=['POST'])
@login_required
def manual_attendance():
    """Menambahkan data absensi secara manual."""
    try:
        data = request.get_json()
        # Cari ID karyawan berdasarkan Nama (atau bisa dropdown ID di frontend)
        # Untuk simpelnya, kita asumsikan frontend kirim employee_id yang benar
        employee_id = data.get('employee_id')
        timestamp = data.get('timestamp') # Format: YYYY-MM-DD HH:MM:SS
        type_ = data.get('type')

        if not all([employee_id, timestamp, type_]):
            return jsonify({"error": "Data tidak lengkap"}), 400

        supabase.table('attendance_records').insert({
            'employee_id': employee_id,
            'timestamp': timestamp,
            'type': type_
        }).execute()

        return jsonify({"success": True, "message": "Data berhasil ditambahkan"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attendance/<int:record_id>', methods=['PUT'])
@login_required
def update_attendance(record_id):
    """Mengedit data absensi."""
    try:
        data = request.get_json()
        # Kita izinkan edit waktu dan tipe
        update_data = {}
        if 'timestamp' in data: update_data['timestamp'] = data['timestamp']
        if 'type' in data: update_data['type'] = data['type']

        supabase.table('attendance_records').update(update_data).eq('id', record_id).execute()
        return jsonify({"success": True, "message": "Data berhasil diupdate"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attendance/<int:record_id>', methods=['DELETE'])
@login_required
def delete_attendance(record_id):
    """Menghapus data absensi."""
    try:
        supabase.table('attendance_records').delete().eq('id', record_id).execute()
        return jsonify({"success": True, "message": "Data berhasil dihapus"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Endpoint untuk mengambil daftar karyawan (untuk dropdown tambah manual)
@app.route('/api/employees-list', methods=['GET'])
@login_required
def get_employees_list():
    try:
        response = supabase.table('employees').select('id, name').execute()
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
    

@app.route('/api/attendance/manual', methods=['POST'])
def manual_attendance():
    try:
        data = request.get_json()

        employee_id = data.get("employee_id")
        date = data.get("date")
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        status_ket = data.get("attendance_status", "Hadir")

        if not employee_id or not date:
            return jsonify({"error": "employee_id dan date wajib"}), 400

        # INSERT CHECK-IN
        if check_in:
            supabase.table("attendance_records").insert({
                "employee_id": employee_id,
                "timestamp": f"{date}T{check_in}:00",
                "type": "check_in",
                "attendance_status": status_ket
            }).execute()

        # INSERT CHECK-OUT
        if check_out:
            supabase.table("attendance_records").insert({
                "employee_id": employee_id,
                "timestamp": f"{date}T{check_out}:00",
                "type": "check_out",
                "attendance_status": status_ket
            }).execute()

        return jsonify({"success": True, "message": "Data manual berhasil ditambahkan"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)