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



supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- API ENDPOINTS (JSON ONLY) ---
def get_file_path_from_url(url):
    """Mengambil path file (photos/xxx.jpg) dari URL publik Supabase"""
    try:
        # URL contoh: https://.../storage/v1/object/public/employee_photos/photos/UID.jpg
        # Kita butuh: photos/UID.jpg
        if "employee_photos/" in url:
            return url.split("employee_photos/")[1]
    except:
        return None
    return None


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
        name = request.form.get('name')
        status = request.form.get('status')
        rfid_uid = request.form.get('rfid_uid')
        photo = request.files.get('image_url')

        if not all([name, status, rfid_uid, photo]):
            return jsonify({"error": "Data tidak lengkap"}), 400

        file_extension = os.path.splitext(photo.filename)[1]
        file_path = f"photos/{rfid_uid}{file_extension}"
        
        # Upload foto ke Supabase Storage
        photo.seek(0)
        supabase.storage.from_('employee_photos').upload(
            file_path, photo.read(), {"content-type": photo.mimetype, "upsert": "true"}
        )
        image_url = supabase.storage.from_('employee_photos').get_public_url(file_path)

        # Simpan data karyawan
        data = {'name': name, 'status': status, 'rfid_uid': rfid_uid, 'image_url': image_url}
        supabase.table('employees').insert(data).execute()

        return jsonify({"success": True, "message": f"{name} berhasil didaftarkan"}), 200

    except Exception as e:
        error_message = str(e).lower()
        # Cek apakah error mengandung kata "duplicate" atau kode error SQL untuk duplikat
        if "duplicate key" in error_message or "23505" in error_message:
            return jsonify({"error": "Gagal Mendaftar: ID Kartu RFID ini sudah terdaftar!"}), 409
        
        # Jika error lain, tampilkan aslinya
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


