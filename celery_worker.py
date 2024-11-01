from celery import Celery
import requests
import json
import os
import re
from datetime import datetime
from celery.signals import celeryd_after_setup
from kombu import Connection
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis connection configuration
REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_MAX_RETRIES = 5
REDIS_RETRY_INTERVAL = 1

def create_celery_app():
    try:
        # Test Redis connection before initializing Celery
        with Connection(f'redis://{REDIS_HOST}:{REDIS_PORT}/0') as conn:
            conn.ensure_connection(max_retries=REDIS_MAX_RETRIES, 
                                interval_start=REDIS_RETRY_INTERVAL,
                                interval_step=REDIS_RETRY_INTERVAL)
            logger.info("Successfully connected to Redis")
            
        app = Celery('sms_tasks',
                    broker=f'redis://{REDIS_HOST}:{REDIS_PORT}/0',
                    backend=f'redis://{REDIS_HOST}:{REDIS_PORT}/0')
        
        # Celery configuration
        app.conf.update(
            broker_connection_retry_on_startup=True,
            broker_connection_max_retries=REDIS_MAX_RETRIES,
            broker_connection_timeout=30,
            result_expires=3600,
            task_serializer='json',
            accept_content=['json'],
            result_serializer='json',
            enable_utc=True,
        )
        
        return app
    except Exception as e:
        logger.error(f"Failed to initialize Celery: {str(e)}")
        raise

# Initialize Celery
try:
    celery = create_celery_app()
except Exception as e:
    logger.error(f"Failed to create Celery application: {str(e)}")
    raise

# SMS API Configuration
SMS_API_ENDPOINT = "https://api.apisms.me/v2/send.php"
SMS_API_TOKEN = os.environ.get('SMS_API_TOKEN')

def format_phone_number(phone):
    """Format Brazilian phone number to international format"""
    try:
        numbers = re.sub(r'\D', '', phone)
        
        if len(numbers) < 10 or len(numbers) > 13:
            raise ValueError("Invalid phone number length")
        
        if not numbers.startswith('55'):
            numbers = '55' + numbers
        
        if len(numbers) < 12:
            raise ValueError("Missing area code (DDD)")
        
        if not numbers.startswith('+'):
            numbers = '+' + numbers
            
        return numbers
    except Exception as e:
        logger.error(f"Error formatting phone number: {str(e)}")
        raise ValueError(f"Invalid phone number format: {str(e)}")

def log_sms_attempt(campaign_id, phone, message, status, api_response, event_type):
    try:
        with open('data/sms_history.json', 'r') as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
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
    
    try:
        with open('data/sms_history.json', 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write to SMS history: {str(e)}")

@celery.task(bind=True, max_retries=3)
def send_sms_task(self, phone, message, operator="claro", campaign_id=None, event_type="manual"):
    try:
        # Format phone number
        try:
            formatted_phone = format_phone_number(phone)
        except ValueError as e:
            log_sms_attempt(
                campaign_id=campaign_id,
                phone=phone,
                message=message,
                status='failed',
                api_response=f"Phone number formatting error: {str(e)}",
                event_type=event_type
            )
            return {
                'success': False,
                'message': f'Invalid phone number: {str(e)}'
            }
        
        # Prepare request payload
        sms_data = {
            "operator": operator,
            "destination_number": formatted_phone,
            "message": message,
            "tag": "SMS Platform",
            "user_reply": False
        }
        
        # Prepare headers with token
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {SMS_API_TOKEN}'
        }
        
        # Send SMS with retry mechanism
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
        def send_request():
            response = requests.post(
                SMS_API_ENDPOINT,
                json=sms_data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        
        # Send the request
        api_response = send_request()
        
        # Log the attempt
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone,
            message=message,
            status='success' if api_response.get('success', False) else 'failed',
            api_response=str(api_response),
            event_type=event_type
        )
        
        return {
            'success': api_response.get('success', False),
            'message': api_response.get('message', 'SMS sent successfully')
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"SMS API request failed: {str(e)}")
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone if 'formatted_phone' in locals() else phone,
            message=message,
            status='failed',
            api_response=str(e),
            event_type=event_type
        )
        
        # Retry the task with exponential backoff
        retry_count = self.request.retries
        backoff = 60 * (2 ** retry_count)  # 60s, 120s, 240s
        raise self.retry(exc=e, countdown=backoff)
