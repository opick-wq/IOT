import os
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime
import numpy as np

# Muat environment variables
load_dotenv()

# Konfigurasi
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HUGGING_FACE_KEY = os.environ.get("HUGGING_FACE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ganti URL model di sini jika nanti memilih model lain
HF_API_URL = "https://api-inference.huggingface.co/models/radames/blip_image_embeddings"
HF_HEADERS = {
    "Authorization": f"Bearer {HUGGING_FACE_KEY}"
}

# Fungsi bantu
def get_image_embedding(image_bytes: bytes, content_type: str):
    """Kirim gambar ke HF inference API, dapatkan embedding."""
    headers = HF_HEADERS.copy()
    headers["Content-Type"] = content_type

    resp = requests.post(HF_API_URL, headers=headers, data=image_bytes)
    if resp.status_code != 200:
        print("💥 Hugging Face API Error", resp.status_code, resp.text)
        raise Exception(f"Hugging Face API error {resp.status_code}: {resp.text}")
    
    # Asumsikan response.json() adalah list of vectors
    embedding = resp.json()[0]
    return embedding

def cosine_similarity(vec1, vec2):
    arr1 = np.array(vec1)
    arr2 = np.array(vec2)
    return float(np.dot(arr1, arr2) / (np.linalg.norm(arr1) * np.linalg.norm(arr2)))

# Endpoint verifikasi
from flask import Flask
app = Flask(__name__)

@app.route('/api/verify-and-record', methods=['POST'])
def verify_and_record():
    try:
        rfid_uid = request.form.get('rfid')
        live_image_file = request.files.get('live_image')
        if not rfid_uid or not live_image_file:
            return jsonify({"error": "RFID atau gambar tidak dikirim"}), 400

        # Ambil data karyawan
        resp = supabase.table('employees')\
            .select('id, name, image_url')\
            .eq('rfid_uid', rfid_uid)\
            .single().execute()
        emp = resp.data
        if not emp:
            return jsonify({"error": "Karyawan tidak ditemukan"}), 404

        # Ambil foto tersimpan
        stored_resp = requests.get(emp['image_url'])
        if stored_resp.status_code != 200:
            return jsonify({"error": "Gagal unduh foto karyawan"}), 500

        print("🔍 Proses foto tersimpan …")
        stored_bytes = stored_resp.content
        stored_ct = stored_resp.headers.get('Content-Type', 'image/jpeg')
        stored_emb = get_image_embedding(stored_bytes, stored_ct)

        print("📸 Proses foto live …")
        live_bytes = live_image_file.read()
        live_ct = live_image_file.mimetype
        live_emb = get_image_embedding(live_bytes, live_ct)

        sim_score = cosine_similarity(stored_emb, live_emb)
        print(f"✨ Kemiripan wajah: {sim_score:.4f}")

        THRESHOLD = 0.90
        if sim_score < THRESHOLD:
            return jsonify({"error": f"Verifikasi gagal (kemiripan hanya {sim_score:.2%})"}), 401

        print("✅ Wajah cocok! Catat absensi …")
        today = datetime.now().strftime('%Y-%m-%d')
        rec_resp = supabase.table('attendance_records')\
            .select('id')\
            .eq('employee_id', emp['id'])\
            .filter('timestamp', 'gte', f"{today}T00:00:00").execute()

        status_type = 'check_out' if rec_resp.data else 'check_in'
        supabase.table('attendance_records').insert({
            'employee_id': emp['id'],
            'type': status_type
        }).execute()

        return jsonify({
            "success": True,
            "message": f"Absensi «{status_type}» untuk {emp['name']} berhasil (kemiripan: {sim_score:.2%})"
        }), 200

    except Exception as e:
        print("❌ Error saat verifikasi:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)