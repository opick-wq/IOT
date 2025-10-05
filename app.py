import os
import requests
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
app = Flask(__name__)

# --- Konfigurasi ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HUGGING_FACE_KEY = os.environ.get("HUGGING_FACE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
HUGGING_FACE_API_URL = "https://api-inference.huggingface.co/models/sentence-transformers/clip-ViT-B-32"
HF_HEADERS = {"Authorization": f"Bearer {HUGGING_FACE_KEY}"}

# --- Halaman Web (Routes) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/report')
def report_page():
    try:
        response = supabase.table('attendance_records').select(
            'timestamp, type, employees(name, status)'
        ).order('timestamp', desc=True).execute()
        return render_template('report.html', records=response.data)
    except Exception as e:
        print(f"Error fetching report data: {e}")
        return render_template('report.html', records=[], error="Gagal memuat data laporan.")

# --- API Endpoints ---
@app.route('/api/register-employee', methods=['POST'])
def register_employee():
    try:
        name = request.form['name']
        status = request.form['status']
        rfid_uid = request.form['rfid_uid']
        photo = request.files['photo']

        file_extension = os.path.splitext(photo.filename)[1]
        file_path_in_storage = f"photos/{rfid_uid}{file_extension}"
        
        photo.seek(0)
        supabase.storage.from_('employee_photos').upload(file_path_in_storage, photo.read(), {"content-type": photo.mimetype})
        
        image_url = supabase.storage.from_('employee_photos').get_public_url(file_path_in_storage)

        employee_data = {
            'name': name, 'status': status, 'rfid_uid': rfid_uid, 'image_url': image_url
        }
        supabase.table('employees').insert(employee_data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan!"}), 201
    except Exception as e:
        print(f"Error saat pendaftaran: {e}")
        return jsonify({"error": f"Terjadi kesalahan: {e}"}), 500

@app.route('/api/get-employee-data', methods=['POST'])
def get_employee_data():
    data = request.get_json()
    rfid_uid = data.get('rfid')
    try:
        response = supabase.table('employees').select('name, status, image_url').eq('rfid_uid', rfid_uid).single().execute()
        employee = response.data
        if not employee:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404
        return jsonify(employee), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/verify-and-record', methods=['POST'])
def verify_and_record():
    try:
        rfid_uid = request.form.get('rfid')
        response = supabase.table('employees').select('id, name').eq('rfid_uid', rfid_uid).single().execute()
        employee = response.data
        if not employee:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404

        # Untuk demo, kita skip verifikasi wajah dan langsung anggap cocok
        is_match = True
        
        if not is_match:
            return jsonify({"error": "Verifikasi wajah gagal!"}), 401
        
        # Logika check-in/check-out
        today_str = datetime.now().strftime('%Y-%m-%d')
        records_response = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today_str}T00:00:00").execute()
        attendance_type = 'check_out' if records_response.data else 'check_in'

        attendance_data = { 'employee_id': employee['id'], 'type': attendance_type }
        supabase.table('attendance_records').insert(attendance_data).execute()

        return jsonify({"success": True, "message": f"Absensi '{attendance_type}' untuk {employee['name']} berhasil direkam."}), 200
    except Exception as e:
        print(f"Error saat verifikasi: {e}")
        return jsonify({"error": str(e)}), 500