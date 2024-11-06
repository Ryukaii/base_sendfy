import json
import os
import uuid
import datetime
import re
import logging
import fcntl
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from celery_worker import send_sms_task
from collections import Counter
from functools import wraps
import traceback

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

DATA_DIR = 'data'
INTEGRATIONS_FILE = os.path.join(DATA_DIR, 'integrations.json')
CAMPAIGNS_FILE = os.path.join(DATA_DIR, 'campaigns.json')
SMS_HISTORY_FILE = os.path.join(DATA_DIR, 'sms_history.json')
TRANSACTIONS_FILE = os.path.join(DATA_DIR, 'transactions.json')

def ensure_data_directory():
    try:
        os.makedirs(DATA_DIR, mode=0o755, exist_ok=True)
        logger.info(f"Data directory {DATA_DIR} exists and is accessible")
    except Exception as e:
        logger.critical(f"Failed to create/access data directory: {str(e)}")
        raise

def initialize_json_file(filepath, initial_data=None):
    try:
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(initial_data if initial_data is not None else [], f, indent=2)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.chmod(filepath, 0o644)
            logger.info(f"Initialized JSON file: {filepath}")
        return True
    except Exception as e:
        logger.error(f"Error initializing JSON file {filepath}: {str(e)}\n{traceback.format_exc()}")
        return False

