import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
from celery_worker import send_sms_task
from collections import Counter
import redis
from redis.exceptions import RedisError
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug.log')
    ]
)
logger = logging.getLogger(__name__)

REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 0

app = Flask(__name__, 
           template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'),
           static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static'))
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_redis_connection():
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            retry_on_timeout=True,
            health_check_interval=30
        )
        redis_client.ping()
        return redis_client
    except RedisError as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise

INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
SMS_HISTORY_FILE = 'data/sms_history.json'
TRANSACTIONS_FILE = 'data/transactions.json'

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

for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE, TRANSACTIONS_FILE]:
    initialize_json_file(file_path, [] if file_path != TRANSACTIONS_FILE else {})

def format_phone_number(phone):
    try:
        logger.debug(f"Formatting phone number: {phone}")
        numbers = re.sub(r'\D', '', phone)
        logger.debug(f"After removing non-numeric characters: {numbers}")
        
        if len(numbers) < 10 or len(numbers) > 13:
            raise ValueError(f"Invalid phone number length: {len(numbers)} digits")
        
        if not numbers.startswith('55'):
            numbers = '55' + numbers
        
        if len(numbers) < 12:
            raise ValueError(f"Missing area code (DDD): {numbers}")
        
        if not numbers.startswith('+'):
            numbers = '+' + numbers
            
        logger.debug(f"Final formatted number: {numbers}")
        return numbers
    except Exception as e:
        logger.error(f"Error formatting phone number {phone}: {str(e)}")
        raise ValueError(f"Invalid phone number format: {str(e)}")

def format_price(price_str):
    try:
        if isinstance(price_str, (int, float)):
            return "{:.2f}".format(float(price_str))
        
        if not price_str:
            return "0.00"
            
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

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error="Página não encontrada"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error="Erro interno do servidor"), 500

@app.errorhandler(RedisError)
def handle_redis_error(e):
    logger.error(f"Redis error: {str(e)}")
    return render_template('error.html', 
                         error="Erro de conexão com o servidor. Por favor, tente novamente em alguns instantes."), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sms')
def sms():
    return render_template('sms.html')

@app.route('/campaigns')
def campaigns():
    return render_template('campaigns.html')

@app.route('/integrations')
def integrations():
    return render_template('integrations.html')

@app.route('/analytics')
def analytics():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        
        total_messages = len(history)
        success_messages = sum(1 for msg in history if msg['status'] == 'success')
        success_rate = round((success_messages / total_messages * 100) if total_messages > 0 else 0, 1)
        
        manual_messages = sum(1 for msg in history if msg['event_type'] == 'manual')
        campaign_messages = total_messages - manual_messages
        
        messages_by_status = []
        status_counts = Counter(msg['status'] for msg in history)
        for status, count in status_counts.items():
            messages_by_status.append({
                'status': status,
                'count': count,
                'percentage': round(count / total_messages * 100, 1)
            })
        
        messages_by_event = []
        event_counts = Counter(msg['event_type'] for msg in history)
        for event_type, count in event_counts.items():
            messages_by_event.append({
                'type': event_type,
                'count': count,
                'percentage': round(count / total_messages * 100, 1)
            })
        
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
        logger.error(f"Error loading analytics: {str(e)}")
        return render_template('error.html', error="Erro ao carregar análises"), 500

@app.route('/sms-history')
def sms_history():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        return render_template('sms_history.html', sms_history=history)
    except Exception as e:
        logger.error(f"Error loading SMS history: {str(e)}")
        return render_template('error.html', error="Erro ao carregar histórico"), 500

@app.route('/campaign-performance')
def campaign_performance():
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        
        campaign_stats = []
        for campaign in campaigns:
            campaign_messages = [msg for msg in history if msg.get('campaign_id') == campaign['id']]
            messages_sent = len(campaign_messages)
            success_messages = sum(1 for msg in campaign_messages if msg['status'] == 'success')
            success_rate = round((success_messages / messages_sent * 100) if messages_sent > 0 else 0, 1)
            
            last_message = max(campaign_messages, key=lambda x: x['timestamp']) if campaign_messages else None
            
            campaign_stats.append({
                'name': campaign['name'],
                'event_type': campaign['event_type'],
                'messages_sent': messages_sent,
                'success_rate': success_rate,
                'last_message': last_message['timestamp'] if last_message else 'N/A'
            })
        
        total_campaigns = len(campaigns)
        active_campaigns = sum(1 for c in campaign_stats if c['messages_sent'] > 0)
        total_messages = sum(c['messages_sent'] for c in campaign_stats)
        
        recent_activity = sorted(
            [msg for msg in history if msg.get('campaign_id')],
            key=lambda x: x['timestamp'],
            reverse=True
        )[:10]
        
        return render_template('campaign_performance.html',
                             campaigns=campaign_stats,
                             total_campaigns=total_campaigns,
                             active_campaigns=active_campaigns,
                             total_messages=total_messages,
                             recent_activity=recent_activity)
    except Exception as e:
        logger.error(f"Error loading campaign performance: {str(e)}")
        return render_template('error.html', error="Erro ao carregar desempenho das campanhas"), 500

