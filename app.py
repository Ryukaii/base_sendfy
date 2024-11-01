import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify, url_for
from celery_worker import send_sms_task
from collections import Counter

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
SMS_HISTORY_FILE = 'data/sms_history.json'

os.makedirs('data', exist_ok=True)

def initialize_json_file(filepath, initial_data=None):
    try:
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump(initial_data if initial_data is not None else [], f)
            logger.info(f"Initialized JSON file: {filepath}")
    except Exception as e:
        logger.error(f"Error initializing JSON file {filepath}: {str(e)}")
        raise

for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE]:
    initialize_json_file(file_path)

def get_webhook_url(integration_id):
    """Generate full webhook URL including domain"""
    return f"{request.host_url.rstrip('/')}/webhook/{integration_id}"

# Your existing format_phone_number, normalize_status, format_price, format_message functions here...

@app.route('/')
def index():
    logger.info("Accessing index page")
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/webhook/<integration_id>', methods=['POST'])
def webhook_handler(integration_id):
    logger.info(f"Received webhook request for integration: {integration_id}")
    
    if not integration_id:
        logger.error("Invalid integration_id: empty or missing")
        return jsonify({'success': False, 'message': 'Invalid integration ID'}), 400
    
    try:
        webhook_data = request.get_json()
        if not webhook_data:
            raise ValueError("Empty webhook data")
            
        # Rest of your webhook_handler code...

@app.route('/api/integrations', methods=['GET', 'POST'])
def api_integrations():
    try:
        if request.method == 'GET':
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
            return jsonify(integrations)
            
        elif request.method == 'POST':
            data = request.get_json()
            if not data or not data.get('name'):
                return jsonify({'error': 'Integration name is required'}), 400
                
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
            
            integration_id = str(uuid.uuid4())
            new_integration = {
                'id': integration_id,
                'name': data['name'],
                'webhook_url': f'/webhook/{integration_id}',
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            integrations.append(new_integration)
            
            with open(INTEGRATIONS_FILE, 'w') as f:
                json.dump(integrations, f, indent=2)
            
            return jsonify({'success': True, 'integration': new_integration})
            
    except Exception as e:
        logger.error(f"Error in integrations API: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Rest of your existing routes...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