def with_file_lock(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        file_path = kwargs.get('file_path')
        if not file_path:
            raise ValueError("file_path parameter is required")
        try:
            with open(file_path, 'r+' if os.path.exists(file_path) else 'w+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                result = func(*args, **kwargs, file_handle=f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return result
        except Exception as e:
            logger.error(f"Error in file operation for {file_path}: {str(e)}\n{traceback.format_exc()}")
            raise
    return wrapper

@with_file_lock
def read_json_file(file_path, file_handle=None):
    try:
        file_handle.seek(0)
        data = json.load(file_handle)
        logger.debug(f"Successfully read JSON file: {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Error reading {file_path}: {str(e)}")
        return []

@with_file_lock
def write_json_file(file_path, data, file_handle=None):
    try:
        file_handle.seek(0)
        json.dump(data, file_handle, indent=2)
        file_handle.truncate()
        logger.debug(f"Successfully wrote to JSON file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error writing to {file_path}: {str(e)}")
        return False

def format_phone_number(phone):
    try:
        logger.debug(f"Formatting phone number: {phone}")
        numbers = re.sub(r'\D', '', phone)
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

def normalize_status(status):
    if not status:
        return None
    try:
        logger.debug(f"Normalizing status: {status}")
        status = str(status).lower().strip()
        status_map = {
            'pending': 'pending', 'pendente': 'pending', 'venda pendente': 'pending',
            'aguardando': 'pending', 'aguardando pagamento': 'pending', 'waiting': 'pending',
            'waiting_payment': 'pending', 'approved': 'approved', 'aprovado': 'approved',
            'venda aprovada': 'approved', 'completed': 'approved', 'concluido': 'approved',
            'pago': 'approved', 'paid': 'approved', 'payment_confirmed': 'approved',
            'pagamento_confirmado': 'approved', 'abandoned_cart': 'abandoned',
            'carrinho_abandonado': 'abandoned', 'canceled': 'canceled', 'cancelado': 'canceled',
            'refused': 'canceled', 'recusado': 'canceled'
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

ensure_data_directory()
for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE, TRANSACTIONS_FILE]:
    initialize_json_file(file_path)

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/campaigns')
def campaigns():
    try:
        return render_template('campaigns.html')
    except Exception as e:
        logger.error(f"Error rendering campaigns template: {str(e)}")
        return render_template('error.html', error="Falha ao carregar página"), 500

@app.route('/sms')
def sms():
    try:
        return render_template('sms.html')
    except Exception as e:
        logger.error(f"Error rendering sms template: {str(e)}")
        return render_template('error.html', error="Falha ao carregar página"), 500

@app.route('/integrations')
def integrations():
    try:
        return render_template('integrations.html')
    except Exception as e:
        logger.error(f"Error rendering integrations template: {str(e)}")
        return render_template('error.html', error="Falha ao carregar página"), 500

@app.route('/analytics')
def analytics():
    try:
        return render_template('analytics.html')
    except Exception as e:
        logger.error(f"Error rendering analytics template: {str(e)}")
        return render_template('error.html', error="Falha ao carregar página"), 500

@app.route('/sms-history')
def sms_history():
    try:
        return render_template('sms_history.html')
    except Exception as e:
        logger.error(f"Error rendering sms history template: {str(e)}")
        return render_template('error.html', error="Falha ao carregar página"), 500

@app.route('/campaign-performance')
def campaign_performance():
    try:
        return render_template('campaign_performance.html')
    except Exception as e:
        logger.error(f"Error rendering campaign performance template: {str(e)}")
        return render_template('error.html', error="Falha ao carregar página"), 500

@app.route('/payment/<transaction_id>')
def payment(transaction_id):
    try:
        logger.debug(f"Loading payment page for transaction: {transaction_id}")
        transactions = read_json_file(file_path=TRANSACTIONS_FILE)
        transaction = next((t for t in transactions if t['transaction_id'] == transaction_id), None)
        if not transaction:
            logger.warning(f"Transaction not found: {transaction_id}")
            return render_template('error.html', error="Transação não encontrada"), 404
        
        customer_name = transaction['customer_name']
        address = transaction.get('address', {})
        customer_address = f"{address.get('street', '')}, {address.get('number', '')}"
        if address.get('city'):
            customer_address += f", {address['city']}/{address['state']}"
        
        context = {
            'customer_name': customer_name,
            'customer_address': customer_address if customer_address.strip() != ',' else None,
            'product_name': transaction.get('product_name', ''),
            'total_price': transaction.get('total_price', ''),
            'pix_code': transaction.get('pix_code', '')
        }
        
        logger.debug(f"Rendering payment template with context: {context}")
        return render_template('payment.html', **context)
    except Exception as e:
        error_msg = f"Error processing payment page: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return render_template('error.html', error="Erro ao processar página de pagamento"), 500

@app.route('/api/transactions', methods=['POST'])
def create_transaction():
    try:
        logger.debug("Creating new transaction")
        data = request.get_json()
        
        if not data:
            raise ValueError("Missing request data")

        required_fields = ['customer_name', 'customer_phone', 'product_name', 'total_price']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        transaction_id = str(uuid.uuid4())[:8]
        transaction = {
            'transaction_id': transaction_id,
            'customer_name': data['customer_name'],
            'customer_phone': format_phone_number(data['customer_phone']),
            'customer_email': data.get('customer_email', ''),
            'address': data.get('address', {
                'street': '',
                'number': '',
                'complement': '',
                'district': '',
                'zip_code': '',
                'city': '',
                'state': '',
                'country': ''
            }),
            'product_name': data['product_name'],
            'total_price': format_price(data['total_price']),
            'pix_code': data.get('pix_code', ''),
            'status': 'pending',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        transactions = read_json_file(file_path=TRANSACTIONS_FILE)
        transactions.append(transaction)

        if not write_json_file(file_path=TRANSACTIONS_FILE, data=transactions):
            raise Exception("Failed to write transaction data")

        logger.info(f"Created new transaction: {transaction_id}")
        return jsonify({
            'success': True,
            'message': 'Transaction created successfully',
            'transaction_id': transaction_id,
            'payment_url': f"/payment/{transaction_id}"
        })

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error in create_transaction: {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 400
    except Exception as e:
        error_msg = f"Error creating transaction: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/transactions/<transaction_id>', methods=['PUT'])
def update_transaction(transaction_id):
    try:
        logger.debug(f"Updating transaction: {transaction_id}")
        data = request.get_json()
        
        if not data:
            raise ValueError("Missing request data")

        transactions = read_json_file(file_path=TRANSACTIONS_FILE)
        transaction_index = next(
            (i for i, t in enumerate(transactions) 
             if t['transaction_id'] == transaction_id),
            None
        )

        if transaction_index is None:
            raise ValueError("Transaction not found")

        transaction = transactions[transaction_index]
        
        if 'status' in data:
            transaction['status'] = normalize_status(data['status'])
        if 'pix_code' in data:
            transaction['pix_code'] = data['pix_code']
        
        transaction['updated_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not write_json_file(file_path=TRANSACTIONS_FILE, data=transactions):
            raise Exception("Failed to write updated transaction data")

        if data.get('status') == 'approved' and transaction['status'] == 'approved':
            try:
                message = f"Olá {transaction['customer_name']}, seu pagamento de R$ {transaction['total_price']} foi confirmado! Obrigado pela compra."
                send_sms_task.delay(
                    phone=transaction['customer_phone'],
                    message=message,
                    event_type="payment_confirmed"
                )
            except Exception as e:
                logger.error(f"Error sending confirmation SMS: {str(e)}")

        logger.info(f"Successfully updated transaction: {transaction_id}")
        return jsonify({
            'success': True,
            'message': 'Transaction updated successfully',
            'transaction': transaction
        })

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error in update_transaction: {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 400
    except Exception as e:
        error_msg = f"Error updating transaction: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/campaigns', methods=['GET'])
def get_campaigns():
    try:
        campaigns = read_json_file(file_path=CAMPAIGNS_FILE)
        logger.info(f"Successfully retrieved {len(campaigns)} campaigns")
        return jsonify(campaigns)
    except Exception as e:
        error_msg = f"Error retrieving campaigns: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/campaigns', methods=['POST'])
def create_campaign():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Missing request data")

        required_fields = ['name', 'integration_id', 'event_type', 'message_template']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        campaigns = read_json_file(file_path=CAMPAIGNS_FILE)
        campaigns.append(campaign)

        if not write_json_file(file_path=CAMPAIGNS_FILE, data=campaigns):
            raise Exception("Failed to write campaign data")

        logger.info(f"Created new campaign: {campaign['id']}")
        return jsonify({
            'success': True,
            'message': 'Campaign created successfully',
            'campaign': campaign
        })

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error in create_campaign: {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 400
    except Exception as e:
        error_msg = f"Error creating campaign: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/campaigns/<campaign_id>', methods=['PUT', 'DELETE'])
def manage_campaign(campaign_id):
    try:
        campaigns = read_json_file(file_path=CAMPAIGNS_FILE)
        campaign_index = next(
            (i for i, c in enumerate(campaigns) if c['id'] == campaign_id),
            None
        )

        if campaign_index is None:
            raise ValueError("Campaign not found")

        if request.method == 'DELETE':
            deleted_campaign = campaigns.pop(campaign_index)
            if not write_json_file(file_path=CAMPAIGNS_FILE, data=campaigns):
                raise Exception("Failed to save changes after deletion")
            
            logger.info(f"Deleted campaign: {campaign_id}")
            return jsonify({
                'success': True,
                'message': 'Campaign deleted successfully'
            })

        data = request.get_json()
        if not data:
            raise ValueError("Missing request data")

        campaign = campaigns[campaign_index]
        updateable_fields = ['name', 'event_type', 'message_template']
        
        for field in updateable_fields:
            if field in data:
                campaign[field] = data[field]
        
        campaign['updated_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not write_json_file(file_path=CAMPAIGNS_FILE, data=campaigns):
            raise Exception("Failed to save updated campaign")

        logger.info(f"Updated campaign: {campaign_id}")
        return jsonify({
            'success': True,
            'message': 'Campaign updated successfully',
            'campaign': campaign
        })

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error in manage_campaign: {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 400
    except Exception as e:
        error_msg = f"Error managing campaign: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/integrations', methods=['GET'])
def get_integrations():
    try:
        integrations = read_json_file(file_path=INTEGRATIONS_FILE)
        logger.info(f"Successfully retrieved {len(integrations)} integrations")
        return jsonify(integrations)
    except Exception as e:
        error_msg = f"Error retrieving integrations: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/integrations', methods=['POST'])
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            raise ValueError("Missing integration name")

        integration = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'webhook_url': f"/webhook/{str(uuid.uuid4())}",
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        integrations = read_json_file(file_path=INTEGRATIONS_FILE)
        integrations.append(integration)

        if not write_json_file(file_path=INTEGRATIONS_FILE, data=integrations):
            raise Exception("Failed to write integration data")

        logger.info(f"Created new integration: {integration['id']}")
        return jsonify({
            'success': True,
            'message': 'Integration created successfully',
            'integration': integration
        })

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error in create_integration: {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 400
    except Exception as e:
        error_msg = f"Error creating integration: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
def delete_integration(integration_id):
    try:
        integrations = read_json_file(file_path=INTEGRATIONS_FILE)
        integration_index = next(
            (i for i, t in enumerate(integrations) if t['id'] == integration_id),
            None
        )

        if integration_index is None:
            raise ValueError("Integration not found")

        deleted_integration = integrations.pop(integration_index)
        
        if not write_json_file(file_path=INTEGRATIONS_FILE, data=integrations):
            raise Exception("Failed to save changes after integration deletion")

        campaigns = read_json_file(file_path=CAMPAIGNS_FILE)
        campaigns = [c for c in campaigns if c['integration_id'] != integration_id]
        
        if not write_json_file(file_path=CAMPAIGNS_FILE, data=campaigns):
            raise Exception("Failed to delete associated campaigns")

        logger.info(f"Deleted integration: {integration_id}")
        return jsonify({
            'success': True,
            'message': 'Integration and associated campaigns deleted successfully'
        })

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"Validation error in delete_integration: {error_msg}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 400
    except Exception as e:
        error_msg = f"Error deleting integration: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Missing request data")
            
        required_fields = ['phone', 'message']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
            
        # Format phone number
        phone = format_phone_number(data['phone'])
        
        # Send SMS using celery task
        task = send_sms_task.delay(
            phone=phone,
            message=data['message'],
            event_type='manual'
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS enviado com sucesso!'
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Erro ao enviar SMS. Por favor, tente novamente.'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
