from celery import Celery
import requests
import json
import os
import re
import logging
from datetime import datetime

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/celery.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize Celery with improved configuration
celery = Celery('sms_tasks')

# Configure Celery with production-ready settings
celery.conf.update(
    broker_url=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    broker_connection_max_retries=None,  # Keep retrying forever
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour
        'socket_timeout': 30,        # Socket timeout in seconds
        'socket_connect_timeout': 30  # Socket connect timeout in seconds
    },
    result_expires=3600,  # Results expire in 1 hour
    worker_max_tasks_per_child=1000, # Restart worker after 1000 tasks
    task_soft_time_limit=60,         # Soft timeout of 60 seconds
    task_time_limit=120              # Hard timeout of 120 seconds
)

# SMS API Configuration with validation
SMS_API_ENDPOINT = "https://api.smsdev.com.br/v1/send"
SMS_API_KEY = os.environ.get('SMSDEV_API_KEY')

if not SMS_API_KEY:
    logger.error("SMSDEV_API_KEY not configured in environment")
    raise ValueError("SMSDEV_API_KEY must be configured")

def format_phone_number(phone):
    """Format Brazilian phone number to international format"""
    # Remove all non-numeric characters
    numbers = re.sub(r'\D', '', phone)
    
    # Ensure it's a valid Brazilian number
    if len(numbers) < 10 or len(numbers) > 13:
        raise ValueError("Invalid phone number length")
    
    # If number doesn't start with country code, add it
    if not numbers.startswith('55'):
        numbers = '55' + numbers
    
    # If DDD is missing (assuming it's an 8-digit number), raise error
    if len(numbers) < 12:
        raise ValueError("Missing area code (DDD)")
    
    return numbers

def log_sms_attempt(campaign_id, phone, message, status, api_response, event_type):
    """Log SMS attempt with improved error handling and retries"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"Logging SMS attempt: {status} - Phone: {phone}")
            with open('data/sms_history.json', 'r+') as f:
                try:
                    # Use file locking for thread safety
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    
                    try:
                        history = json.load(f)
                    except json.JSONDecodeError:
                        logger.warning("SMS history file corrupted, creating new one")
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
                    
                    history.append(entry)
                    
                    f.seek(0)
                    json.dump(history, f, indent=2)
                    f.truncate()
                    
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
            break  # Success, exit loop
            
        except (IOError, OSError) as e:
            retry_count += 1
            logger.error(f"Error logging SMS attempt (try {retry_count}): {str(e)}")
            if retry_count == max_retries:
                logger.critical(f"Failed to log SMS after {max_retries} attempts")
    
@celery.task(bind=True, 
             max_retries=5,
             default_retry_delay=300,
             soft_time_limit=60,
             time_limit=120,
             autoretry_for=(requests.exceptions.RequestException,),
             retry_backoff=True,
             retry_jitter=True)
def send_sms_task(self, phone, message, operator="claro", campaign_id=None, event_type="manual"):
    """Send SMS with improved error handling and retries"""
    logger.info(f"Starting SMS task for phone: {phone}")
    
    if not SMS_API_KEY:
        error_msg = "SMS_API_KEY not configured"
        logger.error(error_msg)
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=phone,
            message=message,
            status='failed',
            api_response=error_msg,
            event_type=event_type
        )
        raise ValueError(error_msg)

    try:
        # Format phone number
        try:
            formatted_phone = format_phone_number(phone)
            logger.info(f"Phone number formatted: {formatted_phone}")
        except ValueError as e:
            error_msg = f"Phone number formatting error: {str(e)}"
            logger.error(error_msg)
            log_sms_attempt(
                campaign_id=campaign_id,
                phone=phone,
                message=message,
                status='failed',
                api_response=error_msg,
                event_type=event_type
            )
            return {
                'success': False,
                'message': f'Invalid phone number: {str(e)}'
            }
        
        # Prepare request payload for smsdev.com.br
        sms_data = {
            "key": SMS_API_KEY,
            "type": 9,  # Type 9 for text message
            "number": formatted_phone,
            "msg": message,
            "ref": campaign_id or "manual_send"
        }
        
        logger.info(f"Sending SMS request to API for phone: {formatted_phone}")
        
        # Configure session with retries
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=100,
            pool_maxsize=100
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Send SMS with proper timeout handling
        response = session.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            timeout=(10, 30)  # (connect timeout, read timeout)
        )
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        logger.info(f"API Response received: {api_response}")
        
        # Check if the message was sent successfully
        success = api_response.get('situacao') == 'OK'
        
        if not success:
            error_msg = api_response.get('erro', 'Unknown error from SMS provider')
            logger.error(f"SMS sending failed: {error_msg}")
            log_sms_attempt(
                campaign_id=campaign_id,
                phone=formatted_phone,
                message=message,
                status='failed',
                api_response=str(api_response),
                event_type=event_type
            )
            
            # Retry for specific error codes that indicate temporary issues
            if any(code in str(api_response) for code in ['timeout', 'rate_limit', 'server_error']):
                raise self.retry(
                    exc=Exception(error_msg),
                    countdown=self.request.retries * 300 + 60  # Progressive backoff
                )
            return {
                'success': False,
                'message': error_msg
            }
        
        # Log successful attempt
        logger.info(f"SMS sent successfully to {formatted_phone}")
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone,
            message=message,
            status='success',
            api_response=str(api_response),
            event_type=event_type
        )
        
        return {
            'success': True,
            'message': api_response.get('retorno', 'SMS sent successfully')
        }
        
    except requests.exceptions.Timeout as e:
        error_msg = f"Timeout while sending SMS: {str(e)}"
        logger.error(error_msg)
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone if 'formatted_phone' in locals() else phone,
            message=message,
            status='failed',
            api_response=error_msg,
            event_type=event_type
        )
        raise self.retry(exc=e)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error sending SMS: {str(e)}"
        logger.error(error_msg)
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone if 'formatted_phone' in locals() else phone,
            message=message,
            status='failed',
            api_response=error_msg,
            event_type=event_type
        )
        raise self.retry(exc=e)
        
    except Exception as e:
        error_msg = f"Unexpected error while sending SMS: {str(e)}"
        logger.error(error_msg)
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone if 'formatted_phone' in locals() else phone,
            message=message,
            status='failed',
            api_response=error_msg,
            event_type=event_type
        )
        raise
