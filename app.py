import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-fallback-secret-key-for-local-dev')
UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

jobs_db = {}

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/save-keys', methods=['POST'])
def save_keys():
    session['TENWEB_API_KEY'] = request.form.get('tenweb_api_key')
    return redirect(url_for('home'))

def transcribe_audio_with_deepgram(audio_file_path, api_key):
    if not api_key:
        return None, "Deepgram API key is not configured on the server."
    try:
        with open(audio_file_path, 'rb') as audio:
            headers = {'Authorization': f'Token {api_key}', 'Content-Type': 'audio/webm'}
            url = 'https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true'
            response = requests.post(url, headers=headers, data=audio)
            response.raise_for_status()
            result = response.json()
            transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
            return transcript, None
    except Exception as e:
        print(f"An error during transcription: {e}")
        return None, "Failed to transcribe the audio. Please check the server logs."
    finally:
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)

def create_blank_website(prompt, api_key):
    if not api_key:
        return None, "10Web API key not found in session."
    api_url = "https://api.10web.io/v1/hosting/website"
    headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}
    subdomain = f"echoforge-{str(uuid.uuid4())[:8]}"
    body = {
        "subdomain": subdomain,
        "region": "us-central1-a",
        "site_title": prompt[:60],
        "admin_username": "admin",
        "admin_password": f"AdminPass!{str(uuid.uuid4())[:6]}"
    }
    try:
        response = requests.post(api_url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json().get('data', {})
        website_id = data.get('website_id')
        site_url = data.get('site_url')
        if website_id and site_url:
            return {'website_id': website_id, 'site_url': site_url}, None
        else:
            return None, "Could not retrieve website details from 10Web."
    except requests.exceptions.RequestException as e:
        print(f"Error calling 10web create API: {e}")
        return None, "Failed to create the website via 10Web API. Please check your API key and server logs."

def start_ai_generation(website_id, prompt, api_key):
    if not api_key:
        return False, "10Web API key not found in session."
    api_url = "https://api.10web.io/v1/ai/generate_site"
    headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}
    body = {
        "website_id": website_id,
        "business_type": "Other",
        "business_name": prompt[:60],
        "business_description": prompt
    }
    try:
        response = requests.post(api_url, headers=headers, json=body)
        response.raise_for_status()
        return True, None
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI generation API: {e}")
        return False, "Failed to start the AI generation process on 10Web."

@app.route('/home')
def home():
    if 'TENWEB_API_KEY' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/process-audio', methods=['POST'])
def process_audio():
    deepgram_api_key = os.getenv('DEEPGRAM_API_KEY')
    tenweb_api_key = session.get('TENWEB_API_KEY')

    if not tenweb_api_key:
        return jsonify({'error': '10Web API key not found. Please log in again.'}), 401

    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file provided.'}), 400

    audio_file = request.files['audio_data']
    filename = f"{uuid.uuid4()}.webm"
    audio_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    audio_file.save(audio_file_path)

    transcript, error = transcribe_audio_with_deepgram(audio_file_path, deepgram_api_key)
    if error: return jsonify({'error': error}), 500

    site_info, error = create_blank_website(transcript, tenweb_api_key)
    if error: return jsonify({'error': error}), 500
    
    website_id = site_info['website_id']
    site_url = site_info['site_url']

    success, error = start_ai_generation(website_id, transcript, tenweb_api_key)
    if error: return jsonify({'error': error}), 500

    job_id = str(uuid.uuid4())
    jobs_db[job_id] = {
        'id': job_id, 'transcript': transcript, 'status': 'completed',
        'website_url': site_url, 'created_at': time.time()
    }
    
    return jsonify({'job_id': job_id, 'transcript': transcript})

@app.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    job = jobs_db.get(job_id)
    if job is None: return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

if __name__ == '__main__':
    app.run(debug=True)
