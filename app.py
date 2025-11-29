import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, time

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# --- KONFIGURASI CORS ---
# Izinkan semua origin untuk akses API (penting untuk pengembangan React terpisah)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- KONFIGURASI SUPABASE & API LAIN ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FRIEND_API_URL = "https://yudhriz-api-absensi.hf.space/verify"

ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")

# Konfigurasi Jam Masuk (untuk status otomatis)
JAM_MASUK_BATAS = time(8, 0, 0) 

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- API ENDPOINTS (JSON ONLY) ---

# 1. API LOGIN
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if username == ADMIN_USER and password == ADMIN_PASS:
        return jsonify({"success": True, "message": "Login berhasil"}), 200
    else:
        return jsonify({"success": False, "message": "Username atau password salah"}), 401

# 2. API DAFTAR KARYAWAN
@app.route('/api/register-employee', methods=['POST'])
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

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. API LIST DATA ABSENSI (REPORT)
@app.route('/api/attendance/report', methods=['GET'])
def get_attendance_report():
    try:
        # Mengambil kolom attendance_status juga
        response = supabase.table('attendance_records').select(
            'id, employee_id, timestamp, type, attendance_status, employees(name, status)'
        ).order('timestamp', desc=True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 4. API LIST KARYAWAN (Untuk Dropdown di Frontend)
@app.route('/api/employees-list', methods=['GET'])
def get_employees_list():
    try:
        response = supabase.table('employees').select('id, name').execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 5. API CRUD MANUAL ABSENSI
@app.route('/api/attendance/manual', methods=['POST'])
def manual_attendance():
    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        timestamp = data.get('timestamp')
        type_ = data.get('type')
        status_ket = data.get('status', 'Hadir') # Ambil status manual

        if not all([employee_id, timestamp, type_]):
            return jsonify({"error": "Data tidak lengkap"}), 400

        supabase.table('attendance_records').insert({
            'employee_id': employee_id,
            'timestamp': timestamp,
            'type': type_,
            'attendance_status': status_ket
        }).execute()

        return jsonify({"success": True, "message": "Data berhasil ditambahkan"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attendance/<int:record_id>', methods=['PUT'])
def update_attendance(record_id):
    try:
        data = request.get_json()
        update_data = {}
        if 'timestamp' in data: update_data['timestamp'] = data['timestamp']
        if 'type' in data: update_data['type'] = data['type']
        if 'status' in data: update_data['attendance_status'] = data['status']

        supabase.table('attendance_records').update(update_data).eq('id', record_id).execute()
        return jsonify({"success": True, "message": "Data berhasil diupdate"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attendance/<int:record_id>', methods=['DELETE'])
def delete_attendance(record_id):
    try:
        supabase.table('attendance_records').delete().eq('id', record_id).execute()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 6. API CEK KARYAWAN (Untuk Halaman Absen)
@app.route('/api/get-employee-data', methods=['POST'])
def get_employee_data():
    data = request.get_json()
    rfid_uid = data.get('rfid')
    try:
        response = supabase.table('employees').select('*').eq('rfid_uid', rfid_uid).single().execute()
        if not response.data:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 7. API CATAT ABSENSI (VERIFIKASI WAJAH)
@app.route('/api/record-attendance', methods=['POST'])
def record_attendance():
    try:
        rfid_uid = request.form.get('rfid')
        live_image = request.files.get('live_image')

        # Cek Karyawan
        emp_resp = supabase.table('employees').select('id, name').eq('rfid_uid', rfid_uid).single().execute()
        if not emp_resp.data: return jsonify({"error": "ID tidak ditemukan"}), 404
        employee = emp_resp.data

        # Kirim ke API Teman (Verifikasi)
        files = {'file': (live_image.filename, live_image.stream, live_image.mimetype)}
        data = {'user_id': rfid_uid}
        
        try:
            api_res = requests.post(FRIEND_API_URL, files=files, data=data, timeout=30)
            api_data = api_res.json()
        except:
            return jsonify({"error": "Gagal koneksi ke server AI"}), 502

        if api_res.status_code != 200:
            return jsonify({
                "error": "Wajah tidak cocok", 
                "details": api_data
            }), 401

        # Logika Otomatis Status (Tepat Waktu / Terlambat)
        now = datetime.now()
        current_time = now.time()
        status_ket = "Hadir"

        today_str = now.strftime('%Y-%m-%d')
        rec_resp = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today_str}T00:00:00").execute()
        att_type = 'check_out' if rec_resp.data else 'check_in'
        
        if att_type == 'check_in':
            status_ket = "Tepat Waktu" if current_time <= JAM_MASUK_BATAS else "Terlambat"
        else:
            status_ket = "Pulang"

        # Catat ke DB
        supabase.table('attendance_records').insert({
            'employee_id': employee['id'], 
            'type': att_type,
            'attendance_status': status_ket
        }).execute()

        return jsonify({
            "success": True, 
            "message": f"Absensi {att_type} Berhasil",
            "details": api_data
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)