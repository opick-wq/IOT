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

    let currentRfid = null;
    let stream = null;

    // --- SIMULASI TAP KARTU RFID ---
    // Di dunia nyata, ini akan didorong oleh ESP8266 melalui WebSocket atau polling.
    // Untuk demo, kita gunakan input dari keyboard.
    let rfidInput = '';
    document.addEventListener('keydown', (e) => {
        if (e.key === "Enter") {
            if (rfidInput) {
                console.log(`RFID Diterima: ${rfidInput}`);
                handleRfidTap(rfidInput);
                rfidInput = '';
            }
        } else {
            rfidInput += e.key;
        }
    });

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
            resetUI();
        }
    }

    async function displayVerificationUI(employee) {
        mainContent.classList.add('hidden');
        verificationContent.classList.remove('hidden');
        
        storedPhoto.src = employee.image_url;
        employeeName.textContent = employee.name;
        employeeStatus.textContent = employee.status;
        
        updateStatus('Nyalakan kamera dan ambil foto.', 'info');
        await startWebcam();
    }

    async function startWebcam() {
        try {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            webcamElement.srcObject = stream;
            captureBtn.disabled = false;
        } catch (error) {
            console.error("Error accessing webcam:", error);
            updateStatus('Gagal mengakses kamera!', 'error');
            captureBtn.disabled = true;
        }
    }
    
    captureBtn.addEventListener('click', async () => {
        captureBtn.disabled = true;
        updateStatus('Memproses verifikasi...', 'loading');

        canvasElement.width = webcamElement.videoWidth;
        canvasElement.height = webcamElement.videoHeight;
        const context = canvasElement.getContext('2d');
        // Flip the image horizontally
        context.translate(canvasElement.width, 0);
        context.scale(-1, 1);
        context.drawImage(webcamElement, 0, 0, canvasElement.width, canvasElement.height);

        canvasElement.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append('rfid', currentRfid);
            formData.append('live_image', blob, 'capture.jpg');
            
            try {
                const response = await fetch('/api/verify-and-record', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.error || 'Verifikasi gagal');
                }

                updateStatus(result.message, 'success');
                setTimeout(resetUI, 5000);

            } catch (error) {
                updateStatus(error.message, 'error');
                setTimeout(resetUI, 5000);
            }

        }, 'image/jpeg');
    });

    function updateStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className = type;
    }

    function resetUI() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        mainContent.classList.remove('hidden');
        verificationContent.classList.add('hidden');
        currentRfid = null;
        updateStatus('', '');
    }

});