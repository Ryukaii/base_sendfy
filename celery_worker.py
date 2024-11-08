import logging
import requests
import json
import os
import re
import sys
from datetime import datetime
from celery import Celery
import redis
from urllib.parse import urlparse

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('celery.log')
    ]
)
logger = logging.getLogger(__name__)

def check_redis_connection():
    """Check Redis connection with improved error handling"""
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    try:
        parsed_url = urlparse(redis_url)
        redis_client = redis.Redis(
            host=parsed_url.hostname or 'localhost',
            port=parsed_url.port or 6379,
            db=int(parsed_url.path.replace('/', '') or 0),
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

# Check environment variables at startup
SMS_API_KEY = os.environ.get('SMSDEV_API_KEY')
if not SMS_API_KEY:
    logger.error("SMSDEV_API_KEY environment variable is not set")
    sys.exit(1)

# Redis URL configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
logger.info(f"Configuring Celery with Redis URL: {REDIS_URL}")

# Configure Celery with optimized settings
celery = Celery('sms_tasks',
                broker=REDIS_URL,
                backend=REDIS_URL)

celery.conf.update(
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Sao_Paulo',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_pool_limit=None,
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=256000,
    task_time_limit=300,
    task_soft_time_limit=240,
    task_default_queue='celery',
    task_default_exchange='celery',
    task_default_routing_key='celery',
    task_default_delivery_mode='persistent',
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    task_track_started=True,
    task_send_sent_event=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={'visibility_timeout': 3600},
    result_expires=3600
)

# SMS API Configuration
SMS_API_ENDPOINT = "https://api.smsdev.com.br/v1/send"

def format_phone_number(phone):
    """Format Brazilian phone number to international format"""
    # Remove all non-numeric characters
    numbers = re.sub(r'\D', '', phone)
    
    # Remove +55 if present at the start
    if numbers.startswith('55'):
        numbers = numbers[2:]
    
    # Ensure it's a valid Brazilian number
    if len(numbers) < 10 or len(numbers) > 11:
        raise ValueError("Invalid phone number length")
    
    # Add country code
    numbers = '55' + numbers
    
    return numbers

def ensure_data_directory():
    """Ensure data directory exists"""
    if not os.path.exists('data'):
        os.makedirs('data')
        logger.info("Created data directory")

def log_sms_attempt(phone, message, status, api_response, event_type="manual", campaign_id=None):
    """Log SMS sending attempt to history file with improved error handling"""
    try:
        ensure_data_directory()
        history_file = 'data/sms_history.json'
        
        # Create history file if it doesn't exist
        if not os.path.exists(history_file):
            with open(history_file, 'w') as f:
                json.dump([], f)
                logger.info("Created new SMS history file")
        
        # Read existing history with proper error handling
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except json.JSONDecodeError:
            logger.error("Error reading SMS history file, resetting to empty list")
            history = []
        
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "phone": phone,
            "message": message,
            "status": status,
            "api_response": api_response,
            "campaign_id": campaign_id,
            "event_type": event_type
        }
        
        # Write updated history with error handling
        try:
            history.append(entry)
            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)
            logger.info(f"SMS attempt logged successfully: {entry}")
        except Exception as e:
            logger.error(f"Error writing to SMS history file: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in log_sms_attempt: {str(e)}")

@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def send_sms_task(self, phone, message, event_type="manual", campaign_id=None):
    """Send SMS using SMS Dev API with improved error handling"""
    logger.info(f"Starting SMS task execution: phone={phone}, campaign_id={campaign_id}")
    
    try:
        # Format phone number
        formatted_phone = format_phone_number(phone)
        logger.info(f"Formatted phone number: {formatted_phone}")
        
        # Prepare request payload
        sms_data = {
            "key": SMS_API_KEY,
            "type": 9,
            "number": formatted_phone,
            "msg": message,
            "ref": campaign_id or "manual_send"
        }
        
        logger.info(f"Sending SMS request to {SMS_API_ENDPOINT}")
        logger.debug(f"Request payload (without key): {json.dumps({k:v for k,v in sms_data.items() if k != 'key'})}")
        
        # Send SMS with timeout and retry settings
        response = requests.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            timeout=30,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'SendFy SMS Platform/1.0'
            }
        )
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        logger.info(f"SMS API Response: {api_response}")
        
        success = api_response.get('situacao') == 'OK'
        
        if not success:
            error_msg = api_response.get('erro', 'Unknown error from SMS provider')
            logger.error(f"SMS sending failed: {error_msg}")
            log_sms_attempt(formatted_phone, message, 'failed', str(api_response), event_type, campaign_id)
            raise self.retry(exc=Exception(error_msg))
        
        # Log successful attempt
        log_sms_attempt(formatted_phone, message, 'success', str(api_response), event_type, campaign_id)
        
        logger.info(f"SMS sent successfully to {formatted_phone}")
        return {
            'success': True,
            'message': api_response.get('retorno', 'SMS sent successfully')
        }
        
    except requests.exceptions.RequestException as e:
        error_msg = f"HTTP Error sending SMS: {str(e)}"
        logger.error(error_msg, exc_info=True)
        log_sms_attempt(phone, message, 'failed', error_msg, event_type, campaign_id)
        raise self.retry(exc=e)
        
    except Exception as e:
        error_msg = f"Error sending SMS: {str(e)}"
        logger.error(error_msg, exc_info=True)
        log_sms_attempt(phone, message, 'failed', error_msg, event_type, campaign_id)
        raise self.retry(exc=e)
