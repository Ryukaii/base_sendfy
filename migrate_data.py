from models.database import db, User, Integration, Campaign, Transaction, SMSHistory
import json
import os
from app import app

def migrate_data():
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Migrate users
        users_file = 'data/users.json'
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                users = json.load(f)
                for user_data in users:
                    user = User(
                        id=int(user_data['id']),
                        username=user_data['username'],
                        password_hash=user_data['password_hash'],
                        is_admin=user_data.get('is_admin', False),
                        credits=user_data.get('credits', 0)
                    )
                    db.session.add(user)
        
        # Migrate integrations
        integrations_file = 'data/integrations.json'
        if os.path.exists(integrations_file):
            with open(integrations_file, 'r') as f:
                integrations = json.load(f)
                for integration_data in integrations:
                    integration = Integration(
                        name=integration_data['name'],
                        webhook_url=integration_data['webhook_url'],
                        user_id=integration_data['user_id'],
                        created_at=integration_data['created_at']
                    )
                    db.session.add(integration)
        
        # Migrate campaigns
        campaigns_file = 'data/campaigns.json'
        if os.path.exists(campaigns_file):
            with open(campaigns_file, 'r') as f:
                campaigns = json.load(f)
                for campaign_data in campaigns:
                    campaign = Campaign(
                        name=campaign_data['name'],
                        integration_id=campaign_data['integration_id'],
                        event_type=campaign_data['event_type'],
                        message_template=campaign_data['message_template'],
                        user_id=campaign_data['user_id'],
                        created_at=campaign_data['created_at']
                    )
                    db.session.add(campaign)
        
        # Migrate transactions
        transactions_file = 'data/transactions.json'
        if os.path.exists(transactions_file):
            with open(transactions_file, 'r') as f:
                transactions = json.load(f)
                for transaction_data in transactions:
                    transaction = Transaction(
                        transaction_id=transaction_data['transaction_id'],
                        customer_name=transaction_data.get('customer_name'),
                        customer_phone=transaction_data.get('customer_phone'),
                        customer_email=transaction_data.get('customer_email'),
                        product_name=transaction_data.get('product_name'),
                        total_price=transaction_data.get('total_price'),
                        pix_code=transaction_data.get('pix_code'),
                        status=transaction_data.get('status'),
                        created_at=transaction_data.get('created_at')
                    )
                    db.session.add(transaction)
        
        # Migrate SMS history
        sms_history_file = 'data/sms_history.json'
        if os.path.exists(sms_history_file):
            with open(sms_history_file, 'r') as f:
                history = json.load(f)
                for sms_data in history:
                    sms = SMSHistory(
                        phone=sms_data['phone'],
                        message=sms_data['message'],
                        type=sms_data['type'],
                        status=sms_data['status'],
                        user_id=sms_data['user_id'],
                        created_at=sms_data['timestamp']
                    )
                    db.session.add(sms)
        
        try:
            db.session.commit()
            print("Data migration completed successfully")
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    migrate_data()
