import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify, flash
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
    initialize_json_file(file_path)

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

# API Routes
@app.route('/api/integrations')
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
        logger.info("Successfully retrieved integrations list")
        return jsonify(integrations)
    except Exception as e:
        logger.error(f"Error retrieving integrations: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving integrations'
        }), 500

@app.route('/api/integrations', methods=['POST'])
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            logger.error("Missing integration name in request")
            return jsonify({
                'success': False,
                'message': 'Integration name is required'
            }), 400

        integration_id = str(uuid.uuid4())
        webhook_url = f'/webhook/{integration_id}'

        integration = {
            'id': integration_id,
            'name': data['name'],
            'webhook_url': webhook_url,
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)

        integrations.append(integration)

        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)

        logger.info(f"Created new integration: {integration_id}")
        return jsonify({
            'success': True,
            'message': 'Integration created successfully',
            'integration': integration
        })

    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error creating integration'
        }), 500

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)

        integration_index = next(
            (i for i, integration in enumerate(integrations) 
             if integration['id'] == integration_id), 
            None
        )

        if integration_index is None:
            logger.error(f"Integration not found: {integration_id}")
            return jsonify({
                'success': False,
                'message': 'Integration not found'
            }), 404

        deleted_integration = integrations.pop(integration_index)

        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)

        logger.info(f"Deleted integration: {integration_id}")
        return jsonify({
            'success': True,
            'message': 'Integration deleted successfully',
            'deleted': deleted_integration
        })

    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error deleting integration'
        }), 500

# Transaction and Payment Routes
@app.route('/api/transactions', methods=['POST'])
def create_transaction():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Missing request data")

        required_fields = ['customer_name', 'customer_phone', 'product_name', 'total_price']
        if not all(field in data for field in required_fields):
            raise ValueError("Missing required fields")

        transaction_id = str(uuid.uuid4())[:8]
        transaction = {
            'transaction_id': transaction_id,
            'customer_name': data['customer_name'],
            'customer_phone': data['customer_phone'],
            'customer_email': data.get('customer_email', ''),
            'address': data.get('address', {}),
            'product_name': data['product_name'],
            'total_price': format_price(data['total_price']),
            'pix_code': data.get('pix_code', ''),
            'status': 'pending',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)

        transactions.append(transaction)

        with open(TRANSACTIONS_FILE, 'w') as f:
            json.dump(transactions, f, indent=2)

        logger.info(f"Created new transaction: {transaction_id}")
        return jsonify({
            'success': True,
            'message': 'Transaction created successfully',
            'transaction_id': transaction_id,
            'payment_url': f"/payment/{transaction_id}"
        })

    except ValueError as e:
        logger.error(f"Validation error in create_transaction: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error creating transaction'
        }), 500

@app.route('/api/transactions/<transaction_id>', methods=['PUT'])
def update_transaction(transaction_id):
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Missing request data")

        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)

        transaction_index = next(
            (i for i, t in enumerate(transactions) 
             if t['transaction_id'] == transaction_id),
            None
        )

        if transaction_index is None:
            raise ValueError("Transaction not found")

        transaction = transactions[transaction_index]
        transaction.update({
            'status': data.get('status', transaction['status']),
            'pix_code': data.get('pix_code', transaction['pix_code'])
        })

        with open(TRANSACTIONS_FILE, 'w') as f:
            json.dump(transactions, f, indent=2)

        logger.info(f"Updated transaction: {transaction_id}")
        return jsonify({
            'success': True,
            'message': 'Transaction updated successfully',
            'transaction': transaction
        })

    except ValueError as e:
        logger.error(f"Validation error in update_transaction: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f"Error updating transaction: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error updating transaction'
        }), 500

# Page Routes
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/payment/<transaction_id>')
def payment(transaction_id):
    try:
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
        
        transaction = next((t for t in transactions if t['transaction_id'] == transaction_id), None)
        if not transaction:
            return render_template('error.html', error="Transação não encontrada"), 404
        
        customer_name = transaction['customer_name']
        customer_address = f"{transaction.get('address', {}).get('street', '')}, {transaction.get('address', {}).get('number', '')}"
        if transaction.get('address', {}).get('city'):
            customer_address += f", {transaction['address']['city']}/{transaction['address']['state']}"
        
        product_name = transaction.get('product_name', '')
        total_price = transaction.get('total_price', '')
        pix_code = transaction.get('pix_code', '')
        
        return render_template(
            'payment.html',
            customer_name=customer_name,
            customer_address=customer_address if customer_address.strip() != ',' else None,
            product_name=product_name,
            total_price=total_price,
            pix_code=pix_code
        )
    except Exception as e:
        logger.error(f"Error processing payment page: {str(e)}")
        return render_template('error.html', error="Erro ao processar página de pagamento"), 500

@app.route('/sms')
def sms():
    try:
        return render_template('sms.html')
    except Exception as e:
        logger.error(f"Error rendering SMS template: {str(e)}")
        return render_template('error.html', error="Failed to load page"), 500

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Missing request data")
        
        phone = data.get('phone')
        message = data.get('message')
        
        if not all([phone, message]):
            raise ValueError("Missing required fields: phone or message")
        
        if len(message) > 160:
            raise ValueError("Message exceeds maximum length of 160 characters")
        
        try:
            formatted_phone = format_phone_number(phone)
        except ValueError as e:
            raise ValueError(f"Invalid phone number: {str(e)}")
        
        task = send_sms_task.delay(
            phone=formatted_phone,
            message=message,
            operator="claro",
            event_type="manual"
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS sent successfully',
            'task_id': task.id
        })
        
    except ValueError as e:
        logger.error(f"Validation error in send_sms: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
