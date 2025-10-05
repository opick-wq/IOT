// ============== SCRIPT.JS VERSI FINAL (HTTP POLLING) ==============
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

    let isPolling = true;
    let lastUid = null;
    let currentRfid = null;
    let stream = null; // <-- DEKLARASI PENTING

    async function pollForUid() {
        if (!isPolling) return;
        try {
            const response = await fetch('http://localhost:5000/get_latest_uid');
            const data = await response.json();
            if (data && data.uid && data.uid !== lastUid) {
                console.log(`💳 UID DITERIMA DARI JEMBATAN HTTP: ${data.uid}`);
                lastUid = data.uid;
                isPolling = false;
                handleRfidTap(data.uid);
            }
        } catch (error) {
            console.error("Gagal terhubung ke jembatan HTTP. Pastikan bridge_http.py berjalan.");
            updateStatus("Gagal terhubung ke alat pembaca.", "error");
            isPolling = false;
        }
    }

    setInterval(pollForUid, 2000);

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
            updateStatus('Gagal mengakses kamera!', 'error');
            captureBtn.disabled = true;
        }
    }
    
    captureBtn.addEventListener('click', async () => {
        captureBtn.disabled = true;
        updateStatus('Memproses absensi...', 'loading');
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
        isPolling = true; 
        lastUid = null;
    }
});