@app.route('/api/attendance/<int:record_id>', methods=['PUT'])
def update_attendance(record_id):
    try:
        data = request.get_json()

        # Ambil data dari input frontend
        date_val = data.get("date")          # Format: YYYY-MM-DD
        check_in_time = data.get("check_in") # Format: HH:MM
        check_out_time = data.get("check_out") # Format: HH:MM
        status = data.get("attendance_status")

        # 1. Cari tahu dulu record_id ini milik karyawan siapa
        # Kita butuh employee_id untuk mencari pasangannya
        current_record = supabase.table("attendance_records").select("employee_id").eq("id", record_id).execute()
        
        if not current_record.data:
            return jsonify({"error": "Record not found"}), 404
            
        employee_id = current_record.data[0]['employee_id']

        # 2. UPDATE CHECK IN (Mencari record tipe check_in di tanggal & karyawan tsb)
        if check_in_time:
            # Buat timestamp lengkap
            new_in_ts = f"{date_val}T{check_in_time}:00"
            
            # Update row yang type='check_in'
            # Kita filter berdasarkan employee_id dan tanggal (menggunakan filter lte & gte untuk tanggal)
            # Atau cara simpel: cari row check_in milik user ini di tanggal ini
            supabase.table("attendance_records").update({
                "timestamp": new_in_ts
            }).eq("employee_id", employee_id).eq("type", "check_in").gte("timestamp", f"{date_val}T00:00:00").lte("timestamp", f"{date_val}T23:59:59").execute()

        # 3. UPDATE CHECK OUT (Mencari record tipe check_out di tanggal & karyawan tsb)
        if check_out_time:
            new_out_ts = f"{date_val}T{check_out_time}:00"
            
            update_payload = {"timestamp": new_out_ts}
            if status:
                update_payload["attendance_status"] = status

            # Update row yang type='check_out'
            supabase.table("attendance_records").update(update_payload).eq("employee_id", employee_id).eq("type", "check_out").gte("timestamp", f"{date_val}T00:00:00").lte("timestamp", f"{date_val}T23:59:59").execute()

        return jsonify({"success": True})

    except Exception as e:
        print(f"Error: {e}") # Print error di console server untuk debugging
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
# Konfigurasi Jam Masuk (untuk status otomatis)
JAM_MASUK_BATAS = time(23, 0, 0) 
@app.route('/api/record-attendance', methods=['POST'])
def record_attendance():
    try:
        rfid_uid = request.form.get('rfid')
        live_image = request.files.get('live_image')

        # Cari karyawan
        emp_resp = supabase.table('employees').select('id, name').eq('rfid_uid', rfid_uid).single().execute()
        if not emp_resp.data:
            return jsonify({"error": "ID tidak ditemukan"}), 404

        employee = emp_resp.data

        # Kirim ke API verifikasi wajah
        files = {'file': (live_image.filename, live_image.stream, live_image.mimetype)}
        data = {'user_id': rfid_uid}

        try:
            api_res = requests.post(FRIEND_API_URL, files=files, data=data, timeout=30)
            api_data = api_res.json()
        except:
            return jsonify({"error": "Gagal koneksi ke server AI"}), 502

        if api_res.status_code != 200:
            return jsonify({"error": "Wajah tidak cocok", "details": api_data}), 401

        # Waktu sekarang
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_time = now.time()

        # Cari record hari ini
        today_records = supabase.table("attendance_records") \
            .select("id, type") \
            .eq("employee_id", employee["id"]) \
            .filter("timestamp", "gte", f"{today_str}T00:00:00") \
            .filter("timestamp", "lte", f"{today_str}T23:59:59") \
            .execute().data

        has_check_in = any(r["type"] == "check_in" for r in today_records)
        has_check_out = any(r["type"] == "check_out" for r in today_records)

        # ❗ Blokir bila sudah check-in & check-out
        if has_check_in and has_check_out:
            return jsonify({
                "error": "Hari ini sudah lengkap absen (check-in & check-out)",
                "status": "Hadir"
            }), 400

        # Tentukan jenis absensi
        if not has_check_in:
            att_type = "check_in"
            status_ket = "Tepat Waktu" if current_time <= JAM_MASUK_BATAS else "Terlambat"
        else:
            att_type = "check_out"
            status_ket = "Hadir"

        # Insert record
        supabase.table('attendance_records').insert({
            "employee_id": employee["id"],
            "timestamp": now.isoformat(),
            "type": att_type,
            "attendance_status": status_ket
        }).execute()

        # Response
        return jsonify({
            "success": True,
            "message": f"Absensi {att_type} berhasil",
            "attendance_status": status_ket,
            "details": api_data
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route('/api/employees-full-list', methods=['GET'])
def get_employees_full_list():
    try:
        # Ambil semua kolom
        response = supabase.table('employees').select('*').order('id', desc=True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 2. UPDATE KARYAWAN (BARU)
@app.route('/api/employees/<int:id>', methods=['PUT'])
def update_employee(id):
    try:
        name = request.form.get('name')
        status = request.form.get('status')
        rfid_uid = request.form.get('rfid_uid')
        photo = request.files.get('image_url') # Foto opsional saat edit

        # Ambil data lama untuk jaga-jaga
        old_data = supabase.table('employees').select('*').eq('id', id).single().execute().data

        update_payload = {
            'name': name,
            'status': status,
            'rfid_uid': rfid_uid
        }

        # Jika ada upload foto baru
        if photo:
            file_extension = os.path.splitext(photo.filename)[1]
            file_path = f"photos/{rfid_uid}{file_extension}"
            
            # Hapus foto lama jika nama filenya beda (opsional, tapi bersih)
            if old_data and old_data.get('image_url'):
                old_path = get_file_path_from_url(old_data['image_url'])
                if old_path:
                    supabase.storage.from_('employee_photos').remove([old_path])

            # Upload foto baru
            photo.seek(0)
            supabase.storage.from_('employee_photos').upload(
                file_path, photo.read(), {"content-type": photo.mimetype, "upsert": "true"}
            )
            image_url = supabase.storage.from_('employee_photos').get_public_url(file_path)
            update_payload['image_url'] = image_url

        # Update Database
        supabase.table('employees').update(update_payload).eq('id', id).execute()

        return jsonify({"success": True, "message": "Data karyawan berhasil diupdate"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 3. DELETE KARYAWAN (DIPERBAIKI: Hapus Foto juga)
@app.route('/api/employees/<int:id>', methods=['DELETE'])
def delete_employee(id):
    try:
        # 1. Ambil info karyawan dulu sebelum dihapus untuk dapat URL foto
        response = supabase.table('employees').select('image_url').eq('id', id).single().execute()
        employee = response.data

        # 2. Hapus Foto di Storage
        if employee and employee.get('image_url'):
            file_path = get_file_path_from_url(employee['image_url'])
            if file_path:
                # Hapus file dari bucket
                res = supabase.storage.from_('employee_photos').remove([file_path])
                if isinstance(res, list) and len(res) == 0:
                    print("Warning: File mungkin sudah tidak ada atau gagal dihapus.")

        # 3. Hapus Data di Database (Cascade delete record absensi biasanya diatur di DB, tapi aman dihapus parentnya)
        # Hapus record absensi terkait dulu (manual cascade jika di DB tidak diset)
        supabase.table('attendance_records').delete().eq('employee_id', id).execute()
        
        # Hapus karyawan
        supabase.table('employees').delete().eq('id', id).execute()

        return jsonify({"success": True, "message": "Karyawan dan data terkait berhasil dihapus"}), 200
    except Exception as e:
        print(f"Error deleting: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)