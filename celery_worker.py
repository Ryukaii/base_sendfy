from celery import Celery
import requests
import json
import os
import re
from datetime import datetime

# Initialize Celery with environment variables for broker/backend
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
celery = Celery('sms_tasks',
                broker=REDIS_URL,
                backend=REDIS_URL)

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

@celery.task(bind=True, max_retries=3, default_retry_delay=300, soft_time_limit=30)
def send_sms_task(self, phone, message, operator="claro", campaign_id=None, event_type="manual"):
    if not SMS_API_KEY:
        error_msg = "SMS_API_KEY not configured"
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
        
        # Send SMS with proper timeout handling
        response = requests.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            timeout=(5, 20)  # (connect timeout, read timeout)
        )
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        
        # Check if the message was sent successfully
        # SMS Dev returns 'situacao': 'OK' for success
        success = api_response.get('situacao') == 'OK'
        
        if not success:
            error_msg = api_response.get('erro', 'Unknown error from SMS provider')
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
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone if 'formatted_phone' in locals() else phone,
            message=message,
            status='failed',
            api_response=error_msg,
            event_type=event_type
        )
        raise self.retry(exc=e, countdown=self.request.retries * 300 + 60)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error sending SMS: {str(e)}"
        log_sms_attempt(
            campaign_id=campaign_id,
            phone=formatted_phone if 'formatted_phone' in locals() else phone,
            message=message,
            status='failed',
            api_response=error_msg,
            event_type=event_type
        )
        # Retry the task with exponential backoff
        raise self.retry(exc=e, countdown=self.request.retries * 300 + 60)
