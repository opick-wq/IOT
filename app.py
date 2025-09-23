import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from supabase_py import create_client, Client
# import face_recognition  <-- (1) Beri komentar pada baris ini
import cv2
import numpy as np
import requests
from datetime import datetime

# (Kode koneksi Supabase biarkan seperti yang sudah diperbaiki)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)

# (Kode @app.route('/') dan @app.route('/register') tidak perlu diubah)
# ...
# ...

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
            
        # (2) NONAKTIFKAN SELURUH BLOK KODE PENGENALAN WAJAH DI BAWAH INI
        # -----------------------------------------------------------------
        # stored_image_url = employee['image_url']
        
        # # Download gambar yang tersimpan
        # response_img = requests.get(stored_image_url, stream=True).raw
        # stored_image_array = np.asarray(bytearray(response_img.read()), dtype="uint8")
        # stored_image = cv2.imdecode(stored_image_array, cv2.IMREAD_COLOR)

        # # --- LOGIKA PENGENALAN WAJAH (FACE RECOGNITION) ---
        # # Untuk implementasi penuh, Anda akan menerima gambar dari webcam di sini
        # # dan membandingkannya. Contoh logikanya:
        # #
        # # webcam_image = ... (gambar dari request)
        # # stored_face_encoding = face_recognition.face_encodings(stored_image)[0]
        # # webcam_face_encodings = face_recognition.face_encodings(webcam_image)
        # #
        # # match = False
        # # if webcam_face_encodings:
        # #     match = face_recognition.compare_faces([stored_face_encoding], webcam_face_encodings[0])[0]
        # #
        # # if not match:
        # #     return jsonify({"error": "Wajah tidak cocok!"}), 401
        # -----------------------------------------------------------------
        
        # 3. Tentukan tipe absensi (masuk/pulang)
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
    app.run(host='0.0.0.0', port=8000, debug=True)