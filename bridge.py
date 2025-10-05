import asyncio
import websockets
import serial
import sys

# --- PENGATURAN ---
SERIAL_PORT = 'COM4' 
BAUD_RATE = 9600
WEBSOCKET_HOST = 'localhost'
WEBSOCKET_PORT = 8765
# ------------------

connected_clients = set()

async def register(websocket):
    """Mendaftarkan koneksi baru."""
    print(f"🖥️  Browser terhubung: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        print(f"🔴 Browser terputus: {websocket.remote_address}")
        connected_clients.remove(websocket)

async def serial_reader():
    """Membaca data dari serial port dan mengirimkannya ke semua browser."""
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
                print(f"✅ Berhasil terhubung ke Arduino di port {SERIAL_PORT}")
                # Beri waktu sejenak agar data 'sampah' saat boot lewat
                await asyncio.sleep(2) 
                
                while True:
                    # Baca satu baris data UID dari Arduino
                    uid_line = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    # Hanya kirim jika UID tidak kosong (menghindari baris kosong)
                    if uid_line:
                        print(f"💳 Kartu terdeteksi! UID: {uid_line}")
                        # Kirim UID ke semua browser yang terhubung
                        if connected_clients:
                            await asyncio.wait([client.send(uid_line) for client in connected_clients])
        except serial.SerialException:
            print(f"🔌 Gagal terhubung ke Arduino di port {SERIAL_PORT}. Mencoba lagi dalam 5 detik...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Terjadi error pada pembaca serial: {e}")
            await asyncio.sleep(5)

async def main():
    """Menjalankan server WebSocket dan pembaca serial secara bersamaan."""
    print(f"🚀 Menjalankan server jembatan di ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    
    # Menjalankan server WebSocket dan pembaca serial sebagai dua tugas terpisah
    server = websockets.serve(register, WEBSOCKET_HOST, WEBSOCKET_PORT)
    serial_task = asyncio.create_task(serial_reader())

    await asyncio.gather(server, serial_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram dihentikan.")
    except OSError as e:
        if e.winerror == 10048:
             print("\nERROR: Port 8765 sudah digunakan oleh program lain. Tutup program tersebut dan coba lagi.")
        else:
             print(f"\nTerjadi OS Error: {e}")