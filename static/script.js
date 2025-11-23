document.addEventListener('DOMContentLoaded', () => {
    const mainContent = document.getElementById('main-content');
    const verificationContent = document.getElementById('verification-content');
    const statusMessage = document.getElementById('status-message');
    const storedPhoto = document.getElementById('stored-photo');
    const employeeName = document.getElementById('employee-name');
    const employeeStatus = document.getElementById('employee-status');
    const webcamElement = document.getElementById('webcam');
    const canvasElement = document.getElementById('canvas');
    const captureBtn = document.getElementById('capture-btn');
    const initialMessage = document.getElementById('initial-message');

    let isPolling = true;
    let lastUid = null;
    let currentEmployee = null;
    let stream = null;

    // Konfigurasi Ambang Batas Lokal
    // Jarak di atas ini akan ditolak, meskipun server bilang OK.
    // Semakin kecil = Semakin ketat. 0.50 adalah standar yang cukup ketat.
    const LOCAL_DISTANCE_THRESHOLD = 0.55; 

    if(initialMessage) initialMessage.textContent = "Menunggu Kartu...";

    // --- 1. POLLING UID ---
    async function pollForUid() {
        if (!isPolling) return;
        try {
            const response = await fetch('http://localhost:5000/get_latest_uid');
            const data = await response.json();
            if (data && data.uid && data.uid !== lastUid) {
                console.log(`💳 UID DITERIMA: ${data.uid}`);
                lastUid = data.uid;
                isPolling = false;
                handleRfidTap(data.uid);
            }
        } catch (error) { /* Silent fail */ }
    }
    setInterval(pollForUid, 2000);

    // --- 2. AMBIL DATA KARYAWAN ---
    async function handleRfidTap(rfid) {
        updateStatus('Mencari data karyawan...', 'loading');
        try {
            const response = await fetch('/api/get-employee-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rfid: rfid })
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);

            currentEmployee = result;
            if (!currentEmployee.rfid_uid) currentEmployee.rfid_uid = rfid; 
            
            displayCameraUI(result);
        } catch (error) {
            updateStatus(error.message, 'error');
            setTimeout(resetUI, 3000);
        }
    }

    // --- 3. TAMPILKAN KAMERA ---
    async function displayCameraUI(employee) {
        mainContent.classList.add('hidden');
        verificationContent.classList.remove('hidden');
        
        storedPhoto.src = employee.image_url;
        employeeName.textContent = employee.name;
        employeeStatus.textContent = employee.status;
        
        updateStatus('Silakan ambil foto untuk verifikasi.', 'info');
        resetCaptureButton();
        
        try {
            if (stream) stream.getTracks().forEach(track => track.stop());
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            webcamElement.srcObject = stream;
        } catch (error) {
            updateStatus('Gagal akses kamera.', 'error');
        }
    }
    
    function resetCaptureButton() {
        captureBtn.disabled = false;
        captureBtn.textContent = "Ambil Foto & Verifikasi";
        captureBtn.classList.remove('btn-retry');
    }

    // --- 4. PROSES VERIFIKASI ---
    captureBtn.addEventListener('click', async () => {
        if (captureBtn.classList.contains('btn-retry')) {
            updateStatus('Silakan ambil foto ulang.', 'info');
            resetCaptureButton();
            return;
        }

        captureBtn.disabled = true;
        captureBtn.textContent = "Memverifikasi...";
        updateStatus('Sedang memverifikasi wajah...', 'loading');

        canvasElement.width = webcamElement.videoWidth;
        canvasElement.height = webcamElement.videoHeight;
        const ctx = canvasElement.getContext('2d');
        ctx.drawImage(webcamElement, 0, 0);

        canvasElement.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append('rfid', currentEmployee.rfid_uid);
            formData.append('live_image', blob, 'capture.jpg');
            
            try {
                const response = await fetch('/api/record-attendance', { 
                    method: 'POST', body: formData 
                });
                const result = await response.json();

                // --- LOGGING ---
                console.log("========================================");
                console.log(`📡 STATUS API: ${response.ok ? "OK" : "GAGAL"}`);
                let distance = 1.0; // Default jarak jauh (tidak mirip)
                
                if (result.details && result.details.distance !== undefined) {
                    distance = result.details.distance;
                    console.log(`📏 Jarak dari Server: ${distance}`);
                }
                console.log("========================================");

                if (!response.ok) {
                    throw new Error(result.error || 'Verifikasi Gagal');
                }

                // --- PENGECEKAN GANDA (DOUBLE CHECK) ---
                // Jika server bilang OK, tapi jaraknya masih terlalu jauh menurut standar kita
                if (distance > LOCAL_DISTANCE_THRESHOLD) {
                     console.warn(`⚠️ Server menerima, tapi ditolak browser karena jarak ${distance} > ${LOCAL_DISTANCE_THRESHOLD}`);
                     throw new Error(`Wajah tidak cukup mirip. Jarak: ${distance.toFixed(3)}`);
                }

                updateStatus(result.message, 'success');
                setTimeout(resetUI, 4000); 

            } catch (error) {
                updateStatus(error.message + " Silakan coba lagi.", 'error');
                captureBtn.disabled = false;
                captureBtn.textContent = "Coba Lagi";
                captureBtn.classList.add('btn-retry');
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
        updateStatus("Silakan tempelkan kartu RFID Anda.", "info");
        isPolling = true; 
        lastUid = null;
        currentEmployee = null;
    }
});