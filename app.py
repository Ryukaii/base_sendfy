import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify
from celery_worker import send_sms_task
from collections import Counter

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        logger.info(f"Initialized JSON file: {filepath}")

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

def normalize_status(status):
    if not status:
        return None
    status = str(status).lower().strip()
    status_map = {
        'pending': 'pending',
        'pend': 'pending',
        'pendente': 'pending',
        'venda pendente': 'pending',
        'approved': 'approved',
        'aprovado': 'approved',
        'approve': 'approved',
        'venda aprovada': 'approved'
    }
    return status_map.get(status, status)

@app.route('/')
def index():
    logger.info("Accessing index page")
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index template: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/analytics')
def analytics():
    logger.info("Accessing analytics page")
    try:
        # Load SMS history
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        
        # Calculate metrics
        total_messages = len(history)
        success_messages = sum(1 for msg in history if msg['status'] == 'success')
        success_rate = round((success_messages / total_messages * 100) if total_messages > 0 else 0, 1)
        
        # Count messages by type
        manual_messages = sum(1 for msg in history if msg['event_type'] == 'manual')
        campaign_messages = sum(1 for msg in history if msg['event_type'] != 'manual')
        
        # Messages by status
        status_counts = Counter(msg['status'] for msg in history)
        messages_by_status = [
            {
                'status': status,
                'count': count,
                'percentage': round(count / total_messages * 100, 1)
            }
            for status, count in status_counts.items()
        ]
        
        # Messages by event type
        event_counts = Counter(msg['event_type'] for msg in history)
        messages_by_event = [
            {
                'type': event_type,
                'count': count,
                'percentage': round(count / total_messages * 100, 1)
            }
            for event_type, count in event_counts.items()
        ]
        
        # Recent activity (last 10 messages)
        recent_activity = sorted(history, key=lambda x: x['timestamp'], reverse=True)[:10]
        
        return render_template('analytics.html',
                             total_messages=total_messages,
                             success_rate=success_rate,
                             manual_messages=manual_messages,
                             campaign_messages=campaign_messages,
                             messages_by_status=messages_by_status,
                             messages_by_event=messages_by_event,
                             recent_activity=recent_activity)
    except Exception as e:
        logger.error(f"Error generating analytics: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/sms')
def sms():
    logger.info("Accessing SMS page")
    try:
        return render_template('sms.html')
    except Exception as e:
        logger.error(f"Error rendering SMS template: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/integrations')
def integrations():
    logger.info("Accessing integrations page")
    try:
        return render_template('integrations.html')
    except Exception as e:
        logger.error(f"Error rendering integrations template: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/campaigns')
def campaigns():
    logger.info("Accessing campaigns page")
    try:
        return render_template('campaigns.html')
    except Exception as e:
        logger.error(f"Error rendering campaigns template: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/sms-history')
def sms_history():
    logger.info("Accessing SMS history page")
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        return render_template('sms_history.html', sms_history=history)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading SMS history data: {str(e)}")
        history = []
        return render_template('sms_history.html', sms_history=history)
    except Exception as e:
        logger.error(f"Error rendering SMS history template: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    logger.info("Received SMS send request")
    data = request.json
    phone = data.get('phone')
    message = data.get('message')
    operator = data.get('operator')
    
    if not all([phone, message, operator]):
        logger.warning("Missing required fields in SMS request")
        return jsonify({
            'success': False, 
            'message': 'Missing required fields: phone, message, or operator'
        }), 400
    
    try:
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
        
        logger.info(f"SMS queued successfully with task ID: {task.id}")
        return jsonify({
            'success': True,
            'message': 'SMS queued for sending',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Error queuing SMS: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error queuing SMS: {str(e)}'
        }), 500

@app.route('/api/integrations', methods=['GET', 'POST'])
def manage_integrations():
    logger.info(f"Managing integrations - Method: {request.method}")
    if request.method == 'GET':
        try:
            with open(INTEGRATIONS_FILE, 'r') as f:
                return jsonify(json.load(f))
        except Exception as e:
            logger.error(f"Error loading integrations: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500
    
    if request.method == 'POST':
        try:
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
            
            logger.info(f"Created new integration: {integration['id']}")
            return jsonify(integration)
        except Exception as e:
            logger.error(f"Error creating integration: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/campaigns', methods=['GET', 'POST'])
def manage_campaigns():
    logger.info(f"Managing campaigns - Method: {request.method}")
    if request.method == 'GET':
        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                return jsonify(json.load(f))
        except Exception as e:
            logger.error(f"Error loading campaigns: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500
    
    if request.method == 'POST':
        try:
            data = request.json
            campaign = {
                'id': str(uuid.uuid4()),
                'name': data['name'],
                'integration_id': data['integration_id'],
                'event_type': normalize_status(data['event_type']),
                'message_template': data['message_template'],
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(CAMPAIGNS_FILE, 'r+') as f:
                campaigns = json.load(f)
                campaigns.append(campaign)
                f.seek(0)
                json.dump(campaigns, f, indent=2)
                f.truncate()
            
            logger.info(f"Created new campaign: {campaign['id']}")
            return jsonify(campaign)
        except Exception as e:
            logger.error(f"Error creating campaign: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500

@app.route('/webhook/<integration_id>', methods=['POST'])
def webhook_handler(integration_id):
    logger.info(f"Received webhook for integration: {integration_id}")
    logger.debug(f"Integration ID: {integration_id}")
    
    try:
        webhook_data = request.json
        logger.debug(f"Raw webhook data structure: {json.dumps(webhook_data, indent=2)}")
        
        # Extract and normalize required fields from webhook data
        status = webhook_data.get('status')
        normalized_status = normalize_status(status)
        customer = webhook_data.get('customer', {})
        total_price = webhook_data.get('total_price')
        
        # Log extracted data
        logger.debug(f"Event type from webhook: {status}")
        logger.debug(f"Normalized event type: {normalized_status}")
        logger.debug(f"Extracted customer data: {json.dumps(customer, indent=2)}")
        logger.debug(f"Total price: {total_price}")
        
        if not normalized_status or not customer or not total_price:
            logger.warning(f"Missing required fields in webhook data: status={normalized_status}, customer={bool(customer)}, total_price={total_price}")
            return jsonify({
                'success': False,
                'message': 'Missing required fields in webhook data'
            }), 400
        
        # Load campaigns
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        
        # Log all campaigns
        logger.debug(f"Found campaigns for integration {integration_id}: {json.dumps(campaigns, indent=2)}")
        
        # Find matching campaigns
        matching_campaigns = [c for c in campaigns 
                          if c['integration_id'] == integration_id 
                          and normalize_status(c['event_type']) == normalized_status]
        
        logger.info(f"Found {len(matching_campaigns)} matching campaigns")
        logger.debug(f"Matching campaigns: {json.dumps(matching_campaigns, indent=2)}")
        
        tasks = []
        for campaign in matching_campaigns:
            try:
                phone = format_phone_number(customer['phone'])
                message = campaign['message_template'].format(
                    customer=customer,
                    total_price=total_price
                )
                
                logger.debug(f"Preparing to queue SMS for campaign {campaign['id']}")
                logger.debug(f"Formatted phone: {phone}")
                logger.debug(f"Formatted message: {message}")
                
                task = send_sms_task.delay(
                    phone=phone,
                    message=message,
                    operator="claro",
                    campaign_id=campaign['id'],
                    event_type=normalized_status
                )
                
                tasks.append(task.id)
                logger.info(f"Queued SMS for campaign {campaign['id']}, task ID: {task.id}")
                
            except KeyError as e:
                logger.error(f"Error formatting message for campaign {campaign['id']}: Missing key {str(e)}")
            except Exception as e:
                logger.error(f"Error queuing SMS for campaign {campaign['id']}: {str(e)}")
        
        return jsonify({
            'success': True,
            'tasks': tasks
        })
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Add startup logging
logger.info("Flask application initialized")
