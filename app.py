import json
import os
import uuid
import datetime
import re
from flask import Flask, render_template, request, jsonify
from celery_worker import send_sms_task

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

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
    
    # Send SMS using Celery task
    task = send_sms_task.delay(
        phone=phone,
        message=message,
        operator=operator,
        campaign_id=None,
        event_type='manual'
    )
    
    return jsonify({
        'success': True,
        'message': 'SMS queued for sending',
        'task_id': task.id
    })

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
    
    tasks = []
    for campaign in matching_campaigns:
        try:
            # Format phone number
            phone = format_phone_number(customer['phone'])
            
            # Format message using webhook data
            message = campaign['message_template'].format(
                customer=customer,
                total_price=total_price
            )
            
            print(f"Queuing SMS for campaign {campaign['id']} to {phone}")
            
            # Queue SMS task
            task = send_sms_task.delay(
                phone=phone,
                message=message,
                operator="claro",  # Default operator
                campaign_id=campaign['id'],
                event_type=status
            )
            
            tasks.append(task.id)
            
        except KeyError as e:
            error_msg = f"Error formatting message for campaign {campaign['id']}: Missing key {str(e)}"
            print(error_msg)
        except Exception as e:
            error_msg = f"Error queuing SMS for campaign {campaign['id']}: {str(e)}"
            print(error_msg)
    
    return jsonify({
        'success': True,
        'tasks': tasks
    })
