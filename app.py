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
from celery_worker import send_sms_task

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Setup login manager with improved configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'warning'

# Setup logging
logging.basicConfig(level=logging.DEBUG)  # Changed to DEBUG for more verbose logging
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

@app.route('/integrations')
@login_required
def integrations_page():
    return render_template('integrations.html')

@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_integrations = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        user_integrations = [
            integration for integration in all_integrations 
            if integration.get('user_id') == current_user.id
        ]
        return jsonify(user_integrations)
        
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return jsonify([])

@app.route('/api/integrations', methods=['POST'])
@login_required
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return handle_api_error('Integration name is required')
            
        integration = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'webhook_url': f"/webhook/{str(uuid.uuid4())}",
            'user_id': current_user.id,
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(INTEGRATIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            integrations.append(integration)
            f.seek(0)
            json.dump(integrations, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Integration created successfully',
            'integration': integration
        })
        
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return handle_api_error('Failed to create integration')

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
@login_required
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            
            integrations = [
                i for i in integrations 
                if i['id'] != integration_id or i.get('user_id') != current_user.id
            ]
            
            f.seek(0)
            json.dump(integrations, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Integration deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return handle_api_error('Failed to delete integration')

@app.route('/campaigns')
@login_required
def campaigns_page():
    return render_template('campaigns.html')

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_campaigns = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        user_campaigns = [
            campaign for campaign in all_campaigns 
            if campaign.get('user_id') == current_user.id
        ]
        return jsonify(user_campaigns)
        
    except Exception as e:
        logger.error(f"Error loading campaigns: {str(e)}")
        return jsonify([])

@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['name', 'integration_id', 'event_type', 'messages']):
            return handle_api_error('Missing required fields')
            
        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'messages': data['messages'],
            'user_id': current_user.id,
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(CAMPAIGNS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            campaigns = json.load(f)
            campaigns.append(campaign)
            f.seek(0)
            json.dump(campaigns, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Campaign created successfully',
            'campaign': campaign
        })
        
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        return handle_api_error('Failed to create campaign')

