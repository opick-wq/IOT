import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from supabase_py import create_client, Client
import face_recognition
import cv2
import numpy as np
import requests
from datetime import datetime

# Inisialisasi koneksi ke Supabase
# Ambil dari Project Settings > API di Supabase
SUPABASE_URL = "https://bzulwuhcmmbmtwmgyerb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ6dWx3dWhjbW1ibXR3bWd5ZXJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTg2MTc4MTEsImV4cCI6MjA3NDE5MzgxMX0.v4tVyjmDv8PhKWQlbtFuKUBwAM2OafDTnsxXwL2g0ns"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)

# --- HALAMAN WEB ---

@app.route('/')
def home():
    """Halaman utama, menampilkan data absensi."""
    try:
        # Ambil data karyawan dan join dengan data absensi
        response = supabase.table('attendance_records').select('*, employees(name, status)').execute()
        records = response.get('data', [])
        return render_template('attendance.html', records=records)
    except Exception as e:
        return f"Error fetching data: {e}"


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Halaman untuk mendaftarkan karyawan baru."""
    if request.method == 'POST':
        name = request.form['name']
        status = request.form['status']
        rfid_uid = request.form['rfid_uid']
        photo = request.files['photo']

        if not all([name, status, rfid_uid, photo]):
            return "Semua field harus diisi!", 400

        try:
            # Simpan foto ke Supabase Storage
            file_extension = os.path.splitext(photo.filename)[1]
            file_path_in_storage = f"{rfid_uid}{file_extension}"
            
            # Reset pointer file sebelum mengunggah
            photo.seek(0)
            
            supabase.storage().from_('employee_photos').upload(file_path_in_storage, photo.read())
            
            # Dapatkan URL publik dari foto yang diunggah
            image_url = supabase.storage().from_('employee_photos').get_public_url(file_path_in_storage)

            # Simpan data karyawan ke tabel 'employees'
            employee_data = {
                'name': name,
                'status': status,
                'rfid_uid': rfid_uid,
                'image_url': image_url['publicURL']
            }
            supabase.table('employees').insert(employee_data).execute()

            return redirect(url_for('home'))
        except Exception as e:
            # Cetak error untuk debugging
            print(f"Error saat pendaftaran: {e}")
            return f"Terjadi kesalahan saat menyimpan data: {e}", 500

    return render_template('register.html')

# --- API UNTUK ESP8266 & PROSES ABSENSI ---

@app.route('/api/record-rfid', methods=['POST'])
def record_rfid():
    """API yang dipanggil oleh ESP8266 saat kartu di-tap."""
    rfid_uid = request.form.get('rfid')
    if not rfid_uid:
        return jsonify({"error": "UID RFID tidak ditemukan"}), 400

    try:
        # 1. Cari karyawan berdasarkan UID RFID
        response = supabase.table('employees').select('*').eq('rfid_uid', rfid_uid).single().execute()
        employee = response.get('data')

        if not employee:
            return jsonify({"error": "Karyawan tidak terdaftar"}), 404
            
        # 2. Ambil gambar dari URL dan gambar dari webcam untuk perbandingan
        stored_image_url = employee['image_url']
        
        # Download gambar yang tersimpan
        response_img = requests.get(stored_image_url, stream=True).raw
        stored_image_array = np.asarray(bytearray(response_img.read()), dtype="uint8")
        stored_image = cv2.imdecode(stored_image_array, cv2.IMREAD_COLOR)

        # Ambil gambar dari webcam (ini bagian yang tricky di web, biasanya pakai JavaScript)
        # Untuk demo, kita simulasikan 'match'
        # Dalam implementasi nyata, frontend akan mengirim gambar dari webcam ke endpoint ini
        
        # --- LOGIKA PENGENALAN WAJAH (FACE RECOGNITION) ---
        # Untuk implementasi penuh, Anda akan menerima gambar dari webcam di sini
        # dan membandingkannya. Contoh logikanya:
        #
        # webcam_image = ... (gambar dari request)
        # stored_face_encoding = face_recognition.face_encodings(stored_image)[0]
        # webcam_face_encodings = face_recognition.face_encodings(webcam_image)
        #
        # match = False
        # if webcam_face_encodings:
        #     match = face_recognition.compare_faces([stored_face_encoding], webcam_face_encodings[0])[0]
        #
        # if not match:
        #     return jsonify({"error": "Wajah tidak cocok!"}), 401
        # ----------------------------------------------------

        # 3. Tentukan tipe absensi (masuk/pulang)
        # Logika sederhana: jika ada record hari ini, maka ini 'check_out', jika tidak maka 'check_in'
        today_str = datetime.now().strftime('%Y-%m-%d')
        response_records = supabase.table('attendance_records').select('id').eq('employee_id', employee['id']).filter('timestamp', 'gte', f"{today_str}T00:00:00").execute()
        
        attendance_type = 'check_out' if response_records.get('data') else 'check_in'

        # 4. Simpan catatan absensi
        attendance_data = {
            'employee_id': employee['id'],
            'type': attendance_type
        }
        supabase.table('attendance_records').insert(attendance_data).execute()

        return jsonify({
            "success": True, 
            "message": f"Absensi '{attendance_type}' untuk {employee['name']} berhasil direkam."
        }), 200

    except Exception as e:
        print(f"Error di API: {e}")
        return jsonify({"error": f"Internal server error: {e}"}), 500

if __name__ == '__main__':
    # Gunakan port 8000 seperti di kode Arduino-mu
    app.run(host='0.0.0.0', port=8000, debug=True)