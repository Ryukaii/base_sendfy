from flask import Flask, render_template, request, jsonify
import json
import uuid
import datetime
import logging
import os
from celery_worker import send_sms_task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# File paths
INTEGRATIONS_FILE = 'data/integrations.json'
CAMPAIGNS_FILE = 'data/campaigns.json'
SMS_HISTORY_FILE = 'data/sms_history.json'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sms')
def sms():
    return render_template('sms.html')

@app.route('/integrations')
def integrations():
    return render_template('integrations.html')

@app.route('/campaigns')
def campaigns():
    return render_template('campaigns.html')

@app.route('/campaign-performance')
def campaign_performance():
    # Load campaign data and SMS history
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        with open(SMS_HISTORY_FILE, 'r') as f:
            sms_history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        campaigns = []
        sms_history = []

    # Calculate campaign statistics
    campaign_stats = []
    for campaign in campaigns:
        campaign_messages = [msg for msg in sms_history if msg['campaign_id'] == campaign['id']]
        success_count = len([msg for msg in campaign_messages if msg['status'] == 'success'])
        total_messages = len(campaign_messages)
        success_rate = (success_count / total_messages * 100) if total_messages > 0 else 0
        
        campaign_stats.append({
            'name': campaign['name'],
            'event_type': campaign['event_type'],
            'messages_sent': total_messages,
            'success_rate': round(success_rate, 1),
            'last_message': campaign_messages[-1]['timestamp'] if campaign_messages else 'N/A'
        })

    # Get recent activity
    recent_activity = sorted(
        [msg for msg in sms_history if msg['campaign_id']],
        key=lambda x: x['timestamp'],
        reverse=True
    )[:10]

    # Add campaign names to recent activity
    campaign_map = {c['id']: c['name'] for c in campaigns}
    for activity in recent_activity:
        activity['campaign_name'] = campaign_map.get(activity['campaign_id'], 'Unknown')

    return render_template('campaign_performance.html',
                         total_campaigns=len(campaigns),
                         active_campaigns=len([c for c in campaigns if any(msg['campaign_id'] == c['id'] for msg in recent_activity)]),
                         total_messages=len([msg for msg in sms_history if msg['campaign_id']]),
                         campaigns=campaign_stats,
                         recent_activity=recent_activity)

@app.route('/sms-history')
def sms_history():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
        return render_template('sms_history.html', sms_history=history)
    except (FileNotFoundError, json.JSONDecodeError):
        return render_template('sms_history.html', sms_history=[])

@app.route('/analytics')
def analytics():
    try:
        with open(SMS_HISTORY_FILE, 'r') as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    # Calculate statistics
    total_messages = len(history)
    success_messages = len([msg for msg in history if msg['status'] == 'success'])
    success_rate = round((success_messages / total_messages * 100) if total_messages > 0 else 0, 1)
    manual_messages = len([msg for msg in history if msg['event_type'] == 'manual'])
    campaign_messages = len([msg for msg in history if msg['event_type'] != 'manual'])

    # Messages by status
    status_counts = {}
    for msg in history:
        status_counts[msg['status']] = status_counts.get(msg['status'], 0) + 1

    messages_by_status = [
        {
            'status': status,
            'count': count,
            'percentage': round((count / total_messages * 100) if total_messages > 0 else 0, 1)
        }
        for status, count in status_counts.items()
    ]

    # Messages by event type
    event_counts = {}
    for msg in history:
        event_counts[msg['event_type']] = event_counts.get(msg['event_type'], 0) + 1

    messages_by_event = [
        {
            'type': event_type,
            'count': count,
            'percentage': round((count / total_messages * 100) if total_messages > 0 else 0, 1)
        }
        for event_type, count in event_counts.items()
    ]

    return render_template('analytics.html',
                         total_messages=total_messages,
                         success_rate=success_rate,
                         manual_messages=manual_messages,
                         campaign_messages=campaign_messages,
                         messages_by_status=messages_by_status,
                         messages_by_event=messages_by_event,
                         recent_activity=sorted(history, key=lambda x: x['timestamp'], reverse=True)[:10])

@app.route('/api/send-sms', methods=['POST'])
def send_sms():
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['phone', 'message', 'operator']):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        # Queue SMS task
        task = send_sms_task.delay(
            phone=data['phone'],
            message=data['message'],
            operator=data['operator']
        )

        return jsonify({
            'success': True,
            'message': 'SMS queued successfully',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/integrations', methods=['GET'])
def get_integrations():
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
        return jsonify(integrations)
    except Exception as e:
        logger.error(f"Error loading integrations: {str(e)}")
        return jsonify([])

@app.route('/api/integrations', methods=['POST'])
def create_integration():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400

        integration_id = str(uuid.uuid4())
        integration = {
            'id': integration_id,
            'name': data['name'],
            'webhook_url': f'/webhook/{integration_id}',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(INTEGRATIONS_FILE, 'r') as f:
                integrations = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            integrations = []

        integrations.append(integration)

        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(integrations, f, indent=2)

        return jsonify(integration), 201
    except Exception as e:
        logger.error(f"Error creating integration: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
def delete_integration(integration_id):
    try:
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)

        updated_integrations = [i for i in integrations if i['id'] != integration_id]

        if len(updated_integrations) == len(integrations):
            return jsonify({'error': 'Integration not found'}), 404

        with open(INTEGRATIONS_FILE, 'w') as f:
            json.dump(updated_integrations, f, indent=2)

        # Also delete associated campaigns
        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                campaigns = json.load(f)

            updated_campaigns = [c for c in campaigns if c['integration_id'] != integration_id]

            with open(CAMPAIGNS_FILE, 'w') as f:
                json.dump(updated_campaigns, f, indent=2)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return jsonify({'message': 'Integration deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting integration: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns', methods=['GET'])
def get_campaigns():
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
        return jsonify(campaigns)
    except Exception as e:
        logger.error(f"Error loading campaigns: {str(e)}")
        return jsonify([])

@app.route('/api/campaigns', methods=['POST'])
def create_campaign():
    try:
        data = request.get_json()
        required_fields = ['name', 'integration_id', 'event_type', 'message_template']
        
        if not data or not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        campaign = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'integration_id': data['integration_id'],
            'event_type': data['event_type'],
            'message_template': data['message_template'],
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                campaigns = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            campaigns = []

        campaigns.append(campaign)

        with open(CAMPAIGNS_FILE, 'w') as f:
            json.dump(campaigns, f, indent=2)

        return jsonify(campaign), 201
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns/<campaign_id>', methods=['PUT'])
def update_campaign(campaign_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)

        campaign_index = next((i for i, c in enumerate(campaigns) if c['id'] == campaign_id), None)
        if campaign_index is None:
            return jsonify({'error': 'Campaign not found'}), 404

        # Update allowed fields
        for field in ['name', 'event_type', 'message_template']:
            if field in data:
                campaigns[campaign_index][field] = data[field]

        with open(CAMPAIGNS_FILE, 'w') as f:
            json.dump(campaigns, f, indent=2)

        return jsonify(campaigns[campaign_index])
    except Exception as e:
        logger.error(f"Error updating campaign: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns/<campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id):
    try:
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)

        updated_campaigns = [c for c in campaigns if c['id'] != campaign_id]

        if len(updated_campaigns) == len(campaigns):
            return jsonify({'error': 'Campaign not found'}), 404

        with open(CAMPAIGNS_FILE, 'w') as f:
            json.dump(updated_campaigns, f, indent=2)

        return jsonify({'message': 'Campaign deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting campaign: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
