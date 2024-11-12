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

def calculate_success_rate():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
            if not history:
                return 0
            success_count = sum(1 for sms in history if sms.get('status') == 'success')
            return round((success_count / len(history)) * 100)
    except Exception:
        return 0

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

# Admin routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        # Get system stats
        stats = {
            'total_users': len(User.get_all()),
            'total_sms': len(json.load(open(SMS_HISTORY_FILE))),
            'active_campaigns': len(json.load(open(CAMPAIGNS_FILE))),
            'success_rate': calculate_success_rate()
        }
        return render_template('admin/dashboard.html', stats=stats, users=User.get_all())
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}")
        return render_template('error.html', error='Error loading admin dashboard')

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    try:
        data = request.get_json()
        if not all(k in data for k in ['username', 'password']):
            return handle_api_error('Missing required fields')
            
        user = User.create(
            username=data['username'],
            password=data['password'],
            is_admin=data.get('is_admin', False),
            credits=int(data.get('credits', 0))
        )
        
        if not user:
            return handle_api_error('Username already exists')
            
        return jsonify({
            'success': True,
            'message': 'User created successfully'
        })
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return handle_api_error('Failed to create user')

@app.route('/api/users/<user_id>/credits', methods=['POST'])
@admin_required
def manage_credits(user_id):
    try:
        data = request.get_json()
        if not all(k in data for k in ['amount', 'operation']):
            return handle_api_error('Missing required fields')
            
        user = User.get(user_id)
        if not user:
            return handle_api_error('User not found')
            
        amount = int(data['amount'])
        if data['operation'] == 'add':
            success = user.add_credits(amount)
        else:
            success = user.deduct_credits(amount)
            
        if not success:
            return handle_api_error('Failed to update credits')
            
        return jsonify({
            'success': True,
            'message': 'Credits updated successfully'
        })
    except Exception as e:
        logger.error(f"Error managing credits: {str(e)}")
        return handle_api_error('Failed to update credits')

@app.route('/api/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    try:
        if current_user.id == user_id:
            return handle_api_error('Cannot delete your own account')
            
        if User.delete(user_id):
            return jsonify({
                'success': True,
                'message': 'User deleted successfully'
            })
        return handle_api_error('Failed to delete user')
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return handle_api_error('Failed to delete user')

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

@app.route('/integrations-and-campaigns')
@login_required
def integrations_and_campaigns():
    return render_template('integrations_and_campaigns.html')

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

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
@login_required
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            
            # Only delete if integration belongs to current user
            integrations = [i for i in integrations if i['id'] != integration_id or i.get('user_id') != current_user.id]
            
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

@app.route('/api/campaigns/<campaign_id>', methods=['PUT'])
@login_required
def update_campaign(campaign_id):
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['name', 'event_type', 'message_template']):
            return handle_api_error('Missing required fields')
            
        with open(CAMPAIGNS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            campaigns = json.load(f)
            
            # Find and update campaign if it belongs to current user
            campaign = next((c for c in campaigns if c['id'] == campaign_id and c.get('user_id') == current_user.id), None)
            if not campaign:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return handle_api_error('Campaign not found')
            
            # Update fields
            campaign['name'] = data['name']
            campaign['event_type'] = data['event_type']
            campaign['message_template'] = data['message_template']
            
            f.seek(0)
            json.dump(campaigns, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Campaign updated successfully',
            'campaign': campaign
        })
    except Exception as e:
        logger.error(f"Error updating campaign: {str(e)}")
        return handle_api_error('Failed to update campaign')

@app.route('/api/campaigns/<campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    try:
        with open(CAMPAIGNS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            campaigns = json.load(f)
            
            # Only delete if campaign belongs to current user
            campaigns = [c for c in campaigns if c['id'] != campaign_id or c.get('user_id') != current_user.id]
            
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
    app.run(host='0.0.0.0', port=5000, debug=True)
