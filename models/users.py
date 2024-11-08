from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import logging
from replit import db

logger = logging.getLogger(__name__)

def init_db():
    """Initialize database collections if they don't exist"""
    if 'users' not in db:
        db['users'] = []
    if 'campaigns' not in db:
        db['campaigns'] = []
    if 'integrations' not in db:
        db['integrations'] = []
    if 'sms_history' not in db:
        db['sms_history'] = []
    if 'transactions' not in db:
        db['transactions'] = []

class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin=False, credits=0):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.credits = credits

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def get(user_id):
        users = db.get('users', [])
        user = next((u for u in users if u['id'] == user_id), None)
        if user:
            return User(
                id=user['id'],
                username=user['username'],
                password_hash=user['password_hash'],
                is_admin=user.get('is_admin', False),
                credits=user.get('credits', 0)
            )
        return None

    @staticmethod
    def get_by_username(username):
        users = db.get('users', [])
        user = next((u for u in users if u['username'] == username), None)
        if user:
            return User(
                id=user['id'],
                username=user['username'],
                password_hash=user['password_hash'],
                is_admin=user.get('is_admin', False),
                credits=user.get('credits', 0)
            )
        return None

    @staticmethod
    def create(username, password, is_admin=False, credits=0):
        users = db.get('users', [])
        
        # Check if username already exists
        if any(u['username'] == username for u in users):
            return None
            
        user = {
            'id': str(len(users) + 1),
            'username': username,
            'password_hash': generate_password_hash(password),
            'is_admin': is_admin,
            'credits': credits
        }
        users.append(user)
        db['users'] = users
        
        return User(
            id=user['id'],
            username=user['username'],
            password_hash=user['password_hash'],
            is_admin=user['is_admin'],
            credits=user['credits']
        )

    @staticmethod
    def delete(user_id):
        try:
            users = db.get('users', [])
            users = [u for u in users if u['id'] != user_id]
            db['users'] = users
            return True
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}")
            return False

    @staticmethod
    def get_all():
        users = db.get('users', [])
        return [User(
            id=u['id'],
            username=u['username'],
            password_hash=u['password_hash'],
            is_admin=u.get('is_admin', False),
            credits=u.get('credits', 0)
        ) for u in users]

    def add_credits(self, amount):
        """Add credits to user account"""
        try:
            users = db.get('users', [])
            for user in users:
                if user['id'] == self.id:
                    user['credits'] = user.get('credits', 0) + amount
                    self.credits = user['credits']
                    db['users'] = users
                    logger.info(f"Added {amount} credits to user {self.username}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error adding credits: {str(e)}")
            return False

    def deduct_credits(self, amount):
        """Deduct credits from user account"""
        try:
            users = db.get('users', [])
            for user in users:
                if user['id'] == self.id:
                    current_credits = user.get('credits', 0)
                    if current_credits < amount:
                        return False
                    
                    user['credits'] = current_credits - amount
                    self.credits = user['credits']
                    db['users'] = users
                    logger.info(f"Deducted {amount} credits from user {self.username}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error deducting credits: {str(e)}")
            return False

    def has_sufficient_credits(self, amount):
        """Check if user has sufficient credits"""
        return self.credits >= amount