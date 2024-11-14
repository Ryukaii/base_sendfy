from models.database import db, User, Integration, Campaign, Transaction, SMSHistory
import json
import os
from app import app

def migrate_data():
    try:
        with app.app_context():
            # Create tables
            db.create_all()
            print("Tables created successfully")
            
            # Migrate users
            users_file = 'data/users.json'
            if os.path.exists(users_file):
                with open(users_file, 'r') as f:
                    users = json.load(f)
                    for user_data in users:
                        existing_user = User.query.filter_by(id=user_data['id']).first()
                        if not existing_user:
                            user = User(
                                id=int(user_data['id']),
                                username=user_data['username'],
                                password_hash=user_data['password_hash'],
                                is_admin=user_data.get('is_admin', False),
                                credits=user_data.get('credits', 0)
                            )
                            db.session.add(user)
                print("Users migrated successfully")
            
            # Migrate integrations
            integrations_file = 'data/integrations.json'
            if os.path.exists(integrations_file):
                with open(integrations_file, 'r') as f:
                    integrations = json.load(f)
                    for integration_data in integrations:
                        existing_integration = Integration.query.filter_by(webhook_url=integration_data['webhook_url']).first()
                        if not existing_integration:
                            integration = Integration(
                                name=integration_data['name'],
                                webhook_url=integration_data['webhook_url'],
                                user_id=integration_data['user_id']
                            )
                            db.session.add(integration)
                print("Integrations migrated successfully")
            
            # Migrate campaigns
            campaigns_file = 'data/campaigns.json'
            if os.path.exists(campaigns_file):
                with open(campaigns_file, 'r') as f:
                    campaigns = json.load(f)
                    for campaign_data in campaigns:
                        existing_campaign = Campaign.query.filter_by(id=campaign_data['id']).first()
                        if not existing_campaign:
                            campaign = Campaign(
                                name=campaign_data['name'],
                                integration_id=campaign_data['integration_id'],
                                event_type=campaign_data['event_type'],
                                message_template=campaign_data['message_template'],
                                user_id=campaign_data['user_id']
                            )
                            db.session.add(campaign)
                print("Campaigns migrated successfully")
            
            # Migrate transactions
            transactions_file = 'data/transactions.json'
            if os.path.exists(transactions_file):
                with open(transactions_file, 'r') as f:
                    transactions = json.load(f)
                    for transaction_data in transactions:
                        existing_transaction = Transaction.query.filter_by(transaction_id=transaction_data['transaction_id']).first()
                        if not existing_transaction:
                            transaction = Transaction(
                                transaction_id=transaction_data['transaction_id'],
                                customer_name=transaction_data.get('customer_name'),
                                customer_phone=transaction_data.get('customer_phone'),
                                customer_email=transaction_data.get('customer_email'),
                                product_name=transaction_data.get('product_name'),
                                total_price=transaction_data.get('total_price'),
                                pix_code=transaction_data.get('pix_code'),
                                status=transaction_data.get('status')
                            )
                            db.session.add(transaction)
                print("Transactions migrated successfully")
            
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
                            user_id=sms_data['user_id']
                        )
                        db.session.add(sms)
                print("SMS history migrated successfully")
            
            try:
                db.session.commit()
                print("All data migrated successfully")
                return True
            except Exception as e:
                print(f"Error during commit: {str(e)}")
                db.session.rollback()
                return False
                
    except Exception as e:
        print(f"Error during database setup: {str(e)}")
        return False

if __name__ == '__main__':
    migrate_data()