@app.route('/api/campaigns/<campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    try:
        with open(CAMPAIGNS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            campaigns = json.load(f)
            
            campaigns = [
                c for c in campaigns 
                if c['id'] != campaign_id or c.get('user_id') != current_user.id
            ]
            
            f.seek(0)
            json.dump(campaigns, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Campaign deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting campaign: {str(e)}")
        return handle_api_error('Failed to delete campaign')

@app.route('/sms')
@login_required
def sms():
    return render_template('sms.html')

@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        if not current_user.has_sufficient_credits(1):
            return handle_api_error('Créditos insuficientes para enviar SMS')
            
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message']):
            return handle_api_error('Número de telefone e mensagem são obrigatórios')
        
        phone = data['phone']
        if not phone.startswith('+55'):
            phone = f'+55{phone}'
        
        if not current_user.deduct_credits(1):
            return handle_api_error('Falha ao deduzir créditos')
            
        task = send_sms_task.delay(
            phone=phone,
            message=data['message'],
            event_type='manual'
        )
        
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
        current_user.add_credits(1)
        return handle_api_error('Erro ao enviar SMS. Por favor, tente novamente.')

@app.route('/sms-history')
@login_required
def sms_history():
    with open(SMS_HISTORY_FILE, 'r') as f:
        all_history = json.load(f)
        user_history = [
            sms for sms in all_history 
            if sms.get('user_id') == current_user.id
        ]
        user_history.reverse()
        
    return render_template('sms_history.html', sms_history=user_history)

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

@app.route('/webhook/<path:webhook_path>', methods=['POST'])
def webhook_handler(webhook_path):
    try:
        # Get webhook data with proper error handling
        webhook_data = request.get_json() or {}
        logger.debug(f"Received webhook data: {webhook_data}")

        # Extract and validate customer data
        customer_data = webhook_data.get('customer', {}) or {}
        if not customer_data:
            logger.warning("No customer data in webhook payload")

        # Validate required webhook data
        if not webhook_data or not all(k in webhook_data for k in ['status', 'customer']):
            logger.error("Missing required webhook data")
            return handle_api_error('Missing required webhook data')

        if not all(k in customer_data for k in ['name', 'phone']):
            logger.error("Missing required customer data")
            return handle_api_error('Missing customer information')

        # Find integration
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            integration = next((i for i in integrations if webhook_path in i.get('webhook_url', '')), None)
        
        if not integration:
            logger.error(f"No integration found for webhook path: {webhook_path}")
            return handle_api_error('Invalid webhook URL', 404)

        # Get user for this integration
        user = User.get(integration['user_id'])
        if not user:
            logger.error(f"No user found for integration: {integration['id']}")
            return handle_api_error('Integration owner not found')
            
        # Load campaigns with case-insensitive matching
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
            
        status = webhook_data.get('status', 'pending').lower()
        
        # Log campaign matching criteria
        logger.debug(f"Looking for campaigns matching: integration_id={integration['id']}, status={status}, user_id={user.id}")
        
        # Find matching campaigns with case-insensitive comparison
        matching_campaigns = [
            c for c in campaigns 
            if c['integration_id'] == integration['id']
            and c['event_type'].lower() == status
            and c['user_id'] == user.id
            and any(msg.get('enabled', True) for msg in c.get('messages', []))  # At least one enabled message
        ]
        
        logger.debug(f"Found {len(matching_campaigns)} matching campaigns")
        
        if not matching_campaigns:
            logger.warning(f"No matching campaigns found for integration {integration['id']} and status {status}")
            return jsonify({'success': True, 'message': 'No matching campaigns'})
            
        # Process matching campaigns
        for campaign in matching_campaigns:
            if not user.has_sufficient_credits(len(campaign['messages'])):
                logger.error(f"Insufficient credits for campaign {campaign['id']}")
                continue
                
            for message in campaign['messages']:
                if not message.get('enabled', True):
                    continue
                    
                # Prepare message with template variables
                template = message['template']
                data = {
                    'customer': customer_data,
                    'total_price': webhook_data.get('total_price', '0.00'),
                    'link_pix': webhook_data.get('link_pix', '')
                }
                
                try:
                    formatted_message = template.format(**data)
                    phone = customer_data['phone']
                    
                    if not phone.startswith('+55'):
                        phone = f'+55{phone}'
                        
                    # Calculate send time with delay
                    delay = message.get('delay', {'amount': 0, 'unit': 'minutes'})
                    send_at = datetime.datetime.now() + datetime.timedelta(
                        seconds=calculate_delay_seconds(delay['amount'], delay['unit'])
                    )
                    
                    # Store scheduled SMS
                    scheduled_sms = {
                        'id': str(uuid.uuid4()),
                        'phone': phone,
                        'message': formatted_message,
                        'send_at': send_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'campaign_id': campaign['id'],
                        'user_id': user.id,
                        'status': 'pending'
                    }
                    
                    with open(SCHEDULED_SMS_FILE, 'r+') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        scheduled = json.load(f)
                        scheduled.append(scheduled_sms)
                        f.seek(0)
                        json.dump(scheduled, f, indent=2)
                        f.truncate()
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
                    # Deduct credits and queue SMS task
                    if user.deduct_credits(1):
                        task = send_sms_task.apply_async(
                            args=[phone, formatted_message, "claro", campaign['id'], 'campaign'],
                            countdown=calculate_delay_seconds(delay['amount'], delay['unit'])
                        )
                    else:
                        logger.error(f"Failed to deduct credits for campaign {campaign['id']}")
                        
                except Exception as e:
                    logger.error(f"Error processing message template: {str(e)}")
                    continue
                    
        return jsonify({
            'success': True,
            'message': 'Webhook processed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return handle_api_error('Error processing webhook')
