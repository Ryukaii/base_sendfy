import os
import logging
import redis
import signal
import sys
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
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

def check_redis_connection():
    """Verify Redis connection with improved error handling"""
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    try:
        redis_client = redis.from_url(
            redis_url,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
            decode_responses=True
        )
        redis_client.ping()
        logger.info("Redis connection successful")
        return True
    except redis.ConnectionError as e:
        logger.error(f"Redis connection failed: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected Redis error: {str(e)}")
        return False
    finally:
        if 'redis_client' in locals():
            try:
                redis_client.close()
            except:
                pass

def create_app():
    """Create and configure the Flask application"""
    logger.info("Initializing Flask application...")
    
    # Check environment variables first
    if not os.environ.get('SMSDEV_API_KEY'):
        logger.error("SMSDEV_API_KEY environment variable is not set")
        sys.exit(1)
    
    try:
        app = Flask(__name__)
        app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
        
        # Create required directories first
        os.makedirs('data', exist_ok=True)
        for path in ['data/integrations.json', 'data/campaigns.json', 'data/transactions.json', 
                     'data/sms_history.json', 'data/scheduled_sms.json']:
            if not os.path.exists(path):
                with open(path, 'w') as f:
                    f.write('[]')
                logger.info(f"Created file: {path}")

        # Apply production middleware with improved settings
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
            x_prefix=1
        )

        # Production configuration
        app.config.update(
            ENV='production',
            DEBUG=False,
            TESTING=False,
            PROPAGATE_EXCEPTIONS=True,
            PRESERVE_CONTEXT_ON_EXCEPTION=True,
            MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max file size
            SERVER_NAME=None,  # Allow all hostnames
            APPLICATION_ROOT='/',
            PREFERRED_URL_SCHEME='https',
            JSON_SORT_KEYS=True,
            JSON_AS_ASCII=False,
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
            PERMANENT_SESSION_LIFETIME=1800
        )

        # Import views after app creation to avoid circular imports
        from app import register_routes
        register_routes(app)

        @app.before_request
        def setup_request_logging():
            """Set up request logging"""
            logger.debug(f"Received request: {request.method} {request.path}")

        @app.after_request
        def after_request_logging(response):
            """Log after request"""
            logger.debug(f"Request completed: {response.status}")
            return response

        @app.route('/health')
        def health_check():
            """Enhanced health check endpoint"""
            try:
                # Check Redis connection
                redis_healthy = check_redis_connection()
                
                # Check SMS API key
                sms_api_key = os.environ.get('SMSDEV_API_KEY')
                sms_api_configured = bool(sms_api_key)
                
                # Check data directory and files
                data_dir_exists = os.path.exists('data')
                required_files = ['integrations.json', 'campaigns.json', 'transactions.json', 
                                'sms_history.json', 'scheduled_sms.json']
                missing_files = [f for f in required_files if not os.path.exists(f'data/{f}')]
                
                health_status = {
                    'status': 'healthy' if (redis_healthy and sms_api_configured and data_dir_exists and not missing_files) else 'unhealthy',
                    'redis': 'connected' if redis_healthy else 'disconnected',
                    'sms_api': 'configured' if sms_api_configured else 'not_configured',
                    'data_directory': 'exists' if data_dir_exists else 'missing',
                    'missing_files': missing_files if missing_files else None,
                    'version': '1.0.0',
                    'environment': app.config['ENV']
                }
                
                logger.info(f"Health check status: {health_status}")
                status_code = 200 if health_status['status'] == 'healthy' else 503
                return health_status, status_code
            except Exception as e:
                logger.error(f"Health check failed: {str(e)}", exc_info=True)
                return {'status': 'error', 'message': str(e)}, 500

        logger.info("Flask application initialized successfully")
        return app

    except Exception as e:
        logger.error(f"Error initializing application: {str(e)}", exc_info=True)
        raise

app = create_app()

if __name__ == "__main__":
    try:
        # Verify required environment variables
        if not os.environ.get('SMSDEV_API_KEY'):
            logger.error("SMSDEV_API_KEY environment variable is not set")
            sys.exit(1)
            
        # Ensure Redis is ready
        if not check_redis_connection():
            logger.error("Redis is not ready")
            sys.exit(1)

        # Run the application
        app.run(
            host='0.0.0.0',
            port=8080,
            threaded=True
        )
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}", exc_info=True)
        sys.exit(1)