@app.route('/pix/<transaction_id>')
def pix_payment(transaction_id):
    try:
        redis_client = get_redis_connection()
        transaction_data = redis_client.get(f"transaction:{transaction_id}")
        
        if transaction_data:
            transaction = json.loads(transaction_data)
        else:
            with open(TRANSACTIONS_FILE, 'r') as f:
                transactions = json.load(f)
                transaction = transactions.get(transaction_id)
        
        if not transaction:
            logger.error(f"Transaction not found: {transaction_id}")
            return render_template('error.html', error="Transação não encontrada"), 404
        
        template_data = {
            'transaction_id': transaction_id,
            'customer_name': transaction.get('customer_name', ''),
            'total_price': transaction.get('total_price', '0.00'),
            'pix_code': transaction.get('pix_code', ''),
            'products': transaction.get('products', []),
            'created_at': transaction.get('created_at', '')
        }
        
        return render_template('pix_payment.html', **template_data)
    except Exception as e:
        logger.error(f"Error rendering PIX payment page: {str(e)}")
        return render_template('error.html', error="Erro ao carregar página de pagamento"), 500

@app.route('/webhook/<integration_id>', methods=['POST'])
def webhook_handler(integration_id):
    logger.info(f"Received webhook request for integration: {integration_id}")
    
    try:
        redis_client = get_redis_connection()
        
        webhook_data = request.get_json()
        if not webhook_data:
            raise ValueError("Empty webhook data")
        
        logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")
        
        transaction_id = webhook_data.get('transaction_id')
        customer = webhook_data.get('customer', {})
        
        if not all([transaction_id, customer]):
            logger.error("Missing required fields")
            return jsonify({
                'success': False,
                'message': 'Missing required fields: transaction_id or customer data'
            }), 400
        
        try:
            transaction_data = {
                'customer_name': customer.get('name', ''),
                'total_price': format_price(webhook_data.get('total_price', '0')),
                'pix_code': webhook_data.get('pix_code', ''),
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'products': webhook_data.get('plans', [])
            }
            
            redis_client.setex(
                f"transaction:{transaction_id}",
                900,
                json.dumps(transaction_data)
            )
            
            with open(TRANSACTIONS_FILE, 'r+') as f:
                transactions = json.load(f)
                transactions[transaction_id] = transaction_data
                f.seek(0)
                json.dump(transactions, f, indent=2)
                f.truncate()
            
        except (RedisError, IOError) as e:
            logger.error(f"Error storing transaction data: {str(e)}")
        
        payment_url = url_for('pix_payment', transaction_id=transaction_id, _external=True)
        
        status = webhook_data.get('status')
        if status:
            normalized_status = normalize_status(status)
            if normalized_status:
                try:
                    with open(CAMPAIGNS_FILE, 'r') as f:
                        campaigns = json.load(f)
                    
                    matching_campaigns = [
                        c for c in campaigns 
                        if c['integration_id'] == integration_id 
                        and normalize_status(c['event_type']) == normalized_status
                    ]
                    
                    for campaign in matching_campaigns:
                        try:
                            phone = format_phone_number(customer['phone'])
                            message = f"Acesse o link para pagamento: {payment_url}"
                            
                            task = send_sms_task.delay(
                                phone=phone,
                                message=message,
                                operator="claro",
                                campaign_id=campaign['id'],
                                event_type=normalized_status
                            )
                            logger.info(f"Queued SMS task {task.id} for campaign {campaign['id']}")
                        except Exception as e:
                            logger.error(f"Error processing campaign {campaign['id']}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error processing campaigns: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'Webhook processed successfully',
            'payment_url': payment_url
        })
        
    except RedisError as e:
        logger.error(f"Redis error in webhook handler: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Service temporarily unavailable'
        }), 503
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

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Missing request data'}), 400
        
        phone = data.get('phone')
        message = data.get('message')
        operator = data.get('operator', 'claro')
        
        if not all([phone, message]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        task = send_sms_task.delay(
            phone=phone,
            message=message,
            operator=operator,
            event_type='manual'
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS queued successfully',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    try:
        redis_client = get_redis_connection()
        logger.info("Successfully connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis on startup: {str(e)}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)