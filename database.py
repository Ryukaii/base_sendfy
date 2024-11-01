import sqlite3
import os
import json
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

DATABASE_PATH = 'data/sendfy.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database schema"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create transactions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            store_name TEXT,
            method TEXT,
            total_price REAL,
            status TEXT,
            order_url TEXT,
            checkout_url TEXT,
            pix_code TEXT,
            pix_code_image64 TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        ''')
        
        # Create customers table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            document TEXT,
            email TEXT,
            phone TEXT,
            transaction_id TEXT,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id)
        )
        ''')
        
        # Create addresses table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            street TEXT,
            number TEXT,
            district TEXT,
            zip_code TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            transaction_id TEXT,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id)
        )
        ''')
        
        # Create products table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            amount INTEGER,
            value REAL,
            photo TEXT,
            created_at TIMESTAMP,
            transaction_id TEXT,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id)
        )
        ''')
        
        conn.commit()
        logger.info("Database schema initialized successfully")

def save_transaction(data):
    """Save transaction data to database"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Insert transaction
            transaction_data = {
                'id': data['transaction_id'],
                'store_name': data.get('store_name'),
                'method': data.get('method'),
                'total_price': float(data.get('total_price', 0)),
                'status': data.get('status'),
                'order_url': data.get('order_url'),
                'checkout_url': data.get('checkout_url'),
                'pix_code': data.get('pix_code'),
                'pix_code_image64': data.get('pix_code_image64'),
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            
            cursor.execute('''
            INSERT INTO transactions (
                id, store_name, method, total_price, status, 
                order_url, checkout_url, pix_code, pix_code_image64,
                created_at, updated_at
            ) VALUES (
                :id, :store_name, :method, :total_price, :status,
                :order_url, :checkout_url, :pix_code, :pix_code_image64,
                :created_at, :updated_at
            )
            ''', transaction_data)
            
            # Insert customer
            if 'customer' in data:
                customer_data = {
                    'name': data['customer'].get('name'),
                    'document': data['customer'].get('document'),
                    'email': data['customer'].get('email'),
                    'phone': data['customer'].get('phone'),
                    'transaction_id': data['transaction_id']
                }
                
                cursor.execute('''
                INSERT INTO customers (
                    name, document, email, phone, transaction_id
                ) VALUES (
                    :name, :document, :email, :phone, :transaction_id
                )
                ''', customer_data)
            
            # Insert address
            if 'address' in data:
                address_data = {
                    'street': data['address'].get('street'),
                    'number': data['address'].get('number'),
                    'district': data['address'].get('district'),
                    'zip_code': data['address'].get('zip_code'),
                    'city': data['address'].get('city'),
                    'state': data['address'].get('state'),
                    'country': data['address'].get('country'),
                    'transaction_id': data['transaction_id']
                }
                
                cursor.execute('''
                INSERT INTO addresses (
                    street, number, district, zip_code,
                    city, state, country, transaction_id
                ) VALUES (
                    :street, :number, :district, :zip_code,
                    :city, :state, :country, :transaction_id
                )
                ''', address_data)
            
            # Insert products
            if 'plans' in data:
                for plan in data['plans']:
                    for product in plan.get('products', []):
                        product_data = {
                            'id': product['id'],
                            'name': product['name'],
                            'description': product.get('description', ''),
                            'amount': int(product.get('amount', 1)),
                            'value': float(plan.get('value', 0)),
                            'photo': product.get('photo', ''),
                            'created_at': datetime.now(),
                            'transaction_id': data['transaction_id']
                        }
                        
                        cursor.execute('''
                        INSERT INTO products (
                            id, name, description, amount,
                            value, photo, created_at, transaction_id
                        ) VALUES (
                            :id, :name, :description, :amount,
                            :value, :photo, :created_at, :transaction_id
                        )
                        ''', product_data)
            
            conn.commit()
            logger.info(f"Transaction {data['transaction_id']} saved successfully")
            return True
            
    except Exception as e:
        logger.error(f"Error saving transaction: {str(e)}")
        return False

def get_transaction(transaction_id):
    """Get transaction details with related data"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get transaction
            cursor.execute('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
            transaction = dict(cursor.fetchone())
            
            # Get customer
            cursor.execute('SELECT * FROM customers WHERE transaction_id = ?', (transaction_id,))
            customer = cursor.fetchone()
            if customer:
                transaction['customer'] = dict(customer)
            
            # Get address
            cursor.execute('SELECT * FROM addresses WHERE transaction_id = ?', (transaction_id,))
            address = cursor.fetchone()
            if address:
                transaction['address'] = dict(address)
            
            # Get products
            cursor.execute('SELECT * FROM products WHERE transaction_id = ?', (transaction_id,))
            products = cursor.fetchall()
            if products:
                transaction['products'] = [dict(product) for product in products]
            
            return transaction
            
    except Exception as e:
        logger.error(f"Error getting transaction {transaction_id}: {str(e)}")
        return None

# Initialize database when module is imported
init_db()
