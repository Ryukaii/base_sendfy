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
                return handle_api_error('Admin privileges required', 403)
            flash('You need admin privileges to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def init_app(app):
    ensure_data_directory()
    for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE, TRANSACTIONS_FILE]:
        initialize_json_file(file_path)
    initialize_json_file('data/users.json', [])

# Initialize app on startup
init_app(app)

# API Routes
@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        logger.debug(f"Retrieved {len(integrations)} integrations")
        return jsonify(integrations)
    except Exception as e:
        logger.error(f"Error retrieving integrations: {str(e)}\n{traceback.format_exc()}")
        return handle_api_error('Failed to retrieve integrations', 500)

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
        logger.error(f"Error retrieving campaigns: {str(e)}")
        return handle_api_error('Failed to retrieve campaigns', 500)

@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    try:
        data = request.get_json()
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
        return handle_api_error('Failed to create campaign', 500)

@app.route('/api/integrations', methods=['POST'])
@login_required
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return handle_api_error('Integration name is required')
            
        name = data['name'].strip()
        if not name:
            return handle_api_error('Integration name cannot be empty')
            
        integration = {
            'id': str(uuid.uuid4()),
            'name': name,
            'webhook_url': f'/webhook/{str(uuid.uuid4())}',
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
            
        logger.info(f"Created new integration: {integration['id']}")
        return jsonify({
            'success': True,
            'message': 'Integration created successfully',
            'integration': integration
        })
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}\n{traceback.format_exc()}")
        return handle_api_error('Failed to create integration', 500)

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
@login_required
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            filtered_integrations = [i for i in integrations if i['id'] != integration_id]
            
            if len(filtered_integrations) == len(integrations):
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return handle_api_error('Integration not found', 404)
                
            f.seek(0)
            json.dump(filtered_integrations, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        logger.info(f"Deleted integration: {integration_id}")
        return jsonify({
            'success': True,
            'message': 'Integration deleted successfully'
        })
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}\n{traceback.format_exc()}")
        return handle_api_error('Failed to delete integration', 500)

# Error Handlers
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

# Regular routes (unchanged)
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

@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        data = request.get_json()
        phone = data.get('phone')
        message = data.get('message')
        
        if not phone or not message:
            return handle_api_error('Número de telefone e mensagem são obrigatórios')
            
        # Queue SMS sending task
        task = send_sms_task.delay(
            phone=phone,
            message=message,
            event_type='manual'
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS enviado com sucesso'
        })
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return handle_api_error('Erro ao enviar SMS. Por favor, tente novamente.', 500)

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
