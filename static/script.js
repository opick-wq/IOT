// ============== SCRIPT.JS FINAL (VERIFIKASI WAJAH DI BROWSER) ==============
document.addEventListener('DOMContentLoaded', async () => {
    // --- 1. Mengambil semua elemen HTML yang dibutuhkan ---
    const mainContent = document.getElementById('main-content');
    const verificationContent = document.getElementById('verification-content');
    const statusMessage = document.getElementById('status-message');
    const storedPhoto = document.getElementById('stored-photo');
    const employeeName = document.getElementById('employee-name');
    const employeeStatus = document.getElementById('employee-status');
    const webcamElement = document.getElementById('webcam');
    const captureBtn = document.getElementById('capture-btn');
    const initialMessage = document.getElementById('initial-message');

    // --- 2. Variabel Global ---
    let isPolling = false;
    let currentEmployee = null;
    let storedFaceDescriptor = null;
    let stream = null;

    // --- 3. MEMUAT MODEL AI DARI FOLDER /static/models ---
    async function loadModels() {
        const MODEL_URL = '/static/models'; // Path ke folder model Anda
        try {
            // Memuat model yang dibutuhkan untuk deteksi dan pengenalan wajah
            await faceapi.nets.ssdMobilenetv1.loadFromUri(MODEL_URL);
            await faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL);
            await faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL);
            
            console.log("✅ Model AI berhasil dimuat!");
            initialMessage.textContent = "Menunggu Kartu...";
            updateStatus("Alat pembaca terhubung. Silakan tempelkan kartu.", "info");
            isPolling = true; // Mulai polling setelah model siap
        } catch (error) {
            console.error("Gagal memuat model AI:", error);
            initialMessage.textContent = "Gagal memuat model AI. Coba refresh halaman.";
            updateStatus("Gagal memuat model AI.", "error");
        }
    }
    // Memuat model saat halaman pertama kali dibuka
    loadModels();
    
    // --- 4. POLLING UNTUK UID DARI JEMBATAN HTTP ---
    async function pollForUid() {
        if (!isPolling) return;
        try {
            const response = await fetch('http://localhost:5000/get_latest_uid');
            const data = await response.json();
            if (data && data.uid) {
                console.log(`💳 UID DITERIMA: ${data.uid}`);
                isPolling = false; // Hentikan polling saat UID diterima
                await handleRfidTap(data.uid);
            }
        } catch (error) {
            // Error ini hanya akan muncul jika bridge_http.py tidak berjalan
            // Tidak perlu update status agar tidak mengganggu pesan "Memuat model AI..."
        }
    }
    setInterval(pollForUid, 2000);

    // --- 5. PROSES SETELAH KARTU DI-TAP ---
    async function handleRfidTap(rfid) {
        updateStatus('Mencari data karyawan...', 'loading');
        try {
            const response = await fetch('/api/get-employee-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rfid: rfid })
            });
            const employee = await response.json();
            if (!response.ok) throw new Error(employee.error);

            currentEmployee = employee;
            await displayVerificationUI(employee);
        } catch (error) {
            updateStatus(error.message, 'error');
            setTimeout(resetUI, 4000);
        }
    }

    // --- 6. TAMPILKAN UI VERIFIKASI ---
    async function displayVerificationUI(employee) {
        mainContent.classList.add('hidden');
        verificationContent.classList.remove('hidden');
        storedPhoto.src = employee.image_url;
        employeeName.textContent = employee.name;
        employeeStatus.textContent = employee.status;

        updateStatus('Menganalisis foto terdaftar...', 'loading');
        
        // Buat "sidik jari digital" (face descriptor) dari foto yang terdaftar
        try {
            // Muat gambar dari URL Supabase, atasi masalah CORS
            const registeredImage = await faceapi.fetchImage(employee.image_url);
            // Deteksi wajah dan hitung sidik jarinya
            storedFaceDescriptor = await faceapi.computeFaceDescriptor(registeredImage);
            
            if (!storedFaceDescriptor) {
                // Jika tidak ada wajah di foto pendaftaran
                throw new Error();
            }
            
            updateStatus('Posisikan wajah Anda di depan kamera.', 'info');
            await startWebcam();
        } catch (error) {
            console.error(error);
            updateStatus("Wajah tidak terdeteksi di foto pendaftaran!", "error");
            setTimeout(resetUI, 4000);
        }
    }

    // --- 7. NYALAKAN WEBCAM ---
    async function startWebcam() {
        try {
            if (stream) stream.getTracks().forEach(track => track.stop());
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            webcamElement.srcObject = stream;
            // Tunggu sebentar agar kamera siap
            webcamElement.onloadedmetadata = () => {
                captureBtn.disabled = false;
            };
        } catch (error) {
            updateStatus('Gagal mengakses kamera! Izinkan akses di browser Anda.', 'error');
        }
    }
    
    // --- 8. PROSES VERIFIKASI SAAT TOMBOL DITEKAN ---
    captureBtn.addEventListener('click', async () => {
        captureBtn.disabled = true;
        updateStatus('Memverifikasi wajah...', 'loading');

        try {
            // Buat "sidik jari digital" dari wajah di webcam
            const liveDescriptor = await faceapi.computeFaceDescriptor(webcamElement);
            if (!liveDescriptor) {
                throw new Error("Wajah tidak terdeteksi di kamera!");
            }
            
            // Bandingkan kedua sidik jari menggunakan jarak Euclidean
            const distance = faceapi.euclideanDistance(storedFaceDescriptor, liveDescriptor);
            // Semakin kecil jarak, semakin mirip.
            const similarity = 1 - distance;
            console.log(`✨ Jarak Wajah: ${distance}, Kemiripan: ${similarity}`);

            const SIMILARITY_THRESHOLD = 0.6; // Ambang batas (0.6 adalah standar yang baik)
            if (distance > SIMILARITY_THRESHOLD) {
                throw new Error(`Wajah tidak cocok! (Jarak: ${distance.toFixed(2)})`);
            }

            // --- JIKA COCOK, KIRIM DATA KE SERVER UNTUK DICATAT ---
            updateStatus('Wajah cocok! Mencatat absensi...', 'success');
            const response = await fetch('/api/record-attendance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rfid: currentEmployee.rfid_uid })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            
            updateStatus(result.message, 'success');
            setTimeout(resetUI, 5000);

        } catch (error) {
            updateStatus(error.message, 'error');
            // Jika gagal, aktifkan kembali tombol setelah jeda
            setTimeout(() => { captureBtn.disabled = false; }, 2000);
        }
    });

    // --- Fungsi Bantuan ---
    function updateStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className = type;
    }

    function resetUI() {
        if (stream) stream.getTracks().forEach(track => track.stop());
        mainContent.classList.remove('hidden');
        verificationContent.classList.add('hidden');
        captureBtn.disabled = true;
        updateStatus("Silakan tempelkan kartu RFID Anda.", "info");
        currentEmployee = null;
        storedFaceDescriptor = null;
        isPolling = true;
    }
});