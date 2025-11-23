import os
import requests
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

# Muat environment variables
load_dotenv()

app = Flask(__name__)

# --- KONFIGURASI SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY]):
    print("WARNING: Supabase credentials not found.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- URL API TEMAN ANDA ---
FRIEND_API_URL = "https://yudhriz-api-absensi.hf.space/verify"

# --- HALAMAN WEB ---
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
        return render_template('report.html', records=[], error="Gagal memuat data.")

# --- API ENDPOINTS ---

@app.route('/api/register-employee', methods=['POST'])
def register_employee():
    """API Pendaftaran Karyawan"""
    try:
        name = request.form['name']
        status = request.form['status']
        rfid_uid = request.form['rfid_uid']
        photo = request.files['photo']

        # Simpan foto ke Supabase Storage
        file_extension = os.path.splitext(photo.filename)[1]
        file_path = f"photos/{rfid_uid}{file_extension}"
        
        photo.seek(0)
        supabase.storage.from_('employee_photos').upload(
            file_path, photo.read(), {"content-type": photo.mimetype}
        )
        image_url = supabase.storage.from_('employee_photos').get_public_url(file_path)

        # Simpan data ke tabel employees
        data = {'name': name, 'status': status, 'rfid_uid': rfid_uid, 'image_url': image_url}
        supabase.table('employees').insert(data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan!"}), 201
    except Exception as e:
        print(f"Error Pendaftaran: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-employee-data', methods=['POST'])
def get_employee_data():
    """Mengambil data karyawan untuk ditampilkan sebelum verifikasi"""
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
    """
    API Inti: Menerima foto -> Kirim ke API Teman -> Catat Absensi
    """
    try:
        rfid_uid = request.form.get('rfid')
        live_image = request.files.get('live_image')

        if not rfid_uid or not live_image:
            return jsonify({"error": "Data tidak lengkap"}), 400

        # 1. Pastikan karyawan ada di database lokal
        emp_response = supabase.table('employees').select('id, name').eq('rfid_uid', rfid_uid).single().execute()
        if not emp_response.data:
             return jsonify({"error": "ID Karyawan tidak ditemukan."}), 404
        
        employee = emp_response.data

        # 2. SIAPKAN REQUEST KE API TEMAN
        print(f"🚀 Mengirim foto {rfid_uid} ke API Yudha...")
        
        # Format file sesuai permintaan `requests`
        files = {'file': (live_image.filename, live_image.stream, live_image.mimetype)}
        data = {'user_id': rfid_uid}

        # 3. KIRIM DAN TERIMA HASIL
        try:
            api_response = requests.post(FRIEND_API_URL, files=files, data=data, timeout=30) # Timeout 30 detik
            api_result = {}
            try:
                api_result = api_response.json()
            except:
                pass # Jika respon bukan JSON
        except Exception as api_err:
            print(f"API Error: {api_err}")
            return jsonify({"error": "Gagal menghubungi server AI verifikasi."}), 502

        print(f"📡 Respon API Teman: {api_result}")

        # 4. CEK HASIL VERIFIKASI
        # Asumsi: API teman mengembalikan status 200 jika VERIFIED
        if api_response.status_code != 200:
             # Kembalikan error beserta detail jarak (jika ada) untuk debugging di console browser
             return jsonify({
                 "error": "Wajah tidak cocok", 
                 "details": api_result 
             }), 401
        
        # 5. JIKA SUKSES, CATAT ABSENSI
        today = datetime.now().strftime('%Y-%m-%d')
        rec_response = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today}T00:00:00").execute()
        
        att_type = 'check_out' if rec_response.data else 'check_in'
        
        supabase.table('attendance_records').insert({
            'employee_id': employee['id'], 
            'type': att_type
        }).execute()

        # 6. KIRIM RESPON SUKSES KE BROWSER (Termasuk detail jarak)
        return jsonify({
            "success": True, 
            "message": f"Absensi '{att_type}' Berhasil!",
            "details": api_result # Kirim balik data dari API teman agar bisa dilihat di console
        }), 200

    except Exception as e:
        print(f"Critical Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)