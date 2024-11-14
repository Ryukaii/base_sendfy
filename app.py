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
from models.database import db, User, Integration, Campaign, Transaction, SMSHistory
from celery_worker import send_sms_task

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database configuration and validation
if not os.getenv('DATABASE_URL'):
    raise ValueError("DATABASE_URL environment variable is not set")

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Initialize database tables and create admin user
with app.app_context():
    db.create_all()
    
    # Create default admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User()
        admin.username = 'admin'
        admin.set_password('admin123')
        admin.is_admin = True
        admin.credits = 100
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created")

# Setup login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required', 'danger')
            return render_template('login.html')
        
        logger.info(f"Login attempt for user: {username}")
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            logger.info("Login successful")
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
            
        logger.warning("Invalid login attempt")
        flash('Invalid username or password', 'danger')
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required', 'danger')
            return render_template('register.html')
            
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('register.html')
            
        user = User()
        user.username = username
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Account created successfully!', 'success')
        return redirect(url_for('index'))
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

# Admin routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        stats = {
            'total_users': User.query.count(),
            'total_sms': SMSHistory.query.count(),
            'active_campaigns': Campaign.query.count(),
            'success_rate': calculate_success_rate()
        }
        return render_template('admin/dashboard.html', stats=stats, users=User.query.all())
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}")
        return render_template('error.html', error='Error loading admin dashboard')

def calculate_success_rate():
    try:
        total = SMSHistory.query.count()
        if total == 0:
            return 0
        success_count = SMSHistory.query.filter_by(status='success').count()
        return round((success_count / total) * 100)
    except Exception:
        return 0

# Main routes
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    try:
        data = request.get_json()
        if not all(k in data for k in ['username', 'password']):
            return handle_api_error('Missing required fields')
        
        existing_user = User.query.filter_by(username=data['username']).first()
        if existing_user:
            return handle_api_error('Username already exists')
            
        user = User()
        user.username = data['username']
        user.set_password(str(data['password']))
        user.is_admin = data.get('is_admin', False)
        user.credits = int(data.get('credits', 0))
        
        db.session.add(user)
        db.session.commit()
            
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
            
        user = User.query.get(user_id)
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
        if current_user.id == int(user_id):
            return handle_api_error('Cannot delete your own account')
            
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'User deleted successfully'
            })
        return handle_api_error('User not found')
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return handle_api_error('Failed to delete user')

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
        sms_history = SMSHistory(
            phone=phone,
            message=data['message'],
            type='manual',
            status='pending',
            user_id=current_user.id
        )
        db.session.add(sms_history)
        db.session.commit()
        
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
    user_history = SMSHistory.query.filter_by(user_id=current_user.id).order_by(SMSHistory.created_at.desc()).all()
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
        user_campaigns = Campaign.query.filter_by(user_id=current_user.id).all()
        return jsonify([c.to_dict() for c in user_campaigns])
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
        integration = Integration.query.filter_by(id=data['integration_id'], user_id=current_user.id).first()
        if not integration:
            return handle_api_error('Invalid integration ID')
            
        campaign = Campaign()
        campaign.name = data['name']
        campaign.integration_id = data['integration_id']
        campaign.event_type = data['event_type']
        campaign.message_template = data['message_template']
        campaign.user_id = current_user.id
        
        db.session.add(campaign)
        db.session.commit()
            
        return jsonify({
            'success': True,
            'message': 'Campaign created successfully',
            'campaign': campaign.to_dict()
        })
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        return handle_api_error('Failed to create campaign')

@app.route('/api/campaigns/<campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    try:
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first()
        if campaign:
            db.session.delete(campaign)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Campaign deleted successfully'
            })
        return handle_api_error('Campaign not found')
    except Exception as e:
        logger.error(f"Error deleting campaign: {str(e)}")
        return handle_api_error('Failed to delete campaign')

@app.route('/api/integrations', methods=['GET'])
@login_required
def get_integrations():
    try:
        # Get only integrations for current user
        user_integrations = Integration.query.filter_by(user_id=current_user.id).all()
        return jsonify([i.to_dict() for i in user_integrations])
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
            
        integration = Integration()
        integration.name = data['name']
        integration.webhook_url = f"/webhook/{str(uuid.uuid4())}"
        integration.user_id = current_user.id
        
        db.session.add(integration)
        db.session.commit()
            
        return jsonify({
            'success': True,
            'message': 'Integration created successfully',
            'integration': integration.to_dict()
        })
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return handle_api_error('Failed to create integration')

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
@login_required
def delete_integration(integration_id):
    try:
        integration = Integration.query.filter_by(id=integration_id, user_id=current_user.id).first()
        if integration:
            db.session.delete(integration)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Integration deleted successfully'
            })
        return handle_api_error('Integration not found')
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return handle_api_error('Failed to delete integration')

