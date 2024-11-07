import os
import json
import uuid
import fcntl
import logging
import datetime
import re
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models.users import User
from celery_worker import send_sms_task

app = Flask(__name__)
app.secret_key = 'sendfy-secure-key-2024'  # Fixed secret key for session persistence

# Setup login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
TRANSACTIONS_FILE = 'data/transactions.json'
SMS_HISTORY_FILE = 'data/sms_history.json'
SCHEDULED_SMS_FILE = 'data/scheduled_sms.json'

def ensure_data_files():
    if not os.path.exists('data'):
        os.makedirs('data')
    data_files = {
        INTEGRATIONS_FILE: [],
        CAMPAIGNS_FILE: [],
        TRANSACTIONS_FILE: [],
        SMS_HISTORY_FILE: [],
        SCHEDULED_SMS_FILE: []
    }
    for file_path, default_data in data_files.items():
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump(default_data, f)

def safe_read_json(file_path):
    try:
        if not os.path.exists(file_path):
            return []
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []

def safe_write_json(file_path, data):
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error writing to {file_path}: {e}")
        return False

def handle_api_error(message, status_code=400):
    return jsonify({
        'success': False,
        'error': message
    }), status_code

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso restrito a administradores', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})

# Routes
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.get_by_username(username)
        if user and user.check_password(password):
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
            
        flash('Usuário ou senha inválidos', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.get_by_username(username):
            flash('Nome de usuário já existe', 'danger')
            return render_template('register.html')
            
        user = User.create(username=username, password=password)
        if user:
            login_user(user)
            flash('Conta criada com sucesso!', 'success')
            return redirect(url_for('index'))
            
        flash('Erro ao criar usuário', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado', 'success')
    return redirect(url_for('login'))

@app.route('/sms')
@login_required
def sms():
    return render_template('sms.html')

@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        # Check if user has enough credits
        if not current_user.has_sufficient_credits(1):
            return handle_api_error('Créditos insuficientes para enviar SMS')
            
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message']):
            return handle_api_error('Número de telefone e mensagem são obrigatórios')
        
        # Format phone number
        phone = data['phone']
        if not phone.startswith('+55'):
            phone = f'+55{phone}'
        
        # Deduct credits before sending
        if not current_user.deduct_credits(1):
            return handle_api_error('Falha ao deduzir créditos')
            
        # Queue SMS task
        task = send_sms_task.delay(
            phone=phone,
            message=data['message'],
            event_type='manual'
        )
        
        # Log SMS in history
        with open(SMS_HISTORY_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            history = json.load(f)
            history.append({
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'phone': phone,
                'message': data['message'],
                'type': 'manual',
                'status': 'pending',
                'user_id': current_user.id
            })
            f.seek(0)
            json.dump(history, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        return jsonify({
            'success': True,
            'message': 'SMS enviado com sucesso',
            'credits_remaining': current_user.credits
        })
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        # Refund credit if SMS failed to queue
        current_user.add_credits(1)
        return handle_api_error('Erro ao enviar SMS. Por favor, tente novamente.')

@app.route('/sms-history')
@login_required
def sms_history():
    # Load SMS history for current user
    with open(SMS_HISTORY_FILE, 'r') as f:
        all_history = json.load(f)
        user_history = [
            sms for sms in all_history 
            if sms.get('user_id') == current_user.id
        ]
        user_history.reverse()  # Most recent first
        
    return render_template('sms_history.html', sms_history=user_history)

@app.route('/campaigns')
@login_required
def campaigns():
    return render_template('campaigns.html')

@app.route('/integrations')
@login_required
def integrations():
    return render_template('integrations.html')

# Admin routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.get_all()
    
    # Get SMS history for statistics
    with open(SMS_HISTORY_FILE, 'r') as f:
        sms_history = json.load(f)
    
    # Get campaigns for statistics
    with open(CAMPAIGNS_FILE, 'r') as f:
        campaigns = json.load(f)
    
    # Calculate statistics
    total_sms = len(sms_history)
    success_sms = len([sms for sms in sms_history if sms.get('status') == 'success'])
    success_rate = (success_sms / total_sms * 100) if total_sms > 0 else 0
    
    stats = {
        'total_users': len(users),
        'total_sms': total_sms,
        'active_campaigns': len(campaigns),
        'success_rate': round(success_rate, 1)
    }
    
    return render_template('admin/dashboard.html', users=users, stats=stats)

# User management API routes
@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['username', 'password']):
            return handle_api_error('Username and password are required')
        
        user = User.create(
            username=data['username'],
            password=data['password'],
            is_admin=data.get('is_admin', False),
            credits=data.get('credits', 0)
        )
        
        if not user:
            return handle_api_error('Failed to create user')
            
        return jsonify({
            'success': True,
            'message': 'User created successfully'
        })
        
    except Exception as e:
        return handle_api_error(f'Error creating user: {str(e)}')

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    try:
        # Don't allow deleting self
        if current_user.id == user_id:
            return handle_api_error('Cannot delete your own account')
        
        success = User.delete(user_id)
        if not success:
            return handle_api_error('Failed to delete user')
            
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        })
        
    except Exception as e:
        return handle_api_error(f'Error deleting user: {str(e)}')

@app.route('/api/users/<user_id>/credits', methods=['POST'])
@login_required
@admin_required
def manage_credits(user_id):
    try:
        data = request.get_json()
        if not data or 'amount' not in data or 'operation' not in data:
            return handle_api_error('Amount and operation are required')
        
        user = User.get(user_id)
        if not user:
            return handle_api_error('User not found', 404)
            
        amount = int(data['amount'])
        operation = data['operation']
        
        if operation == 'add':
            success = user.add_credits(amount)
        elif operation == 'remove':
            success = user.deduct_credits(amount)
        else:
            return handle_api_error('Invalid operation')
            
        if not success:
            return handle_api_error('Failed to update credits')
            
        return jsonify({
            'success': True,
            'message': f'Credits {"added to" if operation == "add" else "removed from"} user successfully'
        })
        
    except Exception as e:
        logger.error(f"Error managing credits: {str(e)}")
        return handle_api_error(f'Error managing credits: {str(e)}')

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error={
        'code': 404,
        'description': 'Página não encontrada'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error={
        'code': 500,
        'description': 'Erro interno do servidor'
    }), 500

# Webhook route
@app.route('/webhook/<path:webhook_path>', methods=['POST'])
def webhook_handler(webhook_path):
    try:
        webhook_data = request.get_json()
        logger.debug(f"Received webhook data: {webhook_data}")
        
        # Find integration with matching webhook URL
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            integration = next((i for i in integrations if webhook_path in i['webhook_url']), None)
        
        if not integration:
            logger.error(f"No integration found for webhook path: {webhook_path}")
            return handle_api_error('Integration not found', 404)
            
        # Get user who owns the integration
        user = User.get(integration['user_id'])
        if not user:
            logger.error(f"User not found for integration {integration['id']}")
            return handle_api_error('Integration owner not found', 404)
            
        # Load campaigns for this integration
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
            
        # Get status from webhook data
        status = webhook_data.get('status', 'pending').lower()
        
        # Find matching campaigns for this status
        matching_campaigns = [
            c for c in campaigns 
            if c['integration_id'] == integration['id'] 
            and c['event_type'].lower() == status
            and c['user_id'] == user.id
        ]
        
        if not matching_campaigns:
            logger.warning(f"No campaigns found for integration {integration['id']} and status {status}")
            return jsonify({
                'success': True,
                'message': 'No matching campaigns found for this event type'
            })
            
        # Create transaction record
        transaction_id = str(uuid.uuid4())[:8]
        customer_data = webhook_data.get('customer', {})
        
        transaction = {
            'transaction_id': transaction_id,
            'customer_name': customer_data.get('name', ''),
            'customer_phone': customer_data.get('phone', ''),
            'customer_email': customer_data.get('email', ''),
            'product_name': webhook_data.get('product_name', ''),
            'total_price': webhook_data.get('total_price', '0.00'),
            'pix_code': webhook_data.get('pix_code', ''),
            'status': status,
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Save transaction
        with open(TRANSACTIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            transactions = json.load(f)
            transactions.append(transaction)
            f.seek(0)
            json.dump(transactions, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        success_count = 0
        # Send SMS for each matching campaign
        for campaign in matching_campaigns:
            try:
                if not user.has_sufficient_credits(1):
                    logger.warning(f"User {user.id} has insufficient credits for campaign {campaign['id']}")
                    continue
                    
                # Get first name
                full_name = customer_data.get('name', '')
                first_name = full_name.split()[0] if full_name else ''
                
                # Format phone number
                phone = customer_data.get('phone', '')
                if not phone.startswith('+55'):
                    phone = f'+55{phone}'
                
                # Format message
                message = campaign['message_template']
                message = message.replace('{customer.first_name}', first_name)
                message = message.replace('{total_price}', webhook_data.get('total_price', ''))
                
                # Add PIX link only for pending status
                if status == 'pending':
                    # Format customer name for URL (remove spaces, special chars)
                    url_safe_name = re.sub(r'[^a-zA-Z0-9]', '', customer_data.get('name', ''))
                    payment_url = f"{request.host_url}payment/{url_safe_name}/{transaction_id}"
                    message = message.replace('{link_pix}', payment_url)
                
                # Deduct credit and send SMS
                if user.deduct_credits(1):
                    send_sms_task.delay(
                        phone=phone,
                        message=message,
                        event_type=campaign['event_type']
                    )
                    success_count += 1
                    logger.info(f"SMS queued for campaign {campaign['id']}")
                
            except Exception as e:
                logger.error(f"Error sending SMS for campaign {campaign['id']}: {str(e)}")
                # Refund credit if SMS failed to queue
                user.add_credits(1)
                
        return jsonify({
            'success': True,
            'message': f'Webhook processed successfully. Sent {success_count} messages',
            'transaction_id': transaction_id
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return handle_api_error('Error processing webhook')

@app.route('/payment/<customer_name>/<transaction_id>')
def payment(customer_name, transaction_id):
    try:
        with open(TRANSACTIONS_FILE, 'r') as f:
            transactions = json.load(f)
            transaction = next((t for t in transactions if t['transaction_id'] == transaction_id), None)
            
        if not transaction:
            return render_template('error.html', error='Transaction not found')
            
        return render_template('payment.html',
            customer_name=transaction['customer_name'],
            pix_code=transaction['pix_code']
        )
    except Exception as e:
        logger.error(f"Error loading payment page: {str(e)}")
        return render_template('error.html', error='Error loading payment page')

if __name__ == '__main__':
    ensure_data_files()
    # Initialize admin user if not exists
    from init_admin import init_admin
    init_admin()
    app.run(host='0.0.0.0', port=5000, debug=True)