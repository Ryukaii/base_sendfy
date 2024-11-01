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

def format_phone_number(phone):
    try:
        logger.debug(f"Formatting phone number: {phone}")
        numbers = re.sub(r'\D', '', phone)
        logger.debug(f"After removing non-numeric characters: {numbers}")
        
        if len(numbers) < 10 or len(numbers) > 13:
            raise ValueError(f"Invalid phone number length: {len(numbers)} digits")
        
        if not numbers.startswith('55'):
            numbers = '55' + numbers
            logger.debug(f"Added country code: {numbers}")
        
        if len(numbers) < 12:
            raise ValueError(f"Missing area code (DDD): {numbers}")
        
        if not numbers.startswith('+'):
            numbers = '+' + numbers
            
        logger.debug(f"Final formatted number: {numbers}")
        return numbers
    except Exception as e:
        logger.error(f"Error formatting phone number {phone}: {str(e)}")
        raise ValueError(f"Invalid phone number format: {str(e)}")

def normalize_status(status):
    if not status:
        return None
    try:
        logger.debug(f"Normalizing status: {status}")
        status = str(status).lower().strip()
        status_map = {
            'pending': 'pending',
            'pendente': 'pending',
            'venda pendente': 'pending',
            'aguardando': 'pending',
            'aguardando pagamento': 'pending',
            'waiting': 'pending',
            'waiting_payment': 'pending',
            'approved': 'approved',
            'aprovado': 'approved',
            'venda aprovada': 'approved',
            'completed': 'approved',
            'concluido': 'approved',
            'pago': 'approved',
            'paid': 'approved',
            'payment_confirmed': 'approved',
            'pagamento_confirmado': 'approved',
            'abandoned_cart': 'abandoned',
            'carrinho_abandonado': 'abandoned',
            'canceled': 'canceled',
            'cancelado': 'canceled',
            'refused': 'canceled',
            'recusado': 'canceled'
        }
        normalized = status_map.get(status)
        logger.debug(f"Normalized status: {status} -> {normalized}")
        return normalized
    except Exception as e:
        logger.error(f"Error normalizing status {status}: {str(e)}")
        return None

