import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
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

# Create data directory and initialize files if they don't exist
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pix/<transaction_id>')
def pix_payment(transaction_id):
    try:
        # Load transaction data
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
        
        transaction = transactions.get(transaction_id)
        if not transaction:
            logger.error(f"Transaction not found: {transaction_id}")
            return render_template('error.html', error="Transação não encontrada"), 404
        
        # Format the template variables
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
        webhook_data = request.get_json()
        if not webhook_data:
            raise ValueError("Empty webhook data")
        
        logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")
        
        # Extract transaction data
        transaction_id = webhook_data.get('transaction_id')
        customer = webhook_data.get('customer', {})
        
        if not all([transaction_id, customer]):
            logger.error("Missing required fields")
            return jsonify({
                'success': False,
                'message': 'Missing required fields: transaction_id or customer data'
            }), 400
        
        # Format price from cents to reais if needed
        price = webhook_data.get('total_price', '0')
        if isinstance(price, (int, float)) and price > 100:
            price = float(price) / 100

        # Create transaction record
        transaction = {
            'customer_name': customer.get('name', ''),
            'total_price': format_price(price),
            'pix_code': webhook_data.get('pix_code', ''),
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'products': webhook_data.get('plans', [])
        }
        
        # Save transaction
        with open(TRANSACTIONS_FILE, 'r+') as f:
            transactions = json.load(f)
            transactions[transaction_id] = transaction
            f.seek(0)
            json.dump(transactions, f, indent=2)
            f.truncate()
        
        # Generate payment URL
        payment_url = url_for('pix_payment', transaction_id=transaction_id, _external=True)
        
        # Process webhook for SMS notifications
        status = webhook_data.get('status')
        if status:
            normalized_status = normalize_status(status)
            if normalized_status:
                # Find matching campaigns
                with open(CAMPAIGNS_FILE, 'r') as f:
                    campaigns = json.load(f)
                
                matching_campaigns = [
                    c for c in campaigns 
                    if c['integration_id'] == integration_id 
                    and normalize_status(c['event_type']) == normalized_status
                ]
                
                # Process matching campaigns
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
        
        return jsonify({
            'success': True,
            'message': 'Webhook processed successfully',
            'payment_url': payment_url
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook data: {str(e)}")
        return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({'success': False, 'message': f'Internal server error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
