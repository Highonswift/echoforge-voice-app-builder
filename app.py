import os
import uuid
import time
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

jobs_db = {}

DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
TENWEB_API_KEY = os.getenv('TENWEB_API_KEY')

def transcribe_audio_with_deepgram(audio_file_path):
    if not DEEPGRAM_API_KEY:
        print("ERROR: DEEPGRAM_API_KEY not found.")
        return None
    try:
        with open(audio_file_path, 'rb') as audio:
            headers = {'Authorization': f'Token {DEEPGRAM_API_KEY}', 'Content-Type': 'audio/webm'}
            url = 'https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true'
            response = requests.post(url, headers=headers, data=audio)
            response.raise_for_status()
            result = response.json()
            transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
            print(f"Successfully transcribed audio: '{transcript}'")
            # Clean up the uploaded file after transcription
            os.remove(audio_file_path)
            return transcript
    except Exception as e:
        print(f"An error during transcription: {e}")
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)
        return None

def create_blank_website(prompt):
    """
    Creates a new blank website on 10web and returns its ID and URL.
    """
    api_url = "https://api.10web.io/v1/hosting/website"
    headers = {
        'x-api-key': TENWEB_API_KEY,
        'Content-Type': 'application/json'
    }
    subdomain = f"echoforge-{str(uuid.uuid4())[:8]}"
    admin_password = f"AdminPass!{str(uuid.uuid4())[:6]}"
    body = {
        "subdomain": subdomain,
        "region": "us-central1-a",
        "site_title": prompt[:60],
        "admin_username": "admin",
        "admin_password": admin_password
    }
    try:
        print(f"Sending request to 10web to create blank website with title: '{body['site_title']}'")
        response = requests.post(api_url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json().get('data', {})
        website_id = data.get('website_id')
        site_url = data.get('site_url')
        if website_id and site_url:
            print(f"Successfully created blank website. ID: {website_id}, URL: {site_url}")
            return {'website_id': website_id, 'site_url': site_url}
        else:
            print(f"Error: 10web response did not contain website_id or site_url. Response: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling 10web create API: {e}")
        if e.response is not None:
            print(f"10web error response: {e.response.text}")
        return None

def start_ai_generation(website_id, prompt):
    """
    Starts the AI website generation process on a given website (fire-and-forget).
    """
    api_url = "https://api.10web.io/v1/ai/generate_site"
    headers = {
        'x-api-key': TENWEB_API_KEY,
        'Content-Type': 'application/json'
    }
    body = {
        "website_id": website_id,
        "business_type": "Other",
        "business_name": prompt[:60],
        "business_description": prompt
    }
    try:
        print(f"Sending request to start AI generation for website {website_id}.")
        response = requests.post(api_url, headers=headers, json=body)
        response.raise_for_status()
        print("Successfully triggered AI generation.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI generation API: {e}")
        if e.response is not None:
            print(f"10web error response: {e.response.text}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process-audio', methods=['POST'])
def process_audio():
    if 'audio_data' not in request.files: return jsonify({'error': 'No audio file'}), 400
    audio_file = request.files['audio_data']
    filename = f"{uuid.uuid4()}.webm"
    audio_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    audio_file.save(audio_file_path)

    transcript = transcribe_audio_with_deepgram(audio_file_path)
    if not transcript: return jsonify({'error': 'Failed to transcribe audio.'}), 500

    site_info = create_blank_website(transcript)
    if not site_info: return jsonify({'error': 'Failed to create blank website.'}), 500
    
    website_id = site_info['website_id']
    site_url = site_info['site_url']

    success = start_ai_generation(website_id, transcript)
    if not success: return jsonify({'error': 'Failed to start AI generation.'}), 500

    job_id = str(uuid.uuid4())
    jobs_db[job_id] = {
        'id': job_id,
        'transcript': transcript,
        'status': 'completed',
        'website_url': site_url,
        'created_at': time.time()
    }
    
    return jsonify({'job_id': job_id, 'transcript': transcript})

@app.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    job = jobs_db.get(job_id)
    if job is None: return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

if __name__ == '__main__':
    app.run(debug=True)
