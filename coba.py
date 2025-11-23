import requests
import cv2

# URL API lokal kamu
url = "https://yudhriz-api-absensi.hf.space/verify"

# ID RFID yang mau dites (harus sama dengan yang di Supabase)
rfid_uid = "FA0C7982" 

print("📸 Tekan SPASI untuk ambil foto & kirim ke server...")

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    cv2.imshow('Simulasi IoT', frame)
    
    key = cv2.waitKey(1)
    
    if key == 32: # Tombol Spasi
        # Simpan foto sementara
        cv2.imwrite("test_capture.jpg", frame)
        print("🚀 Mengirim request ke API...")
        
        # Kirim ke API
        files = {'file': open('test_capture.jpg', 'rb')}
        data = {'user_id': rfid_uid}
        
        try:
            response = requests.post(url, files=files, data=data)
            print("\n--- RESPON SERVER ---")
            print(response.json())
            print("---------------------\n")
        except Exception as e:
            print(f"Error koneksi: {e}")
            
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()