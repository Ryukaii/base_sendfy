import json
import os
import uuid
import datetime
import re
from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# API Configuration
SMS_API_ENDPOINT = "https://api.apisms.me/v2/send.php"
SMS_API_TOKEN = "df1cacd5-954f251b-6e5dfe0b-df9bfd66-7d98907a"

# File paths
INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
SMS_HISTORY_FILE = 'data/sms_history.json'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Initialize JSON files if they don't exist
def initialize_json_file(filepath, initial_data=None):
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            json.dump(initial_data if initial_data is not None else [], f)

initialize_json_file(INTEGRATIONS_FILE)
initialize_json_file(CAMPAIGNS_FILE)
initialize_json_file(SMS_HISTORY_FILE)

def format_phone_number(phone):
    # Remove all non-numeric characters
    numbers = re.sub(r'\D', '', phone)
    # Ensure it starts with country code
    if not numbers.startswith('55'):
        numbers = '55' + numbers
    if not numbers.startswith('+'):
        numbers = '+' + numbers
    return numbers

def log_sms_attempt(campaign_id, phone, message, status, api_response, event_type):
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []
    
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phone": phone,
        "message": message,
        "status": status,
        "api_response": api_response,
        "campaign_id": campaign_id,
        "event_type": event_type
    }
    
    history.append(entry)
    
    with open(SMS_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

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

@app.route('/sms-history')
def sms_history():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []
    return render_template('sms_history.html', sms_history=history)

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    data = request.json
    phone = data.get('phone')
    message = data.get('message')
    operator = data.get('operator')
    
    if not all([phone, message, operator]):
        return jsonify({
            'success': False, 
            'message': 'Missing required fields: phone, message, or operator'
        }), 400
    
    # Format phone number
    phone = format_phone_number(phone)
    
    # Prepare request payload
    sms_data = {
        "operator": operator,
        "destination_number": phone,
        "message": message,
        "tag": "SMS Platform",
        "user_reply": False
    }
    
    # Prepare headers with token using Bearer authentication
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {SMS_API_TOKEN}'
    }
    
    try:
        # Make request to SMS API
        response = requests.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            headers=headers,
            timeout=10
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        
        # Log the SMS attempt
        log_sms_attempt(
            campaign_id=None,
            phone=phone,
            message=message,
            status='success' if api_response.get('success', False) else 'failed',
            api_response=str(api_response),
            event_type='manual'
        )
        
        if api_response.get('success', False):
            return jsonify({
                'success': True,
                'message': 'SMS sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': api_response.get('message', 'Failed to send SMS')
            }), 400
            
    except requests.exceptions.Timeout:
        log_sms_attempt(None, phone, message, 'failed', 'Request timed out', 'manual')
        return jsonify({
            'success': False,
            'message': 'Request timed out while trying to send SMS'
        }), 504
    except requests.exceptions.RequestException as e:
        log_sms_attempt(None, phone, message, 'failed', str(e), 'manual')
        return jsonify({
            'success': False,
            'message': f'Error sending SMS: {str(e)}'
        }), 500

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
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(INTEGRATIONS_FILE, 'r+') as f:
            integrations = json.load(f)
            integrations.append(integration)
            f.seek(0)
            json.dump(integrations, f, indent=2)
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
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(CAMPAIGNS_FILE, 'r+') as f:
            campaigns = json.load(f)
            campaigns.append(campaign)
            f.seek(0)
            json.dump(campaigns, f, indent=2)
            f.truncate()
        
        return jsonify(campaign)

@app.route('/webhook/<integration_id>', methods=['POST'])
def webhook_handler(integration_id):
    webhook_data = request.json
    print(f"Received webhook data for integration {integration_id}:")
    print(json.dumps(webhook_data, indent=2))
    
    # Extract required fields from webhook data
    status = webhook_data.get('status')
    customer = webhook_data.get('customer', {})
    total_price = webhook_data.get('total_price')
    
    if not status or not customer or not total_price:
        print(f"Missing required fields in webhook data: status={status}, customer={customer}, total_price={total_price}")
        return jsonify({
            'success': False,
            'message': 'Missing required fields in webhook data'
        }), 400
    
    # Load campaigns
    with open(CAMPAIGNS_FILE, 'r') as f:
        campaigns = json.load(f)
    
    # Find matching campaigns for this integration and status
    matching_campaigns = [c for c in campaigns 
                         if c['integration_id'] == integration_id 
                         and c['event_type'] == status]
    
    print(f"Found {len(matching_campaigns)} matching campaigns for status: {status}")
    
    for campaign in matching_campaigns:
        try:
            # Format phone number
            phone = format_phone_number(customer['phone'])
            
            # Format message using webhook data
            message = campaign['message_template'].format(
                customer=customer,
                total_price=total_price
            )
            
            print(f"Sending SMS for campaign {campaign['id']} to {phone}")
            
            # Prepare SMS data
            sms_data = {
                "operator": "claro",  # Default operator
                "destination_number": phone,
                "message": message,
                "tag": "SMS Platform",
                "user_reply": False
            }
            
            # Prepare headers with token using Bearer authentication
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {SMS_API_TOKEN}'
            }
            
            # Send SMS
            response = requests.post(
                SMS_API_ENDPOINT,
                json=sms_data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            # Parse API response
            api_response = response.json()
            print(f"SMS API Response: {json.dumps(api_response, indent=2)}")
            
            # Log the SMS attempt
            log_sms_attempt(
                campaign_id=campaign['id'],
                phone=phone,
                message=message,
                status='success' if api_response.get('success', False) else 'failed',
                api_response=str(api_response),
                event_type=status
            )
            
        except KeyError as e:
            error_msg = f"Error formatting message for campaign {campaign['id']}: Missing key {str(e)}"
            print(error_msg)
            log_sms_attempt(
                campaign_id=campaign['id'],
                phone=phone if 'phone' in locals() else 'unknown',
                message=message if 'message' in locals() else 'unknown',
                status='failed',
                api_response=error_msg,
                event_type=status
            )
        except Exception as e:
            error_msg = f"Error sending SMS for campaign {campaign['id']}: {str(e)}"
            print(error_msg)
            log_sms_attempt(
                campaign_id=campaign['id'],
                phone=phone if 'phone' in locals() else 'unknown',
                message=message if 'message' in locals() else 'unknown',
                status='failed',
                api_response=error_msg,
                event_type=status
            )
    
    return jsonify({'success': True})
