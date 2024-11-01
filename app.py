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

@app.route('/api/integrations', methods=['GET'])
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
        return jsonify(integrations)
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/integrations', methods=['POST'])
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400

        integration_id = str(uuid.uuid4())
        integration = {
            'id': integration_id,
            'name': data['name'],
            'webhook_url': f'/webhook/{integration_id}',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            integrations = []

        integrations.append(integration)

        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)

        return jsonify(integration), 201
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
def delete_integration(integration_id):
    try:
        logger.info(f"Attempting to delete integration: {integration_id}")
        
        # Load integrations
        try:
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
        except Exception as e:
            logger.error(f"Error loading integrations file: {str(e)}")
            return jsonify({'error': 'Failed to load integrations'}), 500

        # Check if integration exists
        if not any(i['id'] == integration_id for i in integrations):
            logger.warning(f"Integration not found: {integration_id}")
            return jsonify({'error': 'Integration not found'}), 404

        # Load campaigns
        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                campaigns = json.load(f)
        except Exception as e:
            logger.error(f"Error loading campaigns file: {str(e)}")
            return jsonify({'error': 'Failed to load campaigns'}), 500

        # Start transaction-like operation
        try:
            # Remove associated campaigns
            updated_campaigns = [c for c in campaigns if c['integration_id'] != integration_id]
            campaigns_removed = len(campaigns) - len(updated_campaigns)
            logger.info(f"Found {campaigns_removed} campaigns to remove")

            # Remove integration
            updated_integrations = [i for i in integrations if i['id'] != integration_id]

            # Write both files - this is our "transaction"
            with open(CAMPAIGNS_FILE, 'w') as f:
                json.dump(updated_campaigns, f, indent=2)
            
            with open(INTEGRATIONS_FILE, 'w') as f:
                json.dump(updated_integrations, f, indent=2)

            logger.info(f"Successfully deleted integration {integration_id} and {campaigns_removed} associated campaigns")
            return jsonify({
                'message': 'Integration deleted successfully',
                'campaigns_removed': campaigns_removed
            })

        except Exception as e:
            logger.error(f"Transaction failed during deletion: {str(e)}")
            return jsonify({
                'error': 'Failed to complete deletion transaction',
                'details': str(e)
            }), 500

    except Exception as e:
        logger.error(f"Unexpected error during integration deletion: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ... [rest of your existing app.py code]
