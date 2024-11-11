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
    os.makedirs('data', exist_ok=True)
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
    ensure_data_files()
    return render_template('index.html')

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

# Protected Routes
@app.route('/sms')
@login_required
def sms_page():
    ensure_data_files()
    return render_template('sms.html')

@app.route('/integrations')
@login_required
def integrations_page():
    ensure_data_files()
    return render_template('integrations.html')

@app.route('/campaigns')
@login_required
def campaigns_page():
    ensure_data_files()
    return render_template('campaigns.html')

@app.route('/sms-history')
@login_required
def sms_history():
    ensure_data_files()
    with open(SMS_HISTORY_FILE, 'r') as f:
        history = json.load(f)
    # Filter history for current user
    user_history = [sms for sms in history if sms.get('user_id') == current_user.id]
    return render_template('sms_history.html', sms_history=user_history)

# Admin Routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    ensure_data_files()
    users = User.get_all()
    
    # Calculate general stats
    total_users = len(users)
    total_sms = sum(user.credits for user in users)
    
    # Calculate SMS statistics
    with open(SMS_HISTORY_FILE, 'r') as f:
        history = json.load(f)
        
    total_messages = len(history) or 1  # Avoid division by zero
    success_messages = len([sms for sms in history if sms.get('status') == 'success'])
    success_rate = int((success_messages / total_messages * 100))
    
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

# Integration API Routes
@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        ensure_data_files()
        with open(INTEGRATIONS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_integrations = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        # Filter integrations for current user
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
        
        ensure_data_files()
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
        ensure_data_files()
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
            'message': 'Integração excluída com sucesso'
        })
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return handle_api_error('Falha ao excluir integração')

# Campaign API Routes
@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    try:
        ensure_data_files()
        with open(CAMPAIGNS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            all_campaigns = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        # Filter campaigns for current user
        user_campaigns = [c for c in all_campaigns if c.get('user_id') == current_user.id]
        return jsonify(user_campaigns)
    except Exception as e:
        logger.error(f"Error loading campaigns: {str(e)}")
        return handle_api_error('Falha ao carregar campanhas')

@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['name', 'integration_id', 'event_type', 'message_template']):
            return handle_api_error('Campos obrigatórios faltando')
            
        # Verify integration belongs to user
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            integration = next((i for i in integrations if i['id'] == data['integration_id']), None)
            
        if not integration or integration.get('user_id') != current_user.id:
            return handle_api_error('Integração inválida')
            
        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
            'user_id': current_user.id,
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        ensure_data_files()
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
            'message': 'Campanha criada com sucesso',
            'campaign': campaign
        })
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        return handle_api_error('Falha ao criar campanha')

@app.route('/api/campaigns/<campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    try:
        ensure_data_files()
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
            'message': 'Campanha excluída com sucesso'
        })
    except Exception as e:
        logger.error(f"Error deleting campaign: {str(e)}")
        return handle_api_error('Falha ao excluir campanha')

@app.route('/api/campaigns/<campaign_id>', methods=['PUT'])
@login_required
def update_campaign(campaign_id):
    try:
        data = request.get_json()
        if not data:
            return handle_api_error('Dados inválidos')
            
        ensure_data_files()
        with open(CAMPAIGNS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            campaigns = json.load(f)
            
            # Find campaign and verify ownership
            campaign = next((c for c in campaigns if c['id'] == campaign_id and c.get('user_id') == current_user.id), None)
            if not campaign:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return handle_api_error('Campanha não encontrada', 404)
            
            # Update fields
            campaign.update({
                'name': data.get('name', campaign['name']),
                'event_type': data.get('event_type', campaign['event_type']),
                'message_template': data.get('message_template', campaign['message_template'])
            })
            
            # Save changes
            f.seek(0)
            json.dump(campaigns, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return jsonify({
            'success': True,
            'message': 'Campanha atualizada com sucesso',
            'campaign': campaign
        })
    except Exception as e:
        logger.error(f"Error updating campaign: {str(e)}")
        return handle_api_error('Falha ao atualizar campanha')

# SMS API Routes
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
        phone = data['phone'].strip()
        phone = re.sub(r'[^\d+]', '', phone)  # Remove non-numeric chars except +
        
        # Add country code if missing
        if not phone.startswith('+55'):
            phone = f'+55{phone}'
            
        # Validate phone number format
        if not re.match(r'^\+55\d{10,11}$', phone):
            return handle_api_error('Número de telefone inválido. Use o formato: DDD + número')
            
        # Validate message length
        if len(data['message']) > 160:
            return handle_api_error('Mensagem muito longa (máximo 160 caracteres)')
            
        # Deduct credits before sending
        if not current_user.deduct_credits(1):
            return handle_api_error('Erro ao deduzir créditos')
            
        try:
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
            # Refund credit if SMS failed to queue
            current_user.add_credits(1)
            logger.error(f"Error queueing SMS: {str(e)}")
            return handle_api_error('Erro ao enviar SMS. Sistema temporariamente indisponível.')
            
    except Exception as e:
        logger.error(f"Error in send_sms endpoint: {str(e)}")
        return handle_api_error('Erro ao processar requisição')

# Error Handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='Página não encontrada'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error='Erro interno do servidor'), 500

if __name__ == '__main__':
    ensure_data_files()
    app.run(host='0.0.0.0', port=5000, debug=True)