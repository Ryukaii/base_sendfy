from celery import Celery
from celery.exceptions import MaxRetriesExceededError
import requests
import json
import os
import re
import logging
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Initialize Celery
celery = Celery('sms_tasks',
                broker='redis://localhost:6379/0',
                backend='redis://localhost:6379/0')

# Configure Celery connection retry settings
celery.conf.broker_connection_retry_on_startup = True
celery.conf.broker_connection_max_retries = 10

# SMS API Configuration
SMS_API_ENDPOINT = "https://api.smsdev.com.br/v1/send"
SMS_API_KEY = os.environ.get('SMSDEV_API_KEY')

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
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
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
        
        # Prepare request payload for smsdev.com.br
        sms_data = {
            "key": SMS_API_KEY,
            "type": 9, # Type 9 for text message
            "number": formatted_phone,
            "msg": message,
            "ref": campaign_id or "manual_send"
        }
        
        # Send SMS
        response = requests.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            timeout=10
        )
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        
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
        
        return {
            'success': success,
            'message': api_response.get('retorno', 'SMS sent successfully') if success else api_response.get('erro', 'Failed to send SMS')
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"SMS API error: {str(e)}")
        try:
            self.retry(countdown=2 ** self.request.retries)
        except MaxRetriesExceededError:
            return {
                'success': False,
                'error': f'Failed to send SMS after retries: {str(e)}'
            }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }