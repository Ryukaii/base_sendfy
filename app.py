import json
import os
import uuid
import datetime
import re
import logging
from flask import Flask, render_template, request, jsonify, abort
from celery_worker import send_sms_task
from collections import Counter
import database

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

@app.route('/order/<transaction_id>')
def view_order(transaction_id):
    """Display order details page"""
    try:
        logger.info(f"Accessing order page for transaction: {transaction_id}")
        transaction = database.get_transaction(transaction_id)
        
        if not transaction:
            logger.warning(f"Transaction not found: {transaction_id}")
            return render_template('error.html', 
                                error="Pedido não encontrado",
                                message="O pedido que você está procurando não existe ou foi removido."), 404
        
        # Format address if exists
        if transaction.get('address'):
            address_parts = []
            if transaction['address'].get('street'):
                address_parts.append(transaction['address']['street'])
            if transaction['address'].get('number'):
                address_parts.append(transaction['address']['number'])
            if transaction['address'].get('district'):
                address_parts.append(transaction['address']['district'])
            transaction['formatted_address'] = ' - '.join(address_parts)
        
        return render_template('order.html', 
                             transaction=transaction,
                             page_title=f"Pedido #{transaction_id}")
                             
    except Exception as e:
        logger.error(f"Error rendering order page for transaction {transaction_id}: {str(e)}")
        return render_template('error.html', 
                             error="Erro ao carregar o pedido",
                             message="Ocorreu um erro ao carregar os detalhes do pedido. Por favor, tente novamente."), 500

[... rest of the file remains the same ...]
