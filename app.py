import os
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

# Muat environment variables (untuk development lokal)
load_dotenv()

app = Flask(__name__)

# --- Konfigurasi ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HUGGING_FACE_KEY = os.environ.get("HUGGING_FACE_KEY")

# Pastikan semua kredensial ada
if not all([SUPABASE_URL, SUPABASE_KEY, HUGGING_FACE_KEY]):
    # Di Vercel, ini akan menyebabkan error saat aplikasi dimulai jika variabel tidak ada
    print("WARNING: Satu atau lebih environment variables tidak ditemukan.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
HUGGING_FACE_API_URL = "https://api-inference.huggingface.co/models/sentence-transformers/clip-ViT-B-32"
HF_HEADERS = {"Authorization": f"Bearer {HUGGING_FACE_KEY}"}


# --- Halaman Web (Routes) ---

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
        # Ambil semua data absensi dan gabungkan dengan data karyawan
        response = supabase.table('attendance_records').select(
            'timestamp, type, employees(name, status)'
        ).order('timestamp', desc=True).execute()
        
        records = response.data
        return render_template('report.html', records=records)
    except Exception as e:
        print(f"Error fetching report data: {e}")
        return render_template('report.html', records=[], error="Gagal memuat data laporan.")


# --- API Endpoints ---

@app.route('/api/register-employee', methods=['POST'])
def register_employee():
    """API untuk menyimpan data karyawan baru."""
    try:
        name = request.form['name']
        status = request.form['status']
        rfid_uid = request.form['rfid_uid']
        photo = request.files['photo']

        if not all([name, status, rfid_uid, photo]):
            return jsonify({"error": "Semua field harus diisi!"}), 400

        # Upload foto ke Supabase Storage
        file_extension = os.path.splitext(photo.filename)[1]
        file_path_in_storage = f"photos/{rfid_uid}{file_extension}"
        
        photo.seek(0)
        supabase.storage.from_('employee_assets').upload(file_path_in_storage, photo.read(), {"content-type": photo.mimetype})
        
        # Dapatkan URL publik dari foto yang diunggah
        public_url_data = supabase.storage.from_('employee_assets').get_public_url(file_path_in_storage)
        image_url = public_url_data

        # Simpan data karyawan ke tabel 'employees'
        employee_data = {
            'name': name,
            'status': status,
            'rfid_uid': rfid_uid,
            'image_url': image_url
        }
        supabase.table('employees').insert(employee_data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan!"}), 201

    except Exception as e:
        # Cetak error untuk debugging
        print(f"Error saat pendaftaran: {e}")
        return jsonify({"error": f"Terjadi kesalahan: {e}"}), 500

# Endpoint API yang lain (get-employee-data, verify-and-record) biarkan sama persis
# ... (kode dari file sebelumnya untuk /api/get-employee-data dan /api/verify-and-record) ...

if __name__ == '__main__':
    app.run(debug=True)