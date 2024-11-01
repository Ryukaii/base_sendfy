import json
import os
import uuid
import datetime
from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# File paths
INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Initialize JSON files if they don't exist
if not os.path.exists(INTEGRATIONS_FILE):
    with open(INTEGRATIONS_FILE, 'w') as f:
        json.dump([], f)

if not os.path.exists(CAMPAIGNS_FILE):
    with open(CAMPAIGNS_FILE, 'w') as f:
        json.dump([], f)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sms')
def sms():
    return render_template('sms.html')

@app.route('/integrations')
def integrations():
    return render_template('integrations.html')

@app.route('/campaigns')
def campaigns():
    return render_template('campaigns.html')

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    phone = data.get('phone')
    message = data.get('message')
    operator = data.get('operator')
    
    # Here we would integrate with SMS API
    try:
        # For now, just simulate success
        return jsonify({'success': True, 'message': 'SMS sent successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/integrations', methods=['GET', 'POST'])
def manage_integrations():
    if request.method == 'GET':
        with open(INTEGRATIONS_FILE, 'r') as f:
            return jsonify(json.load(f))
    
    if request.method == 'POST':
        data = request.json
        integration = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'webhook_url': f"/webhook/{str(uuid.uuid4())}",
            'created_at': str(datetime.datetime.now())
        }
        
        with open(INTEGRATIONS_FILE, 'r+') as f:
            integrations = json.load(f)
            integrations.append(integration)
            f.seek(0)
            json.dump(integrations, f)
            f.truncate()
        
        return jsonify(integration)

@app.route('/api/campaigns', methods=['GET', 'POST'])
def manage_campaigns():
    if request.method == 'GET':
        with open(CAMPAIGNS_FILE, 'r') as f:
            return jsonify(json.load(f))
    
    if request.method == 'POST':
        data = request.json
        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
            'created_at': str(datetime.datetime.now())
        }
        
        with open(CAMPAIGNS_FILE, 'r+') as f:
            campaigns = json.load(f)
            campaigns.append(campaign)
            f.seek(0)
            json.dump(campaigns, f)
            f.truncate()
        
        return jsonify(campaign)

@app.route('/webhook/<integration_id>', methods=['POST'])
def webhook_handler(integration_id):
    data = request.json
    
    # Load campaigns
    with open(CAMPAIGNS_FILE, 'r') as f:
        campaigns = json.load(f)
    
    # Find matching campaigns and send SMS
    matching_campaigns = [c for c in campaigns if c['integration_id'] == integration_id 
                        and c['event_type'] == data.get('event_type')]
    
    for campaign in matching_campaigns:
        # Process message template
        message = campaign['message_template'].format(**data)
        
        # Send SMS
        try:
            # For now, just print the message that would be sent
            print(f"Would send SMS: {message} to {data.get('phone')}")
        except Exception as e:
            print(f"Error sending SMS for campaign {campaign['id']}: {str(e)}")
    
    return jsonify({'success': True})
