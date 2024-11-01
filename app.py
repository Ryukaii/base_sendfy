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
        pix_code = transaction.get('pix_code', '')
        
        return render_template(
            'payment.html',
            customer_name=customer_name,
            customer_address=customer_address if customer_address.strip() != ',' else None,
            product_name=product_name,
            pix_code=pix_code
        )
    except Exception as e:
        logger.error(f"Error processing payment page: {str(e)}")
        return render_template('error.html', error="Erro ao processar página de pagamento"), 500

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
        
        try:
            with open(TRANSACTIONS_FILE, 'r') as f:
                transactions = json.load(f)
            
            transaction_data = {
                'transaction_id': transaction_id,
                'customer_name': customer.get('name', ''),
                'customer_phone': formatted_phone,
                'customer_email': customer.get('email', ''),
                'address': webhook_data.get('address', {}),
                'product_name': webhook_data['plans'][0]['name'] if webhook_data.get('plans') else '',
                'total_price': format_price(webhook_data.get('total_price', '0')),
                'pix_code': webhook_data.get('pix_code', ''),
                'status': normalized_status,
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            existing_idx = next((i for i, t in enumerate(transactions) if t['transaction_id'] == transaction_id), None)
            if existing_idx is not None:
                transactions[existing_idx] = transaction_data
            else:
                transactions.append(transaction_data)
            
            with open(TRANSACTIONS_FILE, 'w') as f:
                json.dump(transactions, f, indent=2)
            
            logger.info(f"Stored transaction data for ID: {transaction_id}")
            
        except Exception as e:
            logger.error(f"Error storing transaction data: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Error storing transaction data: {str(e)}'
            }), 500
        
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
                    'checkout_url': webhook_data.get('checkout_url', ''),
                    'payment_url': f"{request.host_url.rstrip('/')}/payment/{transaction_id}"
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
