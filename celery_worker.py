from celery import Celery
import requests
import json
import os
import re
from datetime import datetime
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery with environment-aware configuration
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
celery = Celery('sms_tasks',
                broker=redis_url,
                backend=redis_url)

# SMS API Configuration
SMS_API_ENDPOINT = "https://api.smsdev.com.br/v1/send"
SMS_API_KEY = os.environ.get('SMSDEV_API_KEY')

if not SMS_API_KEY:
    raise ValueError("SMSDEV_API_KEY environment variable is not set")

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
    """Log SMS sending attempt to history file"""
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
    
    with open('data/sms_history.json', 'w') as f:
        json.dump(history, f, indent=2)

@celery.task(bind=True, max_retries=3)
def send_sms_task(self, phone, message, campaign_id=None, event_type="manual"):
    """Celery task for sending SMS messages"""
    try:
        logger.info(f"Sending SMS to {phone}: {message}")
        
        # Format phone number
        try:
            formatted_phone = format_phone_number(phone)
            logger.info(f"Formatted phone number: {formatted_phone}")
        except ValueError as e:
            logger.error(f"Phone number formatting error: {str(e)}")
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
        
        # Prepare request payload for smsdev.com.br
        sms_data = {
            "key": SMS_API_KEY,
            "type": 9, # Type 9 for text message
            "number": formatted_phone,
            "msg": message,
            "ref": campaign_id or "manual_send"
        }
        
        logger.info(f"Sending request to SMS API: {SMS_API_ENDPOINT}")
        
        # Send SMS
        response = requests.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            timeout=10
        )
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        logger.info(f"SMS API Response: {api_response}")
        
        # Check if the message was sent successfully
        # SMS Dev returns 'situacao': 'OK' for success
        success = api_response.get('situacao') == 'OK'
        
        # Log the attempt
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone,
            message=message,
            status='success' if success else 'failed',
            api_response=str(api_response),
            event_type=event_type
        )
        
        if success:
            logger.info(f"SMS sent successfully to {formatted_phone}")
        else:
            logger.error(f"Failed to send SMS: {api_response.get('erro', 'Unknown error')}")
        
        return {
            'success': success,
            'message': api_response.get('retorno', 'SMS sent successfully') if success else api_response.get('erro', 'Failed to send SMS')
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
        logger.info(f"Retrying SMS task in {backoff} seconds (attempt {retry_count + 1}/3)")
        raise self.retry(exc=e, countdown=backoff)
