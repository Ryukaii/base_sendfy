from flask import Flask, request, jsonify, render_template, flash, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models.users import User
from celery_worker import send_sms_task
import os
import json
import re
import logging
import fcntl
import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/app.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Constants
SMS_HISTORY_FILE = 'data/sms_history.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
TRANSACTIONS_FILE = 'data/transactions.json'

def handle_api_error(message, status_code=400):
    return jsonify({
        'success': False,
        'message': message
    }), status_code

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
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
            return redirect(url_for('index'))
            
        flash('Nome de usuário ou senha inválidos', 'danger')
    
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
            return redirect(url_for('register'))
            
        user = User.create(username=username, password=password)
        if user:
            flash('Conta criada com sucesso! Faça login para continuar.', 'success')
            return redirect(url_for('login'))
            
        flash('Erro ao criar conta', 'danger')
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/webhook/<integration_id>', methods=['POST'])
def webhook(integration_id):
    try:
        # Load campaigns
        if not os.path.exists(CAMPAIGNS_FILE):
            return jsonify({'success': False, 'message': 'No campaigns configured'}), 404
            
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
            
        # Find campaign for this integration
        campaign = next((c for c in campaigns if c['integration_id'] == integration_id), None)
        if not campaign:
            return jsonify({'success': False, 'message': 'Campaign not found'}), 404
            
        # Process webhook data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
            
        # Store transaction
        os.makedirs('data', exist_ok=True)
        if not os.path.exists(TRANSACTIONS_FILE):
            with open(TRANSACTIONS_FILE, 'w') as f:
                json.dump([], f)
                
        with open(TRANSACTIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                transactions = json.load(f)
            except json.JSONDecodeError:
                transactions = []
                
            transaction = {
                'id': data.get('transaction_id'),
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'campaign_id': campaign['id'],
                'integration_id': integration_id,
                'customer_name': data.get('customer_name'),
                'customer_phone': data.get('customer_phone'),
                'total_price': data.get('total_price'),
                'status': data.get('status', 'pending')
            }
            
            transactions.append(transaction)
            
            f.seek(0)
            json.dump(transactions, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        # Queue SMS messages
        for message in campaign['messages']:
            if message['enabled']:
                template = message['template']
                formatted_message = template.format(
                    customer_first_name=data.get('customer_name', '').split()[0],
                    total_price=data.get('total_price'),
                    link_pix=f"{request.host_url}payment/{transaction['id']}"
                )
                
                # Schedule SMS
                send_time = datetime.datetime.now() + datetime.timedelta(
                    **{message['delay']['unit']: message['delay']['amount']}
                )
                
                task = send_sms_task.apply_async(
                    args=[data['customer_phone'], formatted_message],
                    kwargs={'campaign_id': campaign['id'], 'event_type': 'webhook'},
                    eta=send_time
                )
                
                logger.info(f"Scheduled SMS task {task.id} for {send_time}")
                
        return jsonify({'success': True, 'message': 'Webhook processed successfully'})
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/send-sms', methods=['POST'])
@login_required
def send_sms():
    try:
        # Check SMS API key first
        if not os.environ.get('SMSDEV_API_KEY'):
            logger.error("SMSDEV_API_KEY not configured")
            return handle_api_error('Erro de configuração do serviço SMS')
            
        if not current_user.has_sufficient_credits(1):
            return handle_api_error('Créditos insuficientes para enviar SMS')
            
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message']):
            return handle_api_error('Número de telefone e mensagem são obrigatórios')
        
        phone = data['phone']
        if not phone.startswith('+55'):
            phone = f'+55{phone}'
            
        # Validate phone number format
        if not re.match(r'^\+55\d{10,11}$', phone):
            return handle_api_error('Formato de telefone inválido')
        
        if not current_user.deduct_credits(1):
            return handle_api_error('Falha ao deduzir créditos')
            
        # Log attempt before sending
        logger.info(f"Attempting to send SMS to {phone}")
        
        try:
            task = send_sms_task.delay(
                phone=phone,
                message=data['message'],
                event_type='manual'
            )
            
            # Ensure data directory exists
            os.makedirs('data', exist_ok=True)
            
            # Create SMS history file if it doesn't exist
            if not os.path.exists(SMS_HISTORY_FILE):
                with open(SMS_HISTORY_FILE, 'w') as f:
                    json.dump([], f)
            
            with open(SMS_HISTORY_FILE, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = []
                    
                history.append({
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'phone': phone,
                    'message': data['message'],
                    'type': 'manual',
                    'status': 'pending',
                    'user_id': current_user.id,
                    'task_id': task.id
                })
                
                f.seek(0)
                json.dump(history, f, indent=2)
                f.truncate()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
            return jsonify({
                'success': True,
                'message': 'SMS enviado com sucesso',
                'credits_remaining': current_user.credits,
                'task_id': task.id
            })
            
        except Exception as e:
            logger.error(f"Error queuing SMS task: {str(e)}")
            current_user.add_credits(1)  # Refund credits on error
            return handle_api_error('Erro ao enviar SMS. Por favor, tente novamente.')
            
    except Exception as e:
        logger.error(f"Unexpected error in send_sms: {str(e)}")
        return handle_api_error('Erro interno do servidor. Por favor, tente novamente.')

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error={'code': 404, 'description': 'Página não encontrada'}), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error={'code': 500, 'description': 'Erro interno do servidor'}), 500

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    # Initialize admin user if needed
    from init_admin import init_admin
    init_admin()
    
    # Run in production mode
    app.run(host='0.0.0.0', port=80)
