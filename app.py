import os
import json
import uuid
import fcntl
import logging
import datetime
import re
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.users import User
from celery_worker import send_sms_task

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = datetime.timedelta(days=7)  # Set session lifetime

# Setup login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'warning'

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
TRANSACTIONS_FILE = 'data/transactions.json'
SMS_HISTORY_FILE = 'data/sms_history.json'

def ensure_data_files():
    """Ensure all required data files exist"""
    if not os.path.exists('data'):
        os.makedirs('data')
    for file_path in [INTEGRATIONS_FILE, CAMPAIGNS_FILE, TRANSACTIONS_FILE, SMS_HISTORY_FILE]:
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump([], f)

def handle_api_error(message, status_code=400):
    """Handle API errors consistently"""
    return jsonify({
        'success': False,
        'error': message
    }), status_code

def admin_required(f):
    """Decorator to require admin access"""
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

# Main Routes
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/sms')
@login_required
def sms_page():
    return render_template('sms.html')

@app.route('/sms-history')
@login_required
def sms_history():
    with open(SMS_HISTORY_FILE, 'r') as f:
        history = json.load(f)
    # Filter history for current user
    user_history = [sms for sms in history if sms.get('user_id') == current_user.id]
    return render_template('sms_history.html', sms_history=user_history)

@app.route('/campaigns')
@login_required
def campaigns_page():
    return render_template('campaigns.html')

@app.route('/integrations')
@login_required
def integrations_page():
    return render_template('integrations.html')

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.get_by_username(username)
        if user and user.check_password(password):
            login_user(user, remember=remember)
            session.permanent = True  # Use permanent session
            
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))
            
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
            session.permanent = True
            flash('Conta criada com sucesso!', 'success')
            return redirect(url_for('index'))
            
        flash('Erro ao criar usuário', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Você foi desconectado com sucesso', 'success')
    return redirect(url_for('login'))

# Admin Dashboard Routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.get_all()
    
    # Calculate general stats
    total_users = len(users)
    total_sms = sum(user.credits for user in users)
    
    # Calculate SMS statistics
    with open(SMS_HISTORY_FILE, 'r') as f:
        history = json.load(f)
        
    total_messages = len(history)
    success_messages = len([sms for sms in history if sms.get('status') == 'success'])
    success_rate = int((success_messages / total_messages * 100) if total_messages > 0 else 0)
    
    # Calculate campaign statistics
    with open(CAMPAIGNS_FILE, 'r') as f:
        campaigns = json.load(f)
    active_campaigns = len(campaigns)
    
    # Get recent activity
    recent_messages = sorted(
        history, 
        key=lambda x: x.get('timestamp', ''), 
        reverse=True
    )[:10]
    
    stats = {
        'total_users': total_users,
        'total_sms': total_sms,
        'active_campaigns': active_campaigns,
        'success_rate': success_rate,
        'total_messages': total_messages,
        'success_messages': success_messages
    }
    
    return render_template(
        'admin/dashboard.html',
        users=users,
        stats=stats,
        recent_activity=recent_messages
    )

# User Management API Routes
@app.route('/api/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    users = User.get_all()
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'is_admin': user.is_admin,
        'credits': user.credits
    } for user in users])

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['username', 'password']):
            return handle_api_error('Nome de usuário e senha são obrigatórios')
        
        user = User.create(
            username=data['username'],
            password=data['password'],
            is_admin=data.get('is_admin', False),
            credits=data.get('credits', 0)
        )
        
        if not user:
            return handle_api_error('Falha ao criar usuário')
            
        return jsonify({
            'success': True,
            'message': 'Usuário criado com sucesso'
        })
        
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return handle_api_error(f'Erro ao criar usuário: {str(e)}')

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    try:
        # Don't allow deleting self
        if current_user.id == user_id:
            return handle_api_error('Não é possível excluir sua própria conta')
        
        success = User.delete(user_id)
        if not success:
            return handle_api_error('Falha ao excluir usuário')
            
        return jsonify({
            'success': True,
            'message': 'Usuário excluído com sucesso'
        })
        
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return handle_api_error(f'Erro ao excluir usuário: {str(e)}')

@app.route('/api/users/<user_id>/credits', methods=['POST'])
@login_required
@admin_required
def manage_credits(user_id):
    try:
        data = request.get_json()
        if not data or 'amount' not in data or 'operation' not in data:
            return handle_api_error('Quantidade e operação são obrigatórios')
        
        user = User.get(user_id)
        if not user:
            return handle_api_error('Usuário não encontrado', 404)
            
        amount = int(data['amount'])
        operation = data['operation']
        
        if operation == 'add':
            success = user.add_credits(amount)
        elif operation == 'remove':
            success = user.deduct_credits(amount)
        else:
            return handle_api_error('Operação inválida')
            
        if not success:
            return handle_api_error('Falha ao atualizar créditos')
            
        return jsonify({
            'success': True,
            'message': f'Créditos {"adicionados" if operation == "add" else "removidos"} com sucesso',
            'new_credits': user.credits
        })
        
    except Exception as e:
        logger.error(f"Error managing credits: {str(e)}")
        return handle_api_error(f'Erro ao gerenciar créditos: {str(e)}')

# Error Handlers
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

# API Routes
@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        # Check user credits
        if not current_user.has_sufficient_credits(1):
            return handle_api_error('Créditos insuficientes para enviar SMS')
            
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message']):
            return handle_api_error('Número de telefone e mensagem são obrigatórios')
        
        # Format phone number
        phone = data['phone']
        if not phone.startswith('+55'):
            phone = f'+55{phone}'
            
        # Remove any non-numeric characters except +
        phone = re.sub(r'[^\d+]', '', phone)
        
        # Deduct credits before sending
        if not current_user.deduct_credits(1):
            return handle_api_error('Falha ao deduzir créditos')
            
        # Queue SMS task
        task = send_sms_task.delay(
            phone=phone,
            message=data['message'],
            event_type='manual'
        )
        
        # Log to SMS history
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

# Integration API Routes
@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_integrations = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        user_integrations = [i for i in all_integrations if i.get('user_id') == current_user.id]
        return jsonify(user_integrations)
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return handle_api_error('Falha ao carregar integrações')

@app.route('/api/integrations', methods=['POST'])
@login_required
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return handle_api_error('Nome da integração é obrigatório')
            
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
            'message': 'Integração criada com sucesso',
            'integration': integration
        })
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return handle_api_error('Falha ao criar integração')

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
@login_required
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            integrations = json.load(f)
            integrations = [i for i in integrations if i['id'] != integration_id or i.get('user_id') != current_user.id]
            f.seek(0)
            json.dump(integrations, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Integração excluída com sucesso'
        })
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return handle_api_error('Falha ao excluir integração')

if __name__ == '__main__':
    ensure_data_files()
    app.run(host='0.0.0.0', port=5000, debug=True)
