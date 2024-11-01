import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify
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

# Page Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/integrations')
def integrations_page():
    return render_template('integrations.html')

@app.route('/campaigns')
def campaigns_page():
    return render_template('campaigns.html')

@app.route('/sms')
def sms_page():
    return render_template('sms.html')

@app.route('/sms-history')
def sms_history_page():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            sms_history = json.load(f)
        return render_template('sms_history.html', sms_history=sms_history)
    except Exception as e:
        logger.error(f"Error loading SMS history: {str(e)}")
        return render_template('sms_history.html', sms_history=[])

@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')

@app.route('/campaign-performance')
def campaign_performance_page():
    return render_template('campaign_performance.html')

# API Routes
@app.route('/api/integrations', methods=['GET'])
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
        return jsonify(integrations)
    except FileNotFoundError:
        logger.error("Integrations file not found")
        return jsonify({'error': 'Integrations data not found'}), 404
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in integrations file: {str(e)}")
        return jsonify({'error': 'Invalid integrations data format'}), 500
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/integrations', methods=['POST'])
def create_integration():
    try:
        data = request.get_json()
        if not data:
            logger.error("No JSON data received in request")
            return jsonify({'error': 'No data provided'}), 400
        
        if 'name' not in data:
            logger.error("Integration name missing in request")
            return jsonify({'error': 'Integration name is required'}), 400

        if not data['name'].strip():
            logger.error("Empty integration name provided")
            return jsonify({'error': 'Integration name cannot be empty'}), 400

        integration_id = str(uuid.uuid4())
        integration = {
            'id': integration_id,
            'name': data['name'].strip(),
            'webhook_url': f'/webhook/{integration_id}',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("Integrations file not found or invalid, creating new")
            integrations = []

        # Check for duplicate names
        if any(i['name'].lower() == integration['name'].lower() for i in integrations):
            logger.warning(f"Duplicate integration name: {integration['name']}")
            return jsonify({'error': 'Integration with this name already exists'}), 400

        integrations.append(integration)

        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)

        logger.info(f"Created new integration: {integration_id}")
        return jsonify(integration), 201
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return jsonify({'error': 'Failed to create integration'}), 500

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
def delete_integration(integration_id):
    try:
        # Ensure we always return JSON
        if not integration_id:
            return jsonify({'error': 'Missing integration ID'}), 400
            
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        
        # Find integration
        integration = next((i for i in integrations if i['id'] == integration_id), None)
        if not integration:
            return jsonify({'error': 'Integration not found'}), 404
        
        # Remove integration and associated campaigns
        updated_integrations = [i for i in integrations if i['id'] != integration_id]
        updated_campaigns = [c for c in campaigns if c['integration_id'] != integration_id]
        
        # Write changes
        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(updated_integrations, f, indent=2)
            
        with open(CAMPAIGNS_FILE, 'w') as f:
            json.dump(updated_campaigns, f, indent=2)
        
        return jsonify({'success': True, 'message': 'Integration deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting integration {integration_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
