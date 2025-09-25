document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname !== '/home') {
        return;
    }

    const recordButton = document.getElementById('recordButton');
    const statusText = document.getElementById('statusText');
    const resultsDiv = document.getElementById('results');
    const websiteLink = document.getElementById('websiteLink');
    const transcriptionContainer = document.getElementById('transcription-container');
    const transcriptionText = document.getElementById('transcriptionText');

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    let pollingInterval;

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
            mediaRecorder.onstop = sendAudioToServer;
            mediaRecorder.start();
            isRecording = true;
            updateUIForRecording();
        } catch (error) {
            console.error("Error accessing microphone:", error);
            statusText.textContent = "Could not access the microphone. Please grant permission.";
        }
    };

    const stopRecording = () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            isRecording = false;
            updateUIForProcessing();
        }
    };

    const sendAudioToServer = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio_data', audioBlob);

        try {
            const response = await fetch('/process-audio', {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `Server error: ${response.statusText}`);
            }

            if (data.job_id && data.transcript) {
                transcriptionText.textContent = `"${data.transcript}"`;
                transcriptionContainer.classList.remove('d-none');
                pollForStatus(data.job_id);
            } else {
                throw new Error(data.error || "Error starting the build process.");
            }

        } catch (error) {
            console.error("Error sending audio:", error);
            // Display the specific error message to the user
            statusText.textContent = `Error: ${error.message}`;
            resetUI();
        } finally {
            audioChunks = [];
        }
    };

    const pollForStatus = (jobId) => {
        statusText.textContent = "EchoForge is now building your site... This may take a moment.";
        
        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${jobId}`);
                const data = await response.json();

                if (response.ok && data.status === 'completed') {
                    clearInterval(pollingInterval);
                    displayResult(data.website_url);
                } else if (!response.ok || data.status === 'failed') {
                    clearInterval(pollingInterval);
                    statusText.textContent = `Sorry, there was an error building your website: ${data.error || 'Unknown error'}`;
                    resetUI();
                }
            } catch (error) {
                console.error("Polling error:", error);
                clearInterval(pollingInterval);
                statusText.textContent = "Error checking status.";
                resetUI();
            }
        }, 3000);
    };

    const updateUIForRecording = () => {
        recordButton.classList.add('recording');
        statusText.textContent = "Listening... Click again when you're done.";
    };
    
    const updateUIForProcessing = () => {
        recordButton.classList.remove('recording');
        recordButton.disabled = true;
        statusText.textContent = "Processing your request...";
    };

    const displayResult = (url) => {
        statusText.textContent = "All done! You can describe another website if you like.";
        websiteLink.href = url;
        resultsDiv.classList.remove('d-none');
        recordButton.disabled = false;
    };
    
    const resetUI = () => {
        recordButton.disabled = false;
        transcriptionContainer.classList.add('d-none');
        resultsDiv.classList.add('d-none');
    };

    recordButton.addEventListener('click', () => {
        if (isRecording) {
            stopRecording();
        } else {
            transcriptionContainer.classList.add('d-none');
            resultsDiv.classList.add('d-none');
            statusText.textContent = "Click the button and start speaking";
            startRecording();
        }
    });
});
