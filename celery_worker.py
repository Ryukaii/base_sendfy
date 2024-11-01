from celery import Celery
import requests
import json
import os
import re
from datetime import datetime

# Initialize Celery
celery = Celery('sms_tasks',
                broker='redis://localhost:6379/0',
                backend='redis://localhost:6379/0')

# SMS API Configuration
SMS_API_ENDPOINT = "https://api.apisms.me/v2/send.php"
SMS_API_TOKEN = os.environ.get('SMS_API_TOKEN')

def format_phone_number(phone):
    # Remove all non-numeric characters
    numbers = re.sub(r'\D', '', phone)
    # Ensure it starts with country code
    if not numbers.startswith('55'):
        numbers = '55' + numbers
    if not numbers.startswith('+'):
        numbers = '+' + numbers
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
def send_sms_task(self, phone, message, operator="claro", campaign_id=None, event_type="manual"):
    try:
        # Format phone number
        formatted_phone = format_phone_number(phone)
        
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
        
        # Send SMS
        response = requests.post(
            SMS_API_ENDPOINT,
            json=sms_data,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        # Parse response
        api_response = response.json()
        
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
