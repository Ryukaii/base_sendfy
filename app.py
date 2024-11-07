import os
import json
import uuid
import fcntl
import logging
import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models.users import User
from celery_worker import send_sms_task

app = Flask(__name__)
app.secret_key = os.urandom(24)

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

def ensure_data_files():
    if not os.path.exists('data'):
        os.makedirs('data')
    for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, TRANSACTIONS_FILE, SMS_HISTORY_FILE]:
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump([], f)

def handle_api_error(message, status_code=400):
    return jsonify({
        'success': False,
        'error': message
    }), status_code

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

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
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
            
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.get_by_username(username):
            flash('Username already exists', 'danger')
            return render_template('register.html')
            
        user = User.create(username=username, password=password)
        if user:
            login_user(user)
            flash('Account created successfully!', 'success')
            return redirect(url_for('index'))
            
        flash('Error creating user', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'success')
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

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    try:
        # Get only campaigns for current user
        with open(CAMPAIGNS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_campaigns = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        user_campaigns = [c for c in all_campaigns if c.get('user_id') == current_user.id]
        return jsonify(user_campaigns)
    except Exception as e:
        logger.error(f"Error loading campaigns: {str(e)}")
        return handle_api_error('Failed to load campaigns')

@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['name', 'integration_id', 'event_type', 'message_template']):
            return handle_api_error('Missing required fields')
            
        # Verify integration belongs to user
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            integration = next((i for i in integrations if i['id'] == data['integration_id']), None)
            
        if not integration or integration.get('user_id') != current_user.id:
            return handle_api_error('Invalid integration ID')
            
        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
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

@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        # Get only integrations for current user
        with open(INTEGRATIONS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_integrations = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        user_integrations = [i for i in all_integrations if i.get('user_id') == current_user.id]
        return jsonify(user_integrations)
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return handle_api_error('Failed to load integrations')

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

# Admin routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.get_all()
    stats = {
        'total_users': len(users),
        'total_sms': sum(user.credits for user in users),
        'active_campaigns': 0,  # Will be implemented later
        'success_rate': 0  # Will be implemented later
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
        'description': 'Page not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error={
        'code': 500,
        'description': 'Internal server error'
    }), 500

if __name__ == '__main__':
    ensure_data_files()
    app.run(host='0.0.0.0', port=5000, debug=True)
