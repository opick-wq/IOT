import serial
import threading
import time
from flask import Flask, jsonify
from flask_cors import CORS

# --- PENGATURAN ---
SERIAL_PORT = 'COM4' 
BAUD_RATE = 9600
# ------------------

# Variabel global untuk menyimpan UID terakhir
latest_uid = None
last_read_time = 0

def read_from_arduino():
    """Fungsi ini berjalan di background untuk membaca serial."""
    global latest_uid, last_read_time
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                print(f"✅ Berhasil terhubung ke Arduino di port {SERIAL_PORT}")
                while True:
                    line = ser.readline().decode('utf-8').strip()
                    if line:
                        latest_uid = line
                        last_read_time = time.time()
                        print(f"💳 Kartu terdeteksi! UID: {latest_uid}")
        except serial.SerialException:
            print(f"🔌 Gagal terhubung ke Arduino. Mencoba lagi dalam 5 detik...")
            time.sleep(5)
        except Exception as e:
            print(f"Error di thread serial: {e}")
            time.sleep(5)

# Setup server Flask
app = Flask(__name__)
CORS(app) # Mengizinkan koneksi dari website Vercel

@app.route('/get_latest_uid')
def get_latest_uid():
    """Endpoint yang akan ditanya oleh browser."""
    global latest_uid, last_read_time
    # Hanya kirim UID jika baru dibaca dalam 2 detik terakhir
    # Ini mencegah browser mendapatkan UID yang sama berulang kali
    if latest_uid and (time.time() - last_read_time < 2):
        uid_to_send = latest_uid
        latest_uid = None # Reset setelah dikirim
        return jsonify({"uid": uid_to_send})
    return jsonify({"uid": None}) # Kirim null jika tidak ada UID baru

if __name__ == '__main__':
    # Jalankan pembaca serial di thread terpisah
    serial_thread = threading.Thread(target=read_from_arduino, daemon=True)
    serial_thread.start()
    
    # Jalankan server web Flask di port 5000
    print("🚀 Menjalankan server jembatan HTTP di http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)