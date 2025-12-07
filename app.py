import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, time
import pytz

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# --- KONFIGURASI CORS ---
# Izinkan semua origin untuk akses API (penting untuk pengembangan React terpisah)
# KODE BARU (BENAR - Izinkan SEMUA):
CORS(app, resources={r"/*": {"origins": "*"}})

# --- KONFIGURASI SUPABASE & API LAIN ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FRIEND_API_URL = "https://yudhriz-api-absensi.hf.space/verify"

ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")



supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BATAS_TELAT = time(8, 0, 0) 
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
        photo = request.files.get('photo')

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
# Pastikan helper ini ada (seperti diskusi sebelumnya)
def determine_status(check_in_time_str):
    try:
        # Parsing string jam
        h, m = map(int, check_in_time_str.split(':'))
        check_in_time = time(h, m, 0)
        if check_in_time > BATAS_TELAT: # Pastikan variabel global BATAS_TELAT sudah didefinisikan
            return "Telat"
        return "Tepat Waktu"
    except:
        return "Hadir"

# 5. API CRUD MANUAL ABSENSI (ANTI DUPLICATE)
@app.route('/api/attendance/manual', methods=['POST'])
def manual_attendance():
    try:
        data = request.get_json()

        employee_id = data.get("employee_id")
        date = data.get("date")
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        
        # Ambil status manual jika admin mengisi, jika tidak biarkan None dulu
        input_status = data.get("attendance_status")
    
        if not employee_id or not date:
            return jsonify({"error": "employee_id dan date wajib"}), 400
        
        if not check_in and not check_out:
            return jsonify({"error": "Gagal: Jam Masuk atau Jam Keluar harus diisi!"}), 400

        # Tentukan rentang waktu hari itu untuk pengecekan
        start_of_day = f"{date}T00:00:00"
        end_of_day = f"{date}T23:59:59"

        # --- PROSES CHECK-IN ---
        if check_in:
            # 1. Cek apakah Check-In sudah ada di tanggal tersebut?
            existing_in = supabase.table("attendance_records").select("id") \
                .eq("employee_id", employee_id) \
                .eq("type", "check_in") \
                .gte("timestamp", start_of_day) \
                .lte("timestamp", end_of_day) \
                .execute()

            # Jika data ditemukan, tolak request
            if existing_in.data:
                return jsonify({
                    "error": f"Gagal: Data Check-In untuk karyawan ini pada tanggal {date} SUDAH ADA."
                }), 409 # 409 Conflict

            # 2. Tentukan status (Otomatis atau Manual)
            final_status = input_status
            if not final_status:
                final_status = determine_status(check_in)

            # 3. Lakukan Insert
            supabase.table("attendance_records").insert({
                "employee_id": employee_id,
                "timestamp": f"{date}T{check_in}:00",
                "type": "check_in",
                "attendance_status": final_status
            }).execute()

        # --- PROSES CHECK-OUT ---
        if check_out:
            # 1. Cek apakah Check-Out sudah ada di tanggal tersebut?
            existing_out = supabase.table("attendance_records").select("id") \
                .eq("employee_id", employee_id) \
                .eq("type", "check_out") \
                .gte("timestamp", start_of_day) \
                .lte("timestamp", end_of_day) \
                .execute()

            # Jika data ditemukan, tolak request
            if existing_out.data:
                return jsonify({
                    "error": f"Gagal: Data Check-Out untuk karyawan ini pada tanggal {date} SUDAH ADA."
                }), 409 # 409 Conflict

            # 2. Lakukan Insert (Status pulang biasanya netral/Hadir/Inputan Admin)
            supabase.table("attendance_records").insert({
                "employee_id": employee_id,
                "timestamp": f"{date}T{check_out}:00",
                "type": "check_out",
                "attendance_status": input_status or "Hadir"
            }).execute()

        return jsonify({"success": True, "message": "Data manual berhasil ditambahkan"})
    
    except Exception as e:
        print(f"Error Manual Attendance: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/attendance/<int:record_id>', methods=['PUT'])
def update_attendance(record_id):
    try:
        data = request.get_json()

        # Data BARU yang diinginkan user
        new_date_val = data.get("date")          # Format: YYYY-MM-DD
        new_check_in_time = data.get("check_in") # Format: HH:MM
        new_check_out_time = data.get("check_out") # Format: HH:MM
        new_status = data.get("attendance_status")

        # 1. AMBIL DATA LAMA DULU (PENTING!)
        # Kita butuh employee_id DAN tanggal lama (timestamp) untuk mencari pasangannya
        current_record = supabase.table("attendance_records").select("*").eq("id", record_id).execute()
        
        if not current_record.data:
            return jsonify({"error": "Record not found"}), 404
            
        old_data = current_record.data[0]
        employee_id = old_data['employee_id']
        
        # Ambil tanggal lama dari timestamp yang tersimpan di DB
        # Asumsi format timestamp di DB: "2025-11-30T08:00:00"
        original_timestamp_str = old_data['timestamp'] 
        original_date = original_timestamp_str.split("T")[0] # Ambil YYYY-MM-DD lama

        # ==========================================
        # 2. UPDATE CHECK IN
        # Cari record check_in milik user ini di TANGGAL LAMA, lalu update ke TANGGAL BARU
        # ==========================================
        if new_check_in_time:
            new_in_ts = f"{new_date_val}T{new_check_in_time}:00"
            
            # Query: Cari data employee ini, tipe check_in, di tanggal ASLI (original_date)
            supabase.table("attendance_records").update({
                "timestamp": new_in_ts
            }).match({
                "employee_id": employee_id,
                "type": "check_in"
            }).gte("timestamp", f"{original_date}T00:00:00").lte("timestamp", f"{original_date}T23:59:59").execute()

        # ==========================================
        # 3. UPDATE CHECK OUT
        # ==========================================
        if new_check_out_time:
            new_out_ts = f"{new_date_val}T{new_check_out_time}:00"
            update_payload = {"timestamp": new_out_ts}
            if new_status:
                update_payload["attendance_status"] = new_status

            # Cek dulu apakah data check_out sudah ada di tanggal lama?
            check_out_exist = supabase.table("attendance_records").select("id").match({
                "employee_id": employee_id,
                "type": "check_out"
            }).gte("timestamp", f"{original_date}T00:00:00").lte("timestamp", f"{original_date}T23:59:59").execute()

            if check_out_exist.data:
                # Kalo ada, kita UPDATE record tanggal lama itu ke tanggal baru
                supabase.table("attendance_records").update(update_payload).eq("id", check_out_exist.data[0]['id']).execute()
            else:
                # Kalo sebelumnya gak ada (misal lupa absen pulang), kita INSERT baru di tanggal baru
                supabase.table("attendance_records").insert({
                    "employee_id": employee_id,
                    "timestamp": new_out_ts,
                    "type": "check_out",
                    "attendance_status": new_status or "Hadir"
                }).execute()
        
        # (Opsional) Jika user menghapus jam check_out (kosong), kita bisa hapus row check_out
        elif not new_check_out_time and old_data['type'] == 'check_out':
             # Logic penghapusan bisa ditambahkan di sini jika perlu
             pass

        return jsonify({"success": True})

    except Exception as e:
        print(f"Error backend: {e}")
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

@app.route('/api/record-attendance', methods=['POST'])
def record_attendance():
    try:
        rfid_uid = request.form.get('rfid')
        live_image = request.files.get('live_image')

        if not rfid_uid or not live_image:
            return jsonify({"error": "Data tidak lengkap"}), 400

        # ============================================
        # 1. AMBIL DATA KARYAWAN
        # ============================================
        emp_res = supabase.table('employees') \
            .select('id, name') \
            .eq('rfid_uid', rfid_uid) \
            .single() \
            .execute()

        if not emp_res or not emp_res.data:
            return jsonify({"error": "ID Karyawan tidak ditemukan"}), 404

        employee = emp_res.data

        # ============================================
        # 2. VERIFIKASI WAJAH KE API TEMAN
        # ============================================
        files = {'file': (live_image.filename, live_image.stream, live_image.mimetype)}
        data = {'user_id': rfid_uid}

        try:
            api_response = requests.post(FRIEND_API_URL, files=files, data=data, timeout=30)
            api_result = api_response.json() if api_response.content else {}
        except:
            return jsonify({"error": "Gagal menghubungi server AI"}), 502

        if api_response.status_code != 200:
            return jsonify({"error": "Wajah tidak cocok", "details": api_result}), 401

        distance = 1.0 # Default angka jelek (tidak mirip)
        
        # Cek berbagai kemungkinan format JSON dari API
        if 'details' in api_result and 'distance' in api_result['details']:
            distance = api_result['details']['distance']
        elif 'distance' in api_result:
            distance = api_result['distance']
        elif 'attendance_data' in api_result and 'distance' in api_result['attendance_data']:
             distance = api_result['attendance_data']['distance']

        # 2. TENTUKAN BATAS (Threshold)
        MAX_DISTANCE = 0.60 

        # 3. LOGIKA PENOLAKAN
        # Jika distance di atas 0.60, STOP! Jangan biarkan kode lanjut ke bawah (penyimpanan DB).
        if distance > MAX_DISTANCE:
            print(f"⛔ DITOLAK SERVER: Distance {distance} terlalu jauh!")
            return jsonify({
                "error": "Wajah tidak cocok. Absensi Ditolak.",
                "distance": distance,
                "threshold": MAX_DISTANCE
            }), 400            

        # ============================================
        # 3. PERSIAPAN WAKTU
        # ============================================
        # 3. PERSIAPAN WAKTU
        tz_jakarta = pytz.timezone('Asia/Jakarta')
        now = datetime.now(tz_jakarta) 
        today = now.date()

        # 4. CEK STATUS CHECK-IN HARI INI
        checkin_res = supabase.table('attendance_records') \
            .select('*') \
            .eq('employee_id', employee['id']) \
            .eq('type', 'check_in') \
            .filter('timestamp', 'gte', f"{today}T00:00:00") \
            .order('timestamp', desc=False) \
            .maybe_single() \
            .execute()

        today_checkin = checkin_res.data if checkin_res and checkin_res.data else None

        # 5. LOGIKA ABSENSI
        
        # --- SKENARIO A: BELUM CHECK-IN ---
        if today_checkin is None:
            check_in_time = now.time()
            status = "Telat" if check_in_time > BATAS_TELAT else "Tepat Waktu"

            # === FIX: HAPUS .select() DAN TAMBAH TRY-EXCEPT KHUSUS ===
            try:
                supabase.table('attendance_records').insert({
                    "employee_id": employee['id'],
                    "timestamp": now.isoformat(),
                    "type": "check_in",
                    "attendance_status": status
                }).execute()
            except Exception as e:
                # Jika error mengandung "204" atau "Missing response", itu artinya BERHASIL disimpan
                # Kita abaikan errornya (pass)
                if "204" in str(e) or "Missing response" in str(e):
                    pass 
                else:
                    raise e # Kalau error lain (misal koneksi putus), baru kita lempar errornya

            return jsonify({
                "success": True,
                "message": "Check-in Berhasil!",
                "status": status,
                "time": now.strftime("%H:%M"),
                "details": api_result
            }), 200

        # --- SKENARIO B: SUDAH CHECK-IN (LANJUT CEK CHECK-OUT) ---
        else:
            # Cek apakah SUDAH check-out hari ini?
            checkout_res = supabase.table('attendance_records') \
                .select('*') \
                .eq('employee_id', employee['id']) \
                .eq('type', 'check_out') \
                .filter('timestamp', 'gte', f"{today}T00:00:00") \
                .maybe_single() \
                .execute()
            
            today_checkout = checkout_res.data if checkout_res and checkout_res.data else None

            # JIKA SUDAH ADA DATA CHECK-OUT -> BLOCK
            if today_checkout:
                return jsonify({
                    "error": "Anda sudah selesai absen hari ini (Sudah Check-Out/Pulang).",
                    "status": "Selesai"
                }), 400

            # JIKA BELUM ADA DATA CHECK-OUT -> LAKUKAN CHECK-OUT
            # === FIX: HAPUS .select() DAN TAMBAH TRY-EXCEPT KHUSUS ===
            try:
                supabase.table('attendance_records').insert({
                    "employee_id": employee['id'],
                    "timestamp": now.isoformat(),
                    "type": "check_out",
                    "attendance_status": "Hadir"
                }).execute()
            except Exception as e:
                # Abaikan error 204 (Missing response) karena itu berarti sukses
                if "204" in str(e) or "Missing response" in str(e):
                    pass
                else:
                    raise e

            return jsonify({
                "success": True,
                "message": "Check-out Berhasil!",
                "status": "Hadir",
                "time": now.strftime("%H:%M"),
                "details": api_result
            }), 200

    except Exception as e:
        print("ERROR SYSTEM:", e)
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
        photo = request.files.get('photo') # Foto opsional saat edit

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
    
# Helper untuk ambil setting alat (ID=1)
def get_device_setting():
    # Ambil data dari table device_settings baris pertama (id=1)
    res = supabase.table('device_settings').select('*').eq('id', 1).single().execute()
    return res.data

# 1. Endpoint untuk Website: Cek Status & Ambil UID
@app.route('/web/status', methods=['GET'])
def get_status_web():
    try:
        setting = get_device_setting()
        
        # Logika: Jika data UID sudah lama (misal > 10 detik lalu), anggap null agar tidak terbaca ulang
        # (Opsional, di frontend sudah ada logic filter duplicate, tapi ini safety)
        
        return jsonify({
            "is_active": setting['is_active'],
            "latest_uid": setting['latest_uid']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. Endpoint untuk Website: Tombol ON/OFF
@app.route('/web/toggle', methods=['POST'])
def toggle_device():
    try:
        data = request.json
        new_status = data.get('active')
        
        # Update ke Supabase
        supabase.table('device_settings').update({
            'is_active': new_status,
            'latest_uid': None # Reset UID saat status berubah
        }).eq('id', 1).execute()
        
        return jsonify({"message": "Status berhasil diupdate", "current_status": new_status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. Endpoint untuk ALAT (NodeMCU): Cek apakah boleh scan?
@app.route('/iot/check_active', methods=['GET'])
def check_active():
    try:
        setting = get_device_setting()
        return jsonify({"is_active": setting['is_active']})
    except:
        # Default aman jika error database
        return jsonify({"is_active": False}) 

# 4. Endpoint untuk ALAT (NodeMCU): Kirim UID Kartu
@app.route('/iot/upload_uid', methods=['POST'])
def upload_uid():
    try:
        # 1. Cek dulu statusnya ON atau OFF
        setting = get_device_setting()
        
        if not setting['is_active']:
            return jsonify({"message": "Device is OFF (Rejected)"}), 403
        
        data = request.json
        uid = data.get('uid')
        
        if uid:
            print(f"📡 [IoT] Kartu Diterima: {uid}")
            # 2. Update UID ke Supabase dan update waktu 'last_updated'
            now_iso = datetime.now(pytz.timezone('Asia/Jakarta')).isoformat()
            
            supabase.table('device_settings').update({
                'latest_uid': uid,
                'last_updated': now_iso
            }).eq('id', 1).execute()
            
            return jsonify({"status": "success"})
        
        return jsonify({"status": "error", "message": "No UID"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

if __name__ == '__main__':
    app.run(debug=True)