def format_price(price_str):
    try:
        if isinstance(price_str, (int, float)):
            return "{:.2f}".format(float(price_str))
        
        price = re.sub(r'[^\d,.]', '', str(price_str))
        
        if ',' in price and '.' not in price:
            price = price.replace(',', '.')
        elif ',' in price and '.' in price:
            price = price.replace('.', '').replace(',', '.')
        
        value = float(price)
        if value < 0:
            raise ValueError("Price cannot be negative")
            
        return "{:.2f}".format(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Error formatting price {price_str}: {str(e)}")
        return "0.00"

def format_message(template, **kwargs):
    try:
        logger.debug(f"Formatting message template: {template}")
        logger.debug(f"Template variables: {kwargs}")
        
        template = re.sub(r'\{(\w+)\.(\w+)\}', r'{\1_\2}', template)
        logger.debug(f"Template after dot notation replacement: {template}")
        
        for key, value in kwargs.items():
            if isinstance(value, (int, float)) or (isinstance(value, str) and re.match(r'^[\d,.]+$', value)):
                try:
                    kwargs[key] = format_price(value)
                    logger.debug(f"Formatted {key}: {value} -> {kwargs[key]}")
                except (ValueError, TypeError):
                    pass
        
        result = template.format(**kwargs)
        logger.debug(f"Final formatted message: {result}")
        return result
    except KeyError as e:
        logger.error(f"Missing template variable: {str(e)}")
        return template
    except Exception as e:
        logger.error(f"Error formatting template: {str(e)}")
        return template

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
        
        logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")
        
        status = webhook_data.get('status')
        transaction_id = webhook_data.get('transaction_id')
        logger.debug(f"Extracted status: {status}, transaction_id: {transaction_id}")
        
        if not all([status, transaction_id]):
            logger.error("Missing required fields")
            return jsonify({
                'success': False,
                'message': 'Missing required fields: status or transaction_id'
            }), 400
        
        normalized_status = normalize_status(status)
        if normalized_status is None:
            logger.error(f"Invalid status value: {status}")
            return jsonify({
                'success': False,
                'message': f'Invalid status value: {status}'
            }), 400
        
        customer = webhook_data.get('customer', {})
        logger.debug(f"Customer data: {customer}")
        
        if not customer or not customer.get('phone'):
            logger.error("Missing customer data or phone")
            return jsonify({
                'success': False,
                'message': 'Missing customer data or phone'
            }), 400
        
        try:
            formatted_phone = format_phone_number(customer['phone'])
            logger.debug(f"Formatted phone: {formatted_phone}")
        except ValueError as e:
            logger.error(f"Invalid phone number: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Invalid phone number: {str(e)}'
            }), 400
        
        full_name = customer.get('name', '')
        name_parts = full_name.split()
        first_name = name_parts[0] if name_parts else ''
        logger.debug(f"Extracted customer name - full: {full_name}, first: {first_name}")
        
        total_price = "0.00"
        if webhook_data.get('total_price'):
            total_price = format_price(webhook_data['total_price'])
        elif webhook_data.get('plans') and webhook_data['plans'][0].get('value'):
            total_price = format_price(webhook_data['plans'][0]['value'])
        logger.debug(f"Formatted total price: {total_price}")
        
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        
        logger.debug(f"Looking for campaigns with integration_id={integration_id} and status={normalized_status}")
        matching_campaigns = [
            c for c in campaigns 
            if c['integration_id'] == integration_id 
            and normalize_status(c['event_type']) == normalized_status
        ]
        logger.debug(f"Found {len(matching_campaigns)} matching campaigns")
        
        if not matching_campaigns:
            logger.info(f"No matching campaigns found for integration {integration_id} and status {normalized_status}")
            return jsonify({
                'success': True,
                'message': 'No matching campaigns found'
            })
        
        tasks = []
        processed_campaigns = 0
        for campaign in matching_campaigns:
            try:
                logger.debug(f"Processing campaign: {campaign['name']} (ID: {campaign['id']})")
                
                template_vars = {
                    'customer_name': first_name,
                    'customer_full_name': full_name,
                    'customer_phone': formatted_phone,
                    'customer_email': customer.get('email', ''),
                    'total_price': total_price,
                    'transaction_id': transaction_id,
                    'pix_code': webhook_data.get('pix_code', ''),
                    'store_name': webhook_data.get('store_name', ''),
                    'order_url': webhook_data.get('order_url', ''),
                    'checkout_url': webhook_data.get('checkout_url', '')
                }
                
                message = format_message(campaign['message_template'], **template_vars)
                logger.debug(f"Generated message: {message}")
                
                task = send_sms_task.delay(
                    phone=formatted_phone,
                    message=message,
                    operator="claro",
                    campaign_id=campaign['id'],
                    event_type=normalized_status
                )
                
                tasks.append(task.id)
                processed_campaigns += 1
                logger.info(f"Queued SMS task {task.id} for campaign {campaign['id']}")
                
            except Exception as e:
                logger.error(f"Error processing campaign {campaign['id']}: {str(e)}")
                continue
        
        return jsonify({
            'success': True,
            'message': f'Successfully processed {processed_campaigns} campaigns',
            'tasks': tasks
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook data: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Invalid JSON data'
        }), 400
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/sms')
def sms():
    try:
        return render_template('sms.html')
    except Exception as e:
        logger.error(f"Error rendering SMS template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/integrations')
def integrations():
    try:
        return render_template('integrations.html')
    except Exception as e:
        logger.error(f"Error rendering integrations template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/campaigns')
def campaigns():
    try:
        return render_template('campaigns.html')
    except Exception as e:
        logger.error(f"Error rendering campaigns template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/campaign-performance')
def campaign_performance():
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
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/sms-history')
def sms_history():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        return render_template('sms_history.html', sms_history=history)
    except Exception as e:
        logger.error(f"Error loading SMS history: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/analytics')
def analytics():
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
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    try:
        data = request.get_json()
        phone = data.get('phone')
        message = data.get('message')
        operator = data.get('operator')
        
        if not all([phone, message, operator]):
            return jsonify({
                'success': False,
                'message': 'Missing required fields'
            }), 400
        
        phone = format_phone_number(phone)
        task = send_sms_task.delay(
            phone=phone,
            message=message,
            operator=operator,
            campaign_id=None,
            event_type='manual'
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS queued successfully',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/integrations', methods=['GET', 'POST'])
def manage_integrations():
    try:
        if request.method == 'GET':
            with open(INTEGRATIONS_FILE, 'r') as f:
                return jsonify(json.load(f))
        
        if request.method == 'POST':
            data = request.get_json()
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
    except Exception as e:
        logger.error(f"Error managing integrations: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns', methods=['GET', 'POST'])
def manage_campaigns():
    try:
        if request.method == 'GET':
            with open(CAMPAIGNS_FILE, 'r') as f:
                return jsonify(json.load(f))
        
        if request.method == 'POST':
            data = request.get_json()
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
            
            return jsonify(campaign)
    except Exception as e:
        logger.error(f"Error managing campaigns: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)