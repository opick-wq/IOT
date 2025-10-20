import os
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

# Muat environment variables (untuk development lokal)
load_dotenv()

app = Flask(__name__)

# --- KONFIGURASI APLIKASI ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Pastikan kredensial Supabase ada
if not all([SUPABASE_URL, SUPABASE_KEY]):
    print("WARNING: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- HALAMAN WEB (ROUTES) ---

@app.route('/')
def index():
    """Halaman utama untuk absensi."""
    return render_template('index.html')

@app.route('/register')
def register_page():
    """Halaman untuk mendaftarkan karyawan baru."""
    return render_template('register.html')

@app.route('/report')
def report_page():
    """Halaman untuk melihat laporan absensi."""
    try:
        response = supabase.table('attendance_records').select(
            'timestamp, type, employees(name, status)'
        ).order('timestamp', desc=True).execute()
        return render_template('report.html', records=response.data)
    except Exception as e:
        print(f"Error saat mengambil data laporan: {e}")
        return render_template('report.html', records=[], error="Gagal memuat data laporan.")

# --- API ENDPOINTS ---

@app.route('/api/register-employee', methods=['POST'])
def register_employee():
    """API untuk menyimpan data karyawan baru."""
    try:
        # (Logika pendaftaran tidak berubah)
        name = request.form['name']
        status = request.form['status']
        rfid_uid = request.form['rfid_uid']
        photo = request.files['photo']

        file_extension = os.path.splitext(photo.filename)[1]
        file_path_in_storage = f"photos/{rfid_uid}{file_extension}"
        
        photo.seek(0)
        # Pastikan nama bucket di sini sesuai dengan yang ada di Supabase Anda
        supabase.storage.from_('employee_photos').upload(
            file_path_in_storage, photo.read(), {"content-type": photo.mimetype}
        )
        
        image_url = supabase.storage.from_('employee_photos').get_public_url(file_path_in_storage)

        employee_data = {'name': name, 'status': status, 'rfid_uid': rfid_uid, 'image_url': image_url}
        supabase.table('employees').insert(employee_data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan!"}), 201
    except Exception as e:
        print(f"Error saat pendaftaran: {e}")
        return jsonify({"error": f"Terjadi kesalahan: {e}"}), 500

@app.route('/api/get-employee-data', methods=['POST'])
def get_employee_data():
    """API untuk memberikan data karyawan ke browser."""
    try:
        rfid_uid = request.get_json().get('rfid')
        response = supabase.table('employees').select('name, status, image_url, rfid_uid').eq('rfid_uid', rfid_uid).single().execute()
        if not response.data:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/record-attendance', methods=['POST'])
def record_attendance():
    """API BARU: Hanya untuk mencatat absensi setelah verifikasi berhasil di browser."""
    try:
        rfid_uid = request.get_json().get('rfid')

        # Dapatkan ID karyawan dari rfid_uid
        employee_response = supabase.table('employees').select('id, name').eq('rfid_uid', rfid_uid).single().execute()
        employee = employee_response.data
        if not employee:
            return jsonify({"error": "Karyawan tidak ditemukan saat akan mencatat absensi."}), 404

        # Logika check-in/check-out (tidak berubah)
        today_str = datetime.now().strftime('%Y-%m-%d')
        records_response = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today_str}T00:00:00").execute()
        attendance_type = 'check_out' if records_response.data else 'check_in'

        attendance_data = { 'employee_id': employee['id'], 'type': attendance_type }
        supabase.table('attendance_records').insert(attendance_data).execute()

        return jsonify({
            "success": True, 
            "message": f"Absensi '{attendance_type}' untuk {employee['name']} berhasil dicatat."
        }), 200
    except Exception as e:
        print(f"Error saat mencatat absensi: {e}")
        return jsonify({"error": str(e)}), 500