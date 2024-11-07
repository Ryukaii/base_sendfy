import os
import json
import uuid
import fcntl
import logging
import datetime
import re
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from models.users import User
from celery_worker import celery, send_sms_task

# File paths
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

app = Flask(__name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)
app.secret_key = os.urandom(24)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Setup login manager with improved configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'warning'

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Celery
app.config.update(
    CELERY_BROKER_URL=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    CELERY_RESULT_BACKEND=os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
)
celery.conf.update(app.config)

# Constants
INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
TRANSACTIONS_FILE = 'data/transactions.json'
SMS_HISTORY_FILE = 'data/sms_history.json'
SCHEDULED_SMS_FILE = 'data/scheduled_sms.json'

def ensure_data_files():
    if not os.path.exists('data'):
        os.makedirs('data')
    for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, TRANSACTIONS_FILE, SMS_HISTORY_FILE, SCHEDULED_SMS_FILE]:
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump([], f)

# Call at startup
ensure_data_files()

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

def calculate_delay_seconds(amount, unit):
    multipliers = {
        'minutes': 60,
        'hours': 3600,
        'days': 86400
    }
    return amount * multipliers.get(unit, 60)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error='Página não encontrada'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error='Erro interno do servidor'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f'Unhandled exception: {str(e)}')
    return render_template('error.html', error='Erro inesperado'), 500

# Routes
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
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
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
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

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.get_all()
    
    with open(SMS_HISTORY_FILE, 'r') as f:
        sms_history = json.load(f)
    
    with open(CAMPAIGNS_FILE, 'r') as f:
        campaigns = json.load(f)
    
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

@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message']):
            return handle_api_error('Missing required fields')
            
        phone = data['phone']
        message = data['message']
        
        # Format phone number
        if not phone.startswith('+55'):
            phone = f'+55{phone}'
            
        # Check credits
        if not current_user.has_sufficient_credits(1):
            return handle_api_error('Insufficient credits')
            
        # Deduct credit
        if not current_user.deduct_credits(1):
            return handle_api_error('Failed to deduct credits')
            
        try:
            # Queue SMS task
            task = send_sms_task.delay(
                phone=phone,
                message=message,
                campaign_id=None,
                event_type='manual'
            )
            
            # Log to history
            with open(SMS_HISTORY_FILE, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                history = json.load(f)
                history.append({
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'phone': phone,
                    'message': message,
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
                'message': 'SMS queued successfully',
                'task_id': task.id
            })
            
        except Exception as e:
            # Refund credit on error
            current_user.add_credits(1)
            logger.error(f"Error queuing SMS: {str(e)}")
            return handle_api_error('Failed to queue SMS')
            
    except Exception as e:
        logger.error(f"Error in send_sms: {str(e)}")
        return handle_api_error('Internal server error')

@app.route('/webhook/<path:webhook_path>', methods=['POST'])
def webhook_handler(webhook_path):
    try:
        webhook_data = request.get_json()
        logger.debug(f"Received webhook data: {webhook_data}")
        
        # Find integration with matching webhook URL
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            integration = next((i for i in integrations if webhook_path in i.get('webhook_url', '')), None)
        
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
        
        # Find matching campaigns
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
        
        # Format customer name for URL
        url_safe_name = re.sub(r'[^a-zA-Z0-9]', '', customer_data.get('name', ''))
        
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
        for campaign in matching_campaigns:
            try:
                for message in campaign.get('messages', []):
                    if not message.get('enabled', True):
                        continue
                        
                    if not user.has_sufficient_credits(1):
                        logger.warning(f"User {user.id} has insufficient credits")
                        continue
                    
                    # Format template variables
                    template = message['template']
                    full_name = customer_data.get('name', '')
                    first_name = full_name.split()[0] if full_name else ''
                    
                    # Format phone
                    phone = customer_data.get('phone', '')
                    if not phone.startswith('+55'):
                        phone = f'+55{phone}'
                        
                    # Replace template variables
                    formatted_message = template
                    formatted_message = formatted_message.replace('{customer.first_name}', first_name)
                    formatted_message = formatted_message.replace('{total_price}', webhook_data.get('total_price', ''))
                    
                    # Add PIX link for pending status
                    if status == 'pending':
                        # Use request.host_url for the domain
                        payment_url = f"{request.host_url.rstrip('/')}/payment/{url_safe_name}/{transaction_id}"
                        formatted_message = formatted_message.replace('{link_pix}', payment_url)
                    
                    # Calculate delay
                    delay = message.get('delay', {})
                    delay_seconds = calculate_delay_seconds(
                        amount=delay.get('amount', 0),
                        unit=delay.get('unit', 'minutes')
                    )
                    
                    # Schedule SMS
                    scheduled_time = (
                        datetime.datetime.now() + 
                        datetime.timedelta(seconds=delay_seconds)
                    ).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Save scheduled SMS
                    scheduled_sms = {
                        'id': str(uuid.uuid4()),
                        'phone': phone,
                        'message': formatted_message,
                        'send_at': scheduled_time,
                        'campaign_id': campaign['id'],
                        'user_id': user.id,
                        'status': 'pending'
                    }
                    
                    with open(SCHEDULED_SMS_FILE, 'r+') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        scheduled_messages = json.load(f)
                        scheduled_messages.append(scheduled_sms)
                        f.seek(0)
                        json.dump(scheduled_messages, f, indent=2)
                        f.truncate()
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
                    # Deduct credit and queue SMS
                    if user.deduct_credits(1):
                        logger.info(f"Queuing SMS to {phone}: {formatted_message}")
                        send_sms_task.apply_async(
                            args=[phone, formatted_message, campaign['event_type']],
                            countdown=delay_seconds
                        )
                        success_count += 1
                        logger.info(f"SMS queued for campaign {campaign['id']}")
                    
                    # Add to history
                    with open(SMS_HISTORY_FILE, 'r+') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        history = json.load(f)
                        history.append({
                            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'phone': phone,
                            'message': formatted_message,
                            'type': 'campaign',
                            'status': 'scheduled',
                            'user_id': user.id,
                            'campaign_id': campaign['id']
                        })
                        f.seek(0)
                        json.dump(history, f, indent=2)
                        f.truncate()
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
            except Exception as e:
                logger.error(f"Error processing campaign {campaign['id']}: {str(e)}")
                user.add_credits(1)  # Refund credit on error
                continue
        
        return jsonify({
            'success': True,
            'message': f'Webhook processed successfully. Queued {success_count} messages.',
            'transaction_id': transaction_id
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return handle_api_error('Error processing webhook')

@app.route('/sms')
@login_required
def sms_page():
    return render_template('sms.html')

@app.route('/integrations')
@login_required
def integrations_page():
    return render_template('integrations.html')

@app.route('/campaigns')
@login_required
def campaigns_page():
    return render_template('campaigns.html')

@app.route('/sms-history')
@login_required
def sms_history_page():
    with open(SMS_HISTORY_FILE, 'r') as f:
        history = json.load(f)
    return render_template('sms_history.html', sms_history=history)

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
    app.run(host='0.0.0.0', port=5000, debug=True)