@app.route('/webhook/<path:webhook_path>', methods=['POST'])
def webhook_handler(webhook_path):
    try:
        webhook_data = request.get_json()
        logger.debug(f"Received webhook data: {webhook_data}")
        
        # Find integration with matching webhook URL
        integration = Integration.query.filter(Integration.webhook_url.like(f"%{webhook_path}%")).first()
        if not integration:
            logger.error(f"No integration found for webhook path: {webhook_path}")
            return handle_api_error('Integration not found', 404)
            
        # Get user who owns the integration
        user = User.query.get(integration.user_id)
        if not user:
            logger.error(f"User not found for integration {integration.id}")
            return handle_api_error('Integration owner not found', 404)
            
        # Load campaigns for this integration
        campaigns = Campaign.query.filter_by(integration_id=integration.id, user_id=user.id).all()
        
        # Get status from webhook data
        status = webhook_data.get('status', 'pending').lower()
        
        # Find matching campaigns for this status
        matching_campaigns = [
            c for c in campaigns 
            if c.event_type.lower() == status
        ]
        
        if not matching_campaigns:
            logger.warning(f"No campaigns found for integration {integration.id} and status {status}")
            return jsonify({
                'success': True,
                'message': 'No matching campaigns found for this event type'
            })
        
        # Create transaction record
        transaction_id = str(uuid.uuid4())[:8]
        customer_data = webhook_data.get('customer', {})
        
        transaction = Transaction(
            transaction_id=transaction_id,
            customer_name=customer_data.get('name', ''),
            customer_phone=customer_data.get('phone', ''),
            customer_email=customer_data.get('email', ''),
            product_name=webhook_data.get('product_name', ''),
            total_price=webhook_data.get('total_price', '0.00'),
            pix_code=webhook_data.get('pix_code', ''),
            status=status
        )
        db.session.add(transaction)
        db.session.commit()

        success_count = 0
        # Send SMS for each matching campaign
        for campaign in matching_campaigns:
            try:
                if not user.has_sufficient_credits(1):
                    logger.warning(f"User {user.id} has insufficient credits for campaign {campaign.id}")
                    continue
                    
                # Get first name
                full_name = customer_data.get('name', '')
                first_name = full_name.split()[0] if full_name else ''
                
                # Format phone number
                phone = customer_data.get('phone', '')
                if not phone.startswith('+55'):
                    phone = f'+55{phone}'
                
                # Format message
                message = campaign.message_template
                message = message.replace('{customer.first_name}', first_name)
                message = message.replace('{total_price}', webhook_data.get('total_price', ''))
                
                # Add PIX link only for pending status
                if status == 'pending':
                    message = message.replace('{link_pix}', f"{request.host_url}payment/{customer_data.get('name', 'cliente')}/{transaction_id}")
                
                # Calculate delay in seconds
                delay_seconds = 0
                if campaign.delay_amount and campaign.delay_unit:
                    if campaign.delay_unit == 'minutes':
                        delay_seconds = campaign.delay_amount * 60
                    elif campaign.delay_unit == 'hours':
                        delay_seconds = campaign.delay_amount * 3600
                    elif campaign.delay_unit == 'days':
                        delay_seconds = campaign.delay_amount * 86400
                
                # Deduct credit and send SMS
                if user.deduct_credits(1):
                    # Add delay to task
                    send_sms_task.apply_async(
                        args=[phone, message, campaign.event_type],
                        countdown=delay_seconds
                    )
                    success_count += 1
                    logger.info(f"SMS queued for campaign {campaign.id}")
                
            except Exception as e:
                logger.error(f"Error sending SMS for campaign {campaign.id}: {str(e)}")
                # Refund credit if SMS failed to queue
                user.add_credits(1)

        return jsonify({
            'success': True,
            'message': f'Webhook processed successfully. Sent {success_count} messages',
            'transaction_id': transaction_id
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return handle_api_error('Error processing webhook')

@app.route('/payment/<transaction_id>')
def payment_page(transaction_id):
    try:
        transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
        if not transaction:
            return render_template('error.html', error='Transação não encontrada')
            
        return render_template('payment.html', 
            customer_name=transaction.customer_name,
            pix_code=transaction.pix_code
        )
    except Exception as e:
        logger.error(f"Error loading payment page: {str(e)}")
        return render_template('error.html', error='Error loading payment page')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)