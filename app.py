import json
import os
import uuid
import datetime
import re
import logging
import fcntl
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
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

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
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
    # Get statistics
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

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        is_admin = data.get('is_admin', False)
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400
            
        user = User.create(username, password, is_admin)
        if not user:
            return jsonify({'success': False, 'message': 'Username already exists'}), 400
            
        return jsonify({'success': True, 'message': 'User created successfully'})
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    try:
        # Prevent deleting the last admin user
        users = User.get_all()
        admin_users = [u for u in users if u.is_admin]
        user_to_delete = User.get(user_id)
        
        if not user_to_delete:
            return jsonify({'success': False, 'message': 'User not found'}), 404
            
        if user_to_delete.is_admin and len(admin_users) <= 1:
            return jsonify({
                'success': False,
                'message': 'Cannot delete the last admin user'
            }), 400
            
        # Read users file
        with open('data/users.json', 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            users = [u for u in users if u['id'] != user_id]
            f.seek(0)
            json.dump(users, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
