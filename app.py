[Previous content plus...]

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
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)

        updated_campaigns = [c for c in campaigns if c['integration_id'] != integration_id]

        with open(CAMPAIGNS_FILE, 'w') as f:
            json.dump(updated_campaigns, f, indent=2)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
