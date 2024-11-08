import os
import json
import logging
import signal
import sys
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_cors import CORS
from models.users import User
from celery_worker import send_sms_task, check_redis_connection

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}. Shutting down...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def create_app():
    """Application factory with improved configuration"""
    logger.info("Creating Flask application...")
    
    app = Flask(__name__)
    app.config['PROPAGATE_EXCEPTIONS'] = True
    CORS(app)
    
    # Check required environment variables
    if not os.environ.get('SMSDEV_API_KEY'):
        logger.error("SMSDEV_API_KEY environment variable is not set")
        sys.exit(1)
    
    # Secure configuration
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
    app.config.update(
        ENV='production',
        DEBUG=False,
        TESTING=False,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max file size
        PREFERRED_URL_SCHEME='https',
        SERVER_NAME=None,  # Allow all hostnames
        SESSION_COOKIE_SECURE=False,  # Required for Replit
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
        JSON_SORT_KEYS=False,
        JSON_AS_ASCII=False,
    )
    
    # Create required directories
    os.makedirs('data', exist_ok=True)
    for file_name in ['integrations.json', 'campaigns.json', 'transactions.json', 'sms_history.json', 'scheduled_sms.json']:
        file_path = f'data/{file_name}'
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                json.dump([], f)
            logger.info(f"Created file: {file_path}")
    
    # Apply proxy fix for Replit
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
        x_prefix=1
    )
    
    # Setup login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)
    
    # Request logging
    @app.before_request
    def log_request_info():
        if request.path != '/health':  # Skip logging health checks
            logger.debug('Headers: %s', dict(request.headers))
            logger.debug('Body: %s', request.get_data())
    
    @app.after_request
    def after_request(response):
        if request.path != '/health':  # Skip logging health checks
            logger.debug('Response: [%s] %s', response.status, response.get_data())
        response.headers['Server'] = 'SendFy'
        return response
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', error={'code': 404, 'description': 'Página não encontrada'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal error: {str(error)}", exc_info=True)
        return render_template('error.html', error={'code': 500, 'description': 'Erro interno do servidor'}), 500
    
    # Routes
    @app.route('/')
    @login_required
    def index():
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
                flash('Login realizado com sucesso!', 'success')
                return redirect(url_for('index'))
            
            flash('Usuário ou senha inválidos', 'danger')
        return render_template('login.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Você foi desconectado', 'success')
        return redirect(url_for('login'))
    
    @app.route('/sms')
    @login_required
    def sms():
        return render_template('sms.html')
    
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
                    'message': 'Telefone e mensagem são obrigatórios'
                }), 400
            
            if not current_user.has_sufficient_credits(1):
                return jsonify({
                    'success': False,
                    'message': 'Créditos insuficientes'
                }), 402
            
            # Deduct credit and send SMS
            if current_user.deduct_credits(1):
                task = send_sms_task.delay(phone, message)
                logger.info(f"SMS task created: {task.id}")
                return jsonify({
                    'success': True,
                    'message': 'SMS enviado com sucesso',
                    'task_id': task.id
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Erro ao deduzir créditos'
                }), 500
            
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'Erro ao enviar SMS: {str(e)}'
            }), 500
    
    @app.route('/health')
    def health_check():
        """Enhanced health check endpoint"""
        try:
            # Check Redis connection
            redis_healthy = check_redis_connection()
            
            # Check environment variables
            sms_api_key = os.environ.get('SMSDEV_API_KEY')
            
            health_status = {
                'status': 'healthy' if (redis_healthy and sms_api_key) else 'unhealthy',
                'redis': 'connected' if redis_healthy else 'disconnected',
                'sms_api': 'configured' if sms_api_key else 'not_configured',
                'environment': app.config['ENV'],
                'version': '1.0.0'
            }
            
            status_code = 200 if health_status['status'] == 'healthy' else 503
            return jsonify(health_status), status_code
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}", exc_info=True)
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 503
    
    logger.info("Flask application created successfully")
    return app

# Create the application instance
app = create_app()

if __name__ == '__main__':
    # Initialize admin user
    from init_admin import init_admin
    init_admin()
    
    # Start the application
    app.run(host='0.0.0.0', port=8080, debug=False)
