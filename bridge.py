import asyncio
import websockets
import serial
import sys

# --- PENGATURAN ---
# Pastikan port ini sudah benar sesuai Arduino IDE Anda
SERIAL_PORT = 'COM4' 
BAUD_RATE = 9600
WEBSOCKET_HOST = 'localhost'
WEBSOCKET_PORT = 8765
# ------------------

# Set untuk menyimpan koneksi browser yang aktif
connected_clients = set()

async def serial_reader(websocket_server):
    """Membaca data dari serial port dan mengirimkannya ke semua browser."""
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                print(f"✅ Berhasil terhubung ke Arduino di port {SERIAL_PORT}")
                while True:
                    # Baca satu baris data UID dari Arduino
                    # Tambahkan errors='ignore' untuk membuang data 'sampah' saat booting
                    uid_line = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    if uid_line:
                        print(f"💳 Kartu terdeteksi! UID: {uid_line}")
                        # Kirim UID ke semua browser yang terhubung
                        websockets.broadcast(connected_clients, uid_line)
        except serial.SerialException:
            print(f"🔌 Gagal terhubung ke Arduino di port {SERIAL_PORT}. Mencoba lagi dalam 5 detik...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Terjadi error: {e}")
            await asyncio.sleep(5)


async def handler(websocket, path):
    """Menangani koneksi baru dari browser."""
    print(f"🖥️  Browser terhubung: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        print(f"🔴 Browser terputus: {websocket.remote_address}")
        connected_clients.remove(websocket)


async def main():
    """Menjalankan server WebSocket dan pembaca serial."""
    print(f"🚀 Menjalankan server jembatan di ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    server = await websockets.serve(handler, WEBSOCKET_HOST, WEBSOCKET_PORT)
    await serial_reader(server)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram dihentikan.")