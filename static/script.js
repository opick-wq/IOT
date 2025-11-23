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

    // Update pesan awal
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
        } catch (error) {
            // Silent error agar tidak spam log
        }
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
            // Pastikan UID tersimpan di objek employee jika API tidak mengembalikannya
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
        
        try {
            if (stream) stream.getTracks().forEach(track => track.stop());
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            webcamElement.srcObject = stream;
            captureBtn.disabled = false;
            captureBtn.textContent = "Ambil Foto & Verifikasi";
        } catch (error) {
            updateStatus('Gagal akses kamera.', 'error');
        }
    }
    
    // --- 4. KIRIM FOTO KE SERVER (YANG AKAN TERUSKAN KE API TEMAN) ---
    captureBtn.addEventListener('click', async () => {
        captureBtn.disabled = true;
        captureBtn.textContent = "Memverifikasi...";
        updateStatus('Sedang memverifikasi wajah dengan Server AI...', 'loading');

        canvasElement.width = webcamElement.videoWidth;
        canvasElement.height = webcamElement.videoHeight;
        const ctx = canvasElement.getContext('2d');
        ctx.drawImage(webcamElement, 0, 0);

        canvasElement.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append('rfid', currentEmployee.rfid_uid);
            formData.append('live_image', blob, 'capture.jpg');
            
            try {
                // Kirim ke app.py, nanti app.py yang kirim ke API teman
                const response = await fetch('/api/record-attendance', { 
                    method: 'POST', 
                    body: formData 
                });
                
                const result = await response.json();

                // LOG RESPON UNTUK DEBUGGING
                console.log("========================================");
                console.log("📡 RESPON DARI SERVER:");
                console.log("Status:", response.status);
                console.log("Pesan:", result.message || result.error);
                if (result.details) {
                    console.log("Detail dari API AI:", result.details);
                    // Log jarak jika ada
                    if (result.details.distance !== undefined) {
                        console.log(`📊 Jarak Wajah: ${result.details.distance}`);
                    }
                    if (result.details.similarity !== undefined) {
                        console.log(`📊 Kemiripan: ${result.details.similarity}`);
                    }
                }
                console.log("========================================");


                if (!response.ok) throw new Error(result.error || 'Verifikasi Gagal');

                updateStatus(result.message, 'success');
                setTimeout(resetUI, 4000);

            } catch (error) {
                updateStatus(error.message, 'error');
                setTimeout(resetUI, 4000);
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
    }
});