import json
import os
import uuid
import datetime
import re
import logging
import fcntl
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, make_response, session
from celery_worker import send_sms_task
from collections import Counter
from functools import wraps
import traceback
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from models.users import User
import secrets
from datetime import timedelta

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
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # For "remember me"
app.config['SESSION_PROTECTION'] = 'strong'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
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
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'message': 'Admin privileges required'
            }), 403
        return f(*args, **kwargs)
    return decorated_function

def init_app(app):
    ensure_data_directory()
    for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, SMS_HISTORY_FILE, TRANSACTIONS_FILE]:
        initialize_json_file(file_path)
    initialize_json_file('data/users.json', [])

# Initialize app on startup
init_app(app)

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        logger.error(f"Error loading campaigns: {str(e)}")
        return jsonify([])

@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    try:
        data = request.get_json()
        campaigns = []
        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                campaigns = json.load(f)
        except:
            pass
            
        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
            'created_at': datetime.datetime.now().isoformat()
        }
        campaigns.append(campaign)
        
        with open(CAMPAIGNS_FILE, 'w') as f:
            json.dump(campaigns, f, indent=2)
            
        return jsonify(campaign)
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        return jsonify({
            'error': 'Failed to create campaign'
        }), 500

@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return jsonify([])

@app.route('/api/integrations', methods=['POST'])
@login_required
def create_integration():
    try:
        data = request.get_json()
        integrations = []
        try:
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
        except:
            pass
            
        integration = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'webhook_url': f"/webhook/{str(uuid.uuid4())}",
            'created_at': datetime.datetime.now().isoformat()
        }
        integrations.append(integration)
        
        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)
            
        return jsonify(integration)
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return jsonify({
            'error': 'Failed to create integration'
        }), 500

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
@login_required
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            
        integrations = [i for i in integrations if i['id'] != integration_id]
        
        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)
            
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return jsonify({
            'error': 'Failed to delete integration'
        }), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password or not confirm_password:
            return jsonify({
                'success': False,
                'message': 'All fields are required'
            }), 400
            
        if password != confirm_password:
            return jsonify({
                'success': False,
                'message': 'Passwords do not match'
            }), 400
            
        if User.get_by_username(username):
            return jsonify({
                'success': False,
                'message': 'Username already exists'
            }), 400
            
        user = User.create(username, password)
        if user:
            login_user(user)
            return jsonify({
                'success': True,
                'redirect': url_for('index')
            })
            
        return jsonify({
            'success': False,
            'message': 'Failed to create account'
        }), 500
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return jsonify({'success': True, 'redirect': url_for('index')})
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            return jsonify({
                'success': False,
                'message': 'Username and password are required'
            }), 400
            
        user = User.get_by_username(username)
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            if remember:
                session.permanent = True
            
            return jsonify({
                'success': True,
                'redirect': request.args.get('next') or url_for('index')
            })
            
        return jsonify({
            'success': False,
            'message': 'Invalid username or password'
        }), 401
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/reset-password-request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.get_by_username(username)
        
        if user:
            token = secrets.token_urlsafe(32)
            user.set_reset_token(token)
            flash(f'Password reset instructions have been sent to your email.', 'info')
            
        return jsonify({
            'success': True,
            'message': 'If an account exists with that username, you will receive reset instructions.'
        })
    
    return render_template('reset_password_request.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    user = User.verify_reset_token(token)
    if not user:
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('reset_password_request'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        if user.reset_password(password):
            flash('Your password has been reset.', 'success')
            return jsonify({
                'success': True,
                'redirect': url_for('login')
            })
        
        return jsonify({
            'success': False,
            'message': 'Failed to reset password. Please try again.'
        }), 400
    
    return render_template('reset_password.html')

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    try:
        users = User.get_all()
        sms_history = []
        campaigns = []
        
        try:
            with open(SMS_HISTORY_FILE, 'r') as f:
                sms_history = json.load(f)
        except Exception as e:
            logger.error(f"Error loading SMS history: {str(e)}")
            
        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                campaigns = json.load(f)
        except Exception as e:
            logger.error(f"Error loading campaigns: {str(e)}")
        
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
    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error loading admin dashboard'
        }), 500

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
            return jsonify({
                'success': False,
                'message': 'Username and password are required'
            }), 400
            
        user = User.create(username, password, is_admin)
        if not user:
            return jsonify({
                'success': False,
                'message': 'Username already exists'
            }), 400
            
        return jsonify({
            'success': True,
            'message': 'User created successfully'
        })
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    try:
        users = User.get_all()
        admin_users = [u for u in users if u.is_admin]
        user_to_delete = User.get(user_id)
        
        if not user_to_delete:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
            
        if user_to_delete.is_admin and len(admin_users) <= 1:
            return jsonify({
                'success': False,
                'message': 'Cannot delete the last admin user'
            }), 400
            
        if User.delete(user_id):
            return jsonify({
                'success': True,
                'message': 'User deleted successfully'
            })
        
        return jsonify({
            'success': False,
            'message': 'Failed to delete user'
        }), 500
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

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
            return jsonify({
                'success': False,
                'message': 'Phone number and message are required'
            }), 400
            
        task = send_sms_task.delay(
            phone=phone,
            message=message,
            event_type='manual'
        )
        
        return jsonify({
            'success': True,
            'message': 'SMS queued successfully'
        })
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error sending SMS. Please try again.'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
