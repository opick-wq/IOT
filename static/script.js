document.addEventListener('DOMContentLoaded', () => {
    // --- 1. Mengambil semua elemen HTML yang dibutuhkan ---
    const mainContent = document.getElementById('main-content');
    const verificationContent = document.getElementById('verification-content');
    const statusMessage = document.getElementById('status-message');
    
    const storedPhoto = document.getElementById('stored-photo');
    const employeeName = document.getElementById('employee-name');
    const employeeStatus = document.getElementById('employee-status');
    
    const webcamElement = document.getElementById('webcam');
    const canvasElement = document.getElementById('canvas');
    const captureBtn = document.getElementById('capture-btn');

    let currentRfid = null; // Menyimpan RFID yang sedang diproses
    let stream = null; // Menyimpan stream dari webcam

    // --- 2. Koneksi ke Program Jembatan via WebSocket ---
    // Program jembatan (bridge.py) harus berjalan di komputer Anda.
    const ws = new WebSocket('ws://localhost:8765');

    // Saat koneksi berhasil dibuka
    ws.onopen = function() {
        console.log("Terhubung ke program jembatan (bridge.py).");
        updateStatus("Alat pembaca terhubung. Silakan tempelkan kartu RFID Anda.", "info");
    };

    // Saat menerima pesan (UID kartu) dari jembatan
    ws.onmessage = function(event) {
        const rfid = event.data;
        console.log(`UID diterima dari jembatan: ${rfid}`);
        
        // Hanya proses UID baru jika tidak ada sesi absensi yang sedang berjalan
        if (!currentRfid) { 
            handleRfidTap(rfid);
        }
    };

    // Saat koneksi ditutup
    ws.onclose = function() {
        console.log("Koneksi ke program jembatan terputus.");
        updateStatus("Koneksi ke alat pembaca terputus! Pastikan program bridge.py berjalan.", "error");
    };
    
    // Jika terjadi error koneksi
    ws.onerror = function() {
        console.error("Gagal terhubung ke WebSocket server.");
        updateStatus("Gagal terhubung ke alat pembaca! Jalankan program bridge.py di komputer Anda.", "error");
    };

    // --- 3. Fungsi Utama untuk Memproses RFID ---
    async function handleRfidTap(rfid) {
        currentRfid = rfid; // Kunci sesi absensi dengan RFID ini
        updateStatus('Mencari data karyawan...', 'loading');

        try {
            // Meminta data karyawan dari server Vercel
            const response = await fetch('/api/get-employee-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rfid: rfid })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || 'Karyawan tidak ditemukan');
            }

            const employee = await response.json();
            displayVerificationUI(employee); // Jika ditemukan, tampilkan UI verifikasi

        } catch (error) {
            updateStatus(error.message, 'error');
            // Gagal, reset UI setelah 3 detik
            setTimeout(resetUI, 3000);
        }
    }

    // --- 4. Fungsi untuk Menampilkan UI Verifikasi & Kamera ---
    async function displayVerificationUI(employee) {
        mainContent.classList.add('hidden');
        verificationContent.classList.remove('hidden');
        
        // Tampilkan data karyawan
        storedPhoto.src = employee.image_url;
        employeeName.textContent = employee.name;
        employeeStatus.textContent = employee.status;
        
        updateStatus('Posisikan wajah Anda di depan kamera.', 'info');
        await startWebcam(); // Nyalakan webcam
    }

    async function startWebcam() {
        try {
            if (stream) {
                stream.getTracks().forEach(track => track.stop()); // Matikan stream lama jika ada
            }
            // Minta izin dan akses ke kamera
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            webcamElement.srcObject = stream;
            captureBtn.disabled = false; // Aktifkan tombol absen
        } catch (error) {
            console.error("Error mengakses webcam:", error);
            updateStatus('Gagal mengakses kamera! Izinkan akses kamera di browser Anda.', 'error');
            captureBtn.disabled = true;
        }
    }
    
    // --- 5. Event Listener untuk Tombol Ambil Foto & Absen ---
    captureBtn.addEventListener('click', async () => {
        captureBtn.disabled = true; // Nonaktifkan tombol saat proses
        updateStatus('Memproses verifikasi wajah dan mencatat absensi...', 'loading');

        // Menggambar frame dari video ke canvas
        canvasElement.width = webcamElement.videoWidth;
        canvasElement.height = webcamElement.videoHeight;
        const context = canvasElement.getContext('2d');
        context.translate(canvasElement.width, 0);
        context.scale(-1, 1); // Balik gambar agar tidak seperti cermin
        context.drawImage(webcamElement, 0, 0, canvasElement.width, canvasElement.height);

        // Konversi gambar di canvas menjadi file Blob
        canvasElement.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append('rfid', currentRfid);
            formData.append('live_image', blob, 'capture.jpg');
            
            try {
                // Kirim RFID dan file gambar ke server Vercel
                const response = await fetch('/api/verify-and-record', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.error || 'Verifikasi gagal');
                }

                updateStatus(result.message, 'success');
                setTimeout(resetUI, 5000); // Reset UI setelah 5 detik jika berhasil

            } catch (error) {
                updateStatus(error.message, 'error');
                captureBtn.disabled = false; // Aktifkan lagi tombol jika gagal
            }

        }, 'image/jpeg');
    });

    // --- 6. Fungsi Bantuan (Helpers) ---
    function updateStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className = type; // (e.g., 'success', 'error', 'info')
    }

    function resetUI() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop()); // Matikan kamera
        }
        mainContent.classList.remove('hidden');
        verificationContent.classList.add('hidden');
        currentRfid = null; // Reset sesi RFID
        updateStatus("Silakan tempelkan kartu RFID Anda.", "info");
    }
});