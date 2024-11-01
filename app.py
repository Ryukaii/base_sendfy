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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
SMS_HISTORY_FILE = 'data/sms_history.json'

os.makedirs('data', exist_ok=True)

def initialize_json_file(filepath, initial_data=None):
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            json.dump(initial_data if initial_data is not None else [], f)
        logger.info(f"Initialized JSON file: {filepath}")

initialize_json_file(INTEGRATIONS_FILE)
initialize_json_file(CAMPAIGNS_FILE)
initialize_json_file(SMS_HISTORY_FILE)

def format_phone_number(phone):
    numbers = re.sub(r'\D', '', phone)
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
        'pendente': 'pending',
        'venda pendente': 'pending',
        'aguardando': 'pending',
        'approved': 'approved',
        'aprovado': 'approved',
        'venda aprovada': 'approved',
        'completed': 'approved',
        'concluido': 'approved',
        'pago': 'approved'
    }
    return status_map.get(status)

@app.route('/')
def index():
    logger.info("Accessing index page")
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index template: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/campaign-performance')
def campaign_performance():
    logger.info("Accessing campaign performance page")
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        with open(SMS_HISTORY_FILE, 'r') as f:
            sms_history = json.load(f)
        
        campaign_metrics = []
        total_messages = 0
        active_campaigns = 0
        
        for campaign in campaigns:
            campaign_messages = [msg for msg in sms_history if msg.get('campaign_id') == campaign['id']]
            messages_count = len(campaign_messages)
            success_count = sum(1 for msg in campaign_messages if msg['status'] == 'success')
            success_rate = round((success_count / messages_count * 100) if messages_count > 0 else 0, 1)
            last_message = max([msg['timestamp'] for msg in campaign_messages]) if campaign_messages else 'No messages'
            
            if campaign_messages:
                latest_msg_time = datetime.datetime.strptime(last_message, "%Y-%m-%d %H:%M:%S")
                if (datetime.datetime.now() - latest_msg_time).days < 1:
                    active_campaigns += 1
            
            total_messages += messages_count
            
            campaign_metrics.append({
                'name': campaign['name'],
                'event_type': campaign['event_type'],
                'messages_sent': messages_count,
                'success_rate': success_rate,
                'last_message': last_message
            })
        
        campaign_messages = [msg for msg in sms_history if msg.get('campaign_id')]
        recent_activity = []
        
        for msg in sorted(campaign_messages, key=lambda x: x['timestamp'], reverse=True)[:10]:
            campaign_name = next((c['name'] for c in campaigns if c['id'] == msg['campaign_id']), 'Unknown')
            recent_activity.append({
                'timestamp': msg['timestamp'],
                'campaign_name': campaign_name,
                'phone': msg['phone'],
                'status': msg['status'],
                'message': msg['message']
            })
        
        return render_template('campaign_performance.html',
                             total_campaigns=len(campaigns),
                             active_campaigns=active_campaigns,
                             total_messages=total_messages,
                             campaigns=campaign_metrics,
                             recent_activity=recent_activity)
    except Exception as e:
        logger.error(f"Error generating campaign performance data: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/analytics')
def analytics():
    logger.info("Accessing analytics page")
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        
        total_messages = len(history)
        success_messages = sum(1 for msg in history if msg['status'] == 'success')
        success_rate = round((success_messages / total_messages * 100) if total_messages > 0 else 0, 1)
        
        manual_messages = sum(1 for msg in history if msg['event_type'] == 'manual')
        campaign_messages = sum(1 for msg in history if msg['event_type'] != 'manual')
        
        status_counts = Counter(msg['status'] for msg in history)
        messages_by_status = [
            {
                'status': status,
                'count': count,
                'percentage': round(count / total_messages * 100, 1)
            }
            for status, count in status_counts.items()
        ]
        
        event_counts = Counter(msg['event_type'] for msg in history)
        messages_by_event = [
            {
                'type': event_type,
                'count': count,
                'percentage': round(count / total_messages * 100, 1)
            }
            for event_type, count in event_counts.items()
        ]
        
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
        phone = format_phone_number(phone)
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
    logger.info(f"Received webhook request for integration: {integration_id}")
    logger.debug(f"Request method: {request.method}")
    logger.debug("Request headers:")
    for header, value in request.headers.items():
        logger.debug(f"{header}: {value}")
    
    if not integration_id:
        logger.error("Invalid integration_id: empty or missing")
        return jsonify({
            'success': False,
            'message': 'Invalid integration ID'
        }), 400
    
    logger.debug(f"Integration ID: {integration_id}")
    
    try:
        webhook_data = request.get_data()
        logger.debug(f"Raw webhook data: {webhook_data.decode('utf-8')}")
        webhook_data = request.get_json()
        logger.debug(f"Parsed webhook data: {json.dumps(webhook_data, indent=2)}")
    except Exception as e:
        logger.error(f"Error parsing webhook JSON: {str(e)}")
        return jsonify({'error': 'Invalid JSON'}), 400
    
    try:
        status = webhook_data.get('status')
        logger.debug(f"Original status: {status}")
        
        if not status:
            logger.error("Missing status in webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing status in webhook data'
            }), 400
            
        normalized_status = normalize_status(status)
        logger.debug(f"Normalized status: {normalized_status}")
        
        if not normalized_status:
            logger.error(f"Invalid status value: {status}")
            return jsonify({
                'success': False,
                'message': f'Invalid status value: {status}'
            }), 400
        
        customer = webhook_data.get('customer', {})
        logger.debug(f"Customer data: {json.dumps(customer, indent=2)}")
        
        if not customer:
            logger.error("Missing customer data in webhook")
            return jsonify({
                'success': False,
                'message': 'Missing customer data'
            }), 400
            
        total_price = webhook_data.get('total_price')
        logger.debug(f"Total price: {total_price}")
        
        if not total_price:
            logger.error("Missing total_price in webhook data")
            return jsonify({
                'success': False,
                'message': 'Missing total_price'
            }), 400
        
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        
        logger.debug(f"Searching for campaigns with integration_id={integration_id} and status={normalized_status}")
        logger.debug(f"All available campaigns: {json.dumps(campaigns, indent=2)}")
        
        matching_campaigns = [c for c in campaigns 
                          if c['integration_id'] == integration_id 
                          and normalize_status(c['event_type']) == normalized_status]
        
        if not matching_campaigns:
            logger.info(f"No matching campaigns found for integration {integration_id} and status {normalized_status}")
            return jsonify({
                'success': True,
                'message': 'No matching campaigns found'
            })
        
        logger.info(f"Found {len(matching_campaigns)} matching campaigns")
        
        tasks = []
        for campaign in matching_campaigns:
            try:
                phone = format_phone_number(customer['phone'])
                message = campaign['message_template'].format(
                    customer=customer,
                    total_price=total_price
                )
                
                logger.debug("Template variables:")
                logger.debug(f"- customer: {json.dumps(customer, indent=2)}")
                logger.debug(f"- total_price: {total_price}")
                logger.debug(f"Final message after template: {message}")
                
                task = send_sms_task.delay(
                    phone=phone,
                    message=message,
                    operator="claro",
                    campaign_id=campaign['id'],
                    event_type=normalized_status
                )
                
                tasks.append(task.id)
                logger.info(f"Successfully queued SMS for campaign {campaign['id']}, task ID: {task.id}")
                
            except KeyError as e:
                logger.error(f"Error formatting message for campaign {campaign['id']}: Missing key {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Error queuing SMS for campaign {campaign['id']}: {str(e)}")
                continue
        
        response_data = {
            'success': True,
            'message': f'Processed {len(tasks)} campaigns',
            'task_ids': tasks
        }
        logger.info(f"Webhook processing completed: {json.dumps(response_data)}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

logger.info("Flask application initialized")