import os
import requests
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime
import numpy as np

# Muat environment variables (untuk development lokal)
load_dotenv()

app = Flask(__name__)

# --- KONFIGURASI APLIKASI ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HUGGING_FACE_KEY = os.environ.get("HUGGING_FACE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Model yang benar dan URL API-nya
HF_API_URL = "https://api-inference.huggingface.co/models/sentence-transformers/clip-ViT-B-32-multilingual-v1"
HF_HEADERS = {"Authorization": f"Bearer {HUGGING_FACE_KEY}"}


# --- FUNGSI BANTUAN UNTUK AI (SUDAH DIPERBAIKI) ---

def get_image_embedding(image_data: bytes, content_type: str):
    """Mengirim data gambar (bytes) ke Hugging Face dengan Content-Type yang benar."""
    
    # Salin header otorisasi dan tambahkan Content-Type yang spesifik
    request_headers = HF_HEADERS.copy()
    request_headers["Content-Type"] = content_type

    response = requests.post(HF_API_URL, headers=request_headers, data=image_data)
    
    if response.status_code != 200:
        print(f"Hugging Face API Error: {response.status_code} - {response.text}")
        raise Exception("Gagal mendapatkan fitur wajah dari Hugging Face API.")
    return response.json()

def cosine_similarity(vec1, vec2):
    """Menghitung kemiripan antara dua vektor wajah."""
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


# --- HALAMAN WEB (ROUTES) ---

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
        print(f"Error saat mengambil data laporan: {e}")
        return render_template('report.html', records=[], error="Gagal memuat data laporan.")


# --- API ENDPOINTS ---

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

        employee_data = {'name': name, 'status': status, 'rfid_uid': rfid_uid, 'image_url': image_url}
        supabase.table('employees').insert(employee_data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan!"}), 201
    except Exception as e:
        print(f"Error saat pendaftaran: {e}")
        return jsonify({"error": f"Terjadi kesalahan: {e}"}), 500

@app.route('/api/get-employee-data', methods=['POST'])
def get_employee_data():
    rfid_uid = request.get_json().get('rfid')
    try:
        response = supabase.table('employees').select('name, status, image_url').eq('rfid_uid', rfid_uid).single().execute()
        if not response.data:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/verify-and-record', methods=['POST'])
def verify_and_record():
    """API untuk verifikasi wajah dan mencatat absensi (SUDAH DIPERBAIKI)."""
    try:
        rfid_uid = request.form.get('rfid')
        live_image_file = request.files.get('live_image')

        # 1. Dapatkan data karyawan
        response = supabase.table('employees').select('id, name, image_url').eq('rfid_uid', rfid_uid).single().execute()
        employee = response.data
        if not employee:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404
        
        # 2. Ambil gambar asli dari URL Supabase
        stored_image_response = requests.get(employee['image_url'])
        if stored_image_response.status_code != 200:
            return jsonify({"error": "Gagal mengunduh foto karyawan."}), 500
        
        # 3. Dapatkan 'sidik jari wajah' dari KEDUA gambar dengan Content-Type yang benar
        print("🔍 Memproses foto tersimpan...")
        stored_content_type = stored_image_response.headers.get('Content-Type', 'image/jpeg')
        stored_embedding = get_image_embedding(stored_image_response.content, stored_content_type)
        
        print("📸 Memproses foto live dari webcam...")
        live_image_bytes = live_image_file.read()
        live_embedding = get_image_embedding(live_image_bytes, live_image_file.mimetype)

        # 4. Hitung skor kemiripan
        similarity_score = cosine_similarity(stored_embedding, live_embedding)
        print(f"✨ Skor Kemiripan Wajah: {similarity_score:.4f}")

        # 5. Tentukan apakah wajah cocok (di atas 90%)
        SIMILARITY_THRESHOLD = 0.90
        if similarity_score < SIMILARITY_THRESHOLD:
            return jsonify({"error": f"Verifikasi wajah gagal! Kemiripan hanya {similarity_score:.2%}"}), 401
        
        # 6. Jika cocok, catat absensi
        print("✅ Wajah cocok! Mencatat absensi...")
        today_str = datetime.now().strftime('%Y-%m-%d')
        records_response = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today_str}T00:00:00").execute()
        attendance_type = 'check_out' if records_response.data else 'check_in'

        attendance_data = { 'employee_id': employee['id'], 'type': attendance_type }
        supabase.table('attendance_records').insert(attendance_data).execute()

        return jsonify({
            "success": True, 
            "message": f"Absensi '{attendance_type}' untuk {employee['name']} berhasil (Kemiripan: {similarity_score:.2%})."
        }), 200

    except Exception as e:
        print(f"Error saat verifikasi: {e}")
        return jsonify({"error": str(e)}), 500