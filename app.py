import json
import os
import uuid
import datetime
import re
import logging
import fcntl
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, make_response
from celery_worker import send_sms_task
from collections import Counter
from functools import wraps
import traceback
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from models.users import User

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'info'

DATA_DIR = 'data'
INTEGRATIONS_FILE = os.path.join(DATA_DIR, 'integrations.json')
CAMPAIGNS_FILE = os.path.join(DATA_DIR, 'campaigns.json')
SMS_HISTORY_FILE = os.path.join(DATA_DIR, 'sms_history.json')
TRANSACTIONS_FILE = os.path.join(DATA_DIR, 'transactions.json')

def ensure_data_directory():
    try:
        os.makedirs(DATA_DIR, mode=0o755, exist_ok=True)
        logger.info(f"Data directory {DATA_DIR} exists and is accessible")
    except Exception as e:
        logger.critical(f"Failed to create/access data directory: {str(e)}")
        raise

def initialize_json_file(filepath, initial_data=None):
    try:
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(initial_data if initial_data is not None else [], f, indent=2)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.chmod(filepath, 0o644)
            logger.info(f"Initialized JSON file: {filepath}")
        return True
    except Exception as e:
        logger.error(f"Error initializing JSON file {filepath}: {str(e)}\n{traceback.format_exc()}")
        return False

def handle_api_error(error_message, status_code=400):
    """Helper function to handle API errors consistently"""
    logger.error(f"API Error: {error_message}")
    response = jsonify({
        'success': False,
        'message': error_message
    })
    response.status_code = status_code
    return response

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            if request.is_json:
                return handle_api_error('Acesso restrito a administradores', 403)
            flash('Você precisa ter privilégios de administrador para acessar esta página.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def init_app(app):
    ensure_data_directory()
    for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE, TRANSACTIONS_FILE]:
        initialize_json_file(file_path)
    initialize_json_file('data/users.json', [])

init_app(app)

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
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))
            
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.get_by_username(username):
            flash('Este nome de usuário já está em uso.', 'danger')
            return render_template('register.html')
            
        user = User.create(username=username, password=password)
        if user:
            flash('Conta criada com sucesso! Você pode fazer login agora.', 'success')
            return redirect(url_for('login'))
            
        flash('Erro ao criar conta. Por favor, tente novamente.', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.get_all()
    sms_history = []
    campaigns = []
    
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            sms_history = json.load(f)
    except:
        pass
        
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
    except:
        pass
    
    success_messages = sum(1 for msg in sms_history if msg.get('status') == 'success')
    total_messages = len(sms_history)
    success_rate = round((success_messages / total_messages * 100) if total_messages > 0 else 0, 1)
    
    stats = {
        'total_users': len(users),
        'total_sms': total_messages,
        'active_campaigns': len(campaigns),
        'success_rate': success_rate
    }
    
    return render_template('admin/dashboard.html', stats=stats, users=users)

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/campaigns')
@login_required
def campaigns():
    return render_template('campaigns.html')

@app.route('/sms')
@login_required
def sms():
    return render_template('sms.html')

@app.route('/integrations')
@login_required
def integrations():
    return render_template('integrations.html')

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@app.route('/sms-history')
@login_required
def sms_history():
    return render_template('sms_history.html')

@app.route('/campaign-performance')
@login_required
def campaign_performance():
    return render_template('campaign_performance.html')

# API Routes
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
            is_admin=data.get('is_admin', False)
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
        if str(current_user.id) == user_id:
            return handle_api_error('Cannot delete your own account')
            
        # Implementation of user deletion would go here
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        })
        
    except Exception as e:
        return handle_api_error(f'Error deleting user: {str(e)}')

@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message']):
            return handle_api_error('Phone number and message are required')
        
        # Queue the SMS task
        task = send_sms_task.delay(
            phone=data['phone'],
            message=data['message'],
            event_type='manual'
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS enviado com sucesso'
        })
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return handle_api_error('Erro ao enviar SMS. Por favor, tente novamente.')

@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return jsonify(integrations)
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
            integrations = [i for i in integrations if i['id'] != integration_id]
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

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            campaigns = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return jsonify(campaigns)
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
            
        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
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
            campaigns = [c for c in campaigns if c['id'] != campaign_id]
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

@app.errorhandler(404)
def not_found_error(error):
    if request.is_json:
        return handle_api_error('Resource not found', 404)
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    if request.is_json:
        return handle_api_error('Internal server error', 500)
    return render_template('error.html', error='Internal server error'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
