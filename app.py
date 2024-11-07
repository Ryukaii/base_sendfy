[Previous content up to line 490...]

@app.route('/webhook/<path:webhook_path>', methods=['POST'])
def webhook_handler(webhook_path):
    try:
        webhook_data = request.get_json()
        logger.debug(f"Received webhook data: {webhook_data}")
        
        # Find integration with matching webhook URL
        with open(INTEGRATIONS_FILE, 'r') as f:
            integrations = json.load(f)
            integration = next((i for i in integrations if webhook_path in i.get('webhook_url', '')), None)
        
        if not integration:
            logger.error(f"No integration found for webhook path: {webhook_path}")
            return handle_api_error('Integration not found', 404)
            
        # Get user who owns the integration
        user = User.get(integration['user_id'])
        if not user:
            logger.error(f"User not found for integration {integration['id']}")
            return handle_api_error('Integration owner not found', 404)
            
        # Load campaigns for this integration
        with open(CAMPAIGNS_FILE, 'r') as f:
            campaigns = json.load(f)
            
        # Get status from webhook data
        status = webhook_data.get('status', 'pending').lower()
        
        # Find matching campaigns
        matching_campaigns = [
            c for c in campaigns 
            if c['integration_id'] == integration['id'] 
            and c['event_type'].lower() == status
            and c['user_id'] == user.id
        ]
        
        if not matching_campaigns:
            logger.warning(f"No campaigns found for integration {integration['id']} and status {status}")
            return jsonify({
                'success': True,
                'message': 'No matching campaigns found for this event type'
            })
            
        # Create transaction record
        transaction_id = str(uuid.uuid4())[:8]
        customer_data = webhook_data.get('customer', {})
        
        # Format customer name for URL
        url_safe_name = re.sub(r'[^a-zA-Z0-9]', '', customer_data.get('name', ''))
        
        transaction = {
            'transaction_id': transaction_id,
            'customer_name': customer_data.get('name', ''),
            'customer_phone': customer_data.get('phone', ''),
            'customer_email': customer_data.get('email', ''),
            'product_name': webhook_data.get('product_name', ''),
            'total_price': webhook_data.get('total_price', '0.00'),
            'pix_code': webhook_data.get('pix_code', ''),
            'status': status,
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Save transaction
        with open(TRANSACTIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            transactions = json.load(f)
            transactions.append(transaction)
            f.seek(0)
            json.dump(transactions, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        success_count = 0
        for campaign in matching_campaigns:
            try:
                for message in campaign.get('messages', []):
                    if not message.get('enabled', True):
                        continue
                        
                    if not user.has_sufficient_credits(1):
                        logger.warning(f"User {user.id} has insufficient credits")
                        continue
                    
                    # Format template variables
                    template = message['template']
                    full_name = customer_data.get('name', '')
                    first_name = full_name.split()[0] if full_name else ''
                    
                    # Format phone
                    phone = customer_data.get('phone', '')
                    if not phone.startswith('+55'):
                        phone = f'+55{phone}'
                        
                    # Replace template variables
                    formatted_message = template
                    formatted_message = formatted_message.replace('{customer.first_name}', first_name)
                    formatted_message = formatted_message.replace('{total_price}', webhook_data.get('total_price', ''))
                    
                    # Add PIX link for pending status
                    if status == 'pending':
                        # Use request.host_url for the domain
                        payment_url = f"{request.host_url.rstrip('/')}/payment/{url_safe_name}/{transaction_id}"
                        formatted_message = formatted_message.replace('{link_pix}', payment_url)
                    
                    # Calculate delay
                    delay = message.get('delay', {})
                    delay_seconds = calculate_delay_seconds(
                        amount=delay.get('amount', 0),
                        unit=delay.get('unit', 'minutes')
                    )
                    
                    # Schedule SMS
                    scheduled_time = (
                        datetime.datetime.now() + 
                        datetime.timedelta(seconds=delay_seconds)
                    ).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Save scheduled SMS
                    scheduled_sms = {
                        'id': str(uuid.uuid4()),
                        'phone': phone,
                        'message': formatted_message,
                        'send_at': scheduled_time,
                        'campaign_id': campaign['id'],
                        'user_id': user.id,
                        'status': 'pending'
                    }
                    
                    with open(SCHEDULED_SMS_FILE, 'r+') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        scheduled_messages = json.load(f)
                        scheduled_messages.append(scheduled_sms)
                        f.seek(0)
                        json.dump(scheduled_messages, f, indent=2)
                        f.truncate()
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
                    # Deduct credit and queue SMS
                    if user.deduct_credits(1):
                        logger.info(f"Queuing SMS to {phone}: {formatted_message}")
                        send_sms_task.apply_async(
                            args=[phone, formatted_message, campaign['event_type']],
                            countdown=delay_seconds
                        )
                        success_count += 1
                        logger.info(f"SMS queued for campaign {campaign['id']}")
                    
                    # Add to history
                    with open(SMS_HISTORY_FILE, 'r+') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        history = json.load(f)
                        history.append({
                            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'phone': phone,
                            'message': formatted_message,
                            'type': 'campaign',
                            'status': 'scheduled',
                            'user_id': user.id,
                            'campaign_id': campaign['id']
                        })
                        f.seek(0)
                        json.dump(history, f, indent=2)
                        f.truncate()
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
            except Exception as e:
                logger.error(f"Error processing campaign {campaign['id']}: {str(e)}")
                user.add_credits(1)  # Refund credit on error
                continue
        
        return jsonify({
            'success': True,
            'message': f'Webhook processed successfully. Queued {success_count} messages.',
            'transaction_id': transaction_id
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return handle_api_error('Error processing webhook')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
