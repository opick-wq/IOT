// ============== SCRIPT.JS VERSI FINAL ==============
document.addEventListener('DOMContentLoaded', () => {
    // Definisi semua elemen (tidak berubah)
    const mainContent = document.getElementById('main-content');
    const verificationContent = document.getElementById('verification-content');
    const statusMessage = document.getElementById('status-message');
    const storedPhoto = document.getElementById('stored-photo');
    const employeeName = document.getElementById('employee-name');
    const employeeStatus = document.getElementById('employee-status');
    const webcamElement = document.getElementById('webcam');
    const canvasElement = document.getElementById('canvas');
    const captureBtn = document.getElementById('capture-btn');

    let currentRfid = null;
    let stream = null;
    
    function connectWebSocket() {
        console.log("🔌 Mencoba terhubung ke program jembatan di ws://localhost:8765...");
        const ws = new WebSocket('ws://localhost:8765');

        ws.onopen = function() {
            console.log("✅ KONEKSI BERHASIL! Menunggu UID dari Arduino...");
            updateStatus("Alat pembaca terhubung. Silakan tempelkan kartu RFID Anda.", "success");
        };

        ws.onmessage = function(event) {
            const rfid = event.data;
            // Pastikan data yang diterima adalah UID yang valid (bukan string kosong atau aneh)
            if (rfid && rfid.length > 4) {
                console.log(`💳 UID DITERIMA DI BROWSER: ${rfid}`);
                if (!currentRfid) { 
                    handleRfidTap(rfid);
                } else {
                    console.log("Sesi absensi lain sedang berjalan, UID diabaikan.");
                }
            } else {
                console.warn(`Data tidak valid diterima dari jembatan: '${rfid}'`);
            }
        };

        ws.onclose = function() {
            console.error("🔴 KONEKSI TERPUTUS! Mencoba menghubungkan kembali dalam 5 detik...");
            updateStatus("Koneksi ke alat pembaca terputus! Pastikan bridge.py berjalan.", "error");
            // Coba hubungkan kembali setelah 5 detik
            setTimeout(connectWebSocket, 5000); 
        };
        
        ws.onerror = function(error) {
            console.error("❌ Terjadi Error pada WebSocket:", error);
            // onclose akan otomatis terpanggil setelah onerror, jadi tidak perlu pesan ganda
        };
    }

    // Mulai koneksi WebSocket saat halaman dimuat
    connectWebSocket();

    // Semua fungsi lain (handleRfidTap, displayVerificationUI, startWebcam, dll)
    // tetap sama persis seperti sebelumnya. Tidak perlu diubah.
    async function handleRfidTap(rfid) {
        currentRfid = rfid;
        updateStatus('Mencari data karyawan...', 'loading');
        try {
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
            displayVerificationUI(employee);
        } catch (error) {
            updateStatus(error.message, 'error');
            setTimeout(resetUI, 3000);
        }
    }

    async function displayVerificationUI(employee) {
        mainContent.classList.add('hidden');
        verificationContent.classList.remove('hidden');
        storedPhoto.src = employee.image_url;
        employeeName.textContent = employee.name;
        employeeStatus.textContent = employee.status;
        updateStatus('Posisikan wajah Anda di depan kamera.', 'info');
        await startWebcam();
    }

    async function startWebcam() {
        try {
            if (stream) stream.getTracks().forEach(track => track.stop());
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            webcamElement.srcObject = stream;
            captureBtn.disabled = false;
        } catch (error) {
            console.error("Error mengakses webcam:", error);
            updateStatus('Gagal mengakses kamera! Izinkan akses kamera di browser Anda.', 'error');
            captureBtn.disabled = true;
        }
    }
    
    captureBtn.addEventListener('click', async () => {
        captureBtn.disabled = true;
        updateStatus('Memproses verifikasi wajah...', 'loading');
        canvasElement.width = webcamElement.videoWidth;
        canvasElement.height = webcamElement.videoHeight;
        const context = canvasElement.getContext('2d');
        context.translate(canvasElement.width, 0);
        context.scale(-1, 1);
        context.drawImage(webcamElement, 0, 0, canvasElement.width, canvasElement.height);
        canvasElement.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append('rfid', currentRfid);
            formData.append('live_image', blob, 'capture.jpg');
            try {
                const response = await fetch('/api/verify-and-record', { method: 'POST', body: formData });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || 'Verifikasi gagal');
                updateStatus(result.message, 'success');
                setTimeout(resetUI, 5000);
            } catch (error) {
                updateStatus(error.message, 'error');
                captureBtn.disabled = false;
            }
        }, 'image/jpeg');
    });

    function updateStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className = type;
    }

    function resetUI() {
        if (stream) stream.getTracks().forEach(track => track.stop());
        mainContent.classList.remove('hidden');
        verificationContent.classList.add('hidden');
        currentRfid = null;
        updateStatus("Silakan tempelkan kartu RFID Anda.", "info");
    }
});