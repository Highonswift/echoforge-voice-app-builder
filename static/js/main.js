// static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const recordButton = document.getElementById('recordButton');
    const statusText = document.getElementById('statusText');
    const resultsDiv = document.getElementById('results');
    const websiteLink = document.getElementById('websiteLink');

    // *** NEW ELEMENT SELECTORS ***
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

            mediaRecorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };

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

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            // *** MODIFICATION HERE ***
            // Destructure both job_id and transcript from the response
            const data = await response.json();

            if (data.job_id && data.transcript) {
                // 1. Display the transcript first
                transcriptionText.textContent = `"${data.transcript}"`;
                transcriptionContainer.classList.remove('d-none');

                // 2. Start polling for the result
                pollForStatus(data.job_id);
            } else {
                statusText.textContent = "Error starting the build process.";
                resetUI();
            }

        } catch (error) {
            console.error("Error sending audio:", error);
            statusText.textContent = "Failed to send audio to the server.";
            resetUI();
        } finally {
            audioChunks = []; // Clear chunks for the next recording
        }
    };

    const pollForStatus = (jobId) => {
        // Update status text after showing the transcript
        statusText.textContent = "EchoForge is now building your site... This may take a moment.";
        
        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${jobId}`);
                const data = await response.json();

                if (data.status === 'completed') {
                    clearInterval(pollingInterval);
                    displayResult(data.website_url);
                } else if (data.status === 'failed') {
                    clearInterval(pollingInterval);
                    statusText.textContent = "Sorry, there was an error building your website.";
                    resetUI();
                }
                // If status is 'processing', the loop continues
            } catch (error) {
                console.error("Polling error:", error);
                clearInterval(pollingInterval);
                statusText.textContent = "Error checking status.";
                resetUI();
            }
        }, 3000); // Poll every 3 seconds
    };

    const updateUIForRecording = () => {
        recordButton.classList.add('recording');
        statusText.textContent = "Listening... Click again when you're done.";
    };
    
    const updateUIForProcessing = () => {
        recordButton.classList.remove('recording');
        recordButton.disabled = true; // Disable button while processing
        statusText.textContent = "Processing your request...";
    };


    const displayResult = (url) => {
        statusText.textContent = "All done! You can describe another website if you like.";
        websiteLink.href = url;
        resultsDiv.classList.remove('d-none'); // Show the results div
        recordButton.disabled = false; // Re-enable for another go
    };
    
    // *** NEW HELPER FUNCTION ***
    const resetUI = () => {
        recordButton.disabled = false;
        transcriptionContainer.classList.add('d-none');
        resultsDiv.classList.add('d-none');
    };

    recordButton.addEventListener('click', () => {
        if (isRecording) {
            stopRecording();
        } else {
            // Reset UI for a new recording session
            transcriptionContainer.classList.add('d-none');
            resultsDiv.classList.add('d-none');
            startRecording();
        }
    });
});