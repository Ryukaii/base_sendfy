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
CUSTOMERS_FILE = 'data/customers.json'

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

for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE, TRANSACTIONS_FILE, CUSTOMERS_FILE]:
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

def format_price(price_str):
    try:
        if isinstance(price_str, (int, float)):
            return "{:.2f}".format(float(price_str) / 100)
        
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

def save_transaction(transaction_data):
    try:
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        transactions = []
    
    transactions.append(transaction_data)
    
    with open(TRANSACTIONS_FILE, 'w') as f:
        json.dump(transactions, f, indent=2)

def save_customer(customer_data):
    try:
        with open(CUSTOMERS_FILE, 'r') as f:
            customers = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        customers = []
    
    customers.append(customer_data)
    
    with open(CUSTOMERS_FILE, 'w') as f:
        json.dump(customers, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/payment/<transaction_id>')
def payment(transaction_id):
    try:
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
        
        transaction = next((t for t in transactions if t['transaction_id'] == transaction_id), None)
        if not transaction:
            return render_template('error.html', error="Transação não encontrada"), 404
        
        if transaction['status'] != 'pending':
            return redirect(url_for('payment_status', transaction_id=transaction_id))
        
        customer_name = transaction['customer']['name']
        address = None
        if transaction['address'].get('street'):
            address = f"{transaction['address']['street']}, {transaction['address']['number']}, {transaction['address']['district']}, {transaction['address']['city']}-{transaction['address']['state']}"
        
        total_price = format_price(transaction['total_price'])
        product_name = transaction['plans'][0]['name'] if transaction['plans'] else "Produto"
        pix_code = transaction['pix_code']
        
        return render_template('payment.html',
                             transaction_id=transaction_id,
                             customer_name=customer_name,
                             address=address,
                             total_price=total_price,
                             product_name=product_name,
                             pix_code=pix_code)
    except Exception as e:
        logger.error(f"Error processing payment page: {str(e)}")
        return render_template('error.html', error="Erro ao processar página de pagamento"), 500

@app.route('/payment/expired/<transaction_id>')
def payment_expired(transaction_id):
    try:
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
        
        transaction_index = next((i for i, t in enumerate(transactions) if t['transaction_id'] == transaction_id), None)
        if transaction_index is not None:
            transactions[transaction_index]['status'] = 'expired'
            with open(TRANSACTIONS_FILE, 'w') as f:
                json.dump(transactions, f, indent=2)
        
        return render_template('payment_expired.html', transaction_id=transaction_id)
    except Exception as e:
        logger.error(f"Error processing expired payment: {str(e)}")
        return render_template('error.html', error="Erro ao processar expiração do pagamento"), 500

@app.route('/payment/status/<transaction_id>')
def payment_status(transaction_id):
    try:
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
        
        transaction = next((t for t in transactions if t['transaction_id'] == transaction_id), None)
        if not transaction:
            return render_template('error.html', error="Transação não encontrada"), 404
        
        return render_template('payment_status.html', 
                             transaction=transaction,
                             total_price=format_price(transaction['total_price']))
    except Exception as e:
        logger.error(f"Error processing payment status: {str(e)}")
        return render_template('error.html', error="Erro ao verificar status do pagamento"), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
