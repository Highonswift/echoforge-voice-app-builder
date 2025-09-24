# app.py
import os
import uuid
import time
import sqlite3
import threading
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Configuration ---
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DATABASE'] = 'database.db'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- API Keys ---
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
TENWEB_API_KEY = os.getenv('TENWEB_API_KEY')

# --- SQLite Database Functions ---
def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, transcript TEXT, status TEXT NOT NULL,
            tenweb_task_id TEXT, website_url TEXT, created_at REAL NOT NULL
        )
    """)
    # In case the DB was created with an old schema, try to add the column.
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN tenweb_task_id TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise

    conn.commit()
    conn.close()
    print("SQLite database initialized.")

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

# --- REAL DEEPGRAM API FUNCTION ---
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
            return transcript
    except Exception as e:
        print(f"An error during transcription: {e}")
        return None

# --- 10Web API Functions ---

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

# --- Flask Routes ---

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

    # Step 1: Create a blank website
    site_info = create_blank_website(transcript)
    if not site_info: return jsonify({'error': 'Failed to create blank website.'}), 500
    
    website_id = site_info['website_id']
    site_url = site_info['site_url']

    # Step 2: Start AI generation (fire and forget)
    success = start_ai_generation(website_id, transcript)
    if not success: return jsonify({'error': 'Failed to start AI generation.'}), 500

    # Since we can't poll, we'll assume success and mark as completed.
    job_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO jobs (id, transcript, status, website_url, created_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, transcript, 'completed', site_url, time.time())
    )
    conn.commit()
    conn.close()
    
    return jsonify({'job_id': job_id, 'transcript': transcript})

@app.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    conn = get_db_connection()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if job is None: return jsonify({'error': 'Job not found'}), 404
    job_dict = dict(job)
    return jsonify(job_dict)

# --- Initialize Database on Startup ---
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)