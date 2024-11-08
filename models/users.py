import json
import os
import fcntl
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import logging
from functools import wraps

logger = logging.getLogger(__name__)

USERS_FILE = 'data/users.json'

def ensure_users_file():
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump([], f)

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
        ensure_users_file()
        with open(USERS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
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
        ensure_users_file()
        with open(USERS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
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
        ensure_users_file()
        with open(USERS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            
            # Check if username already exists
            if any(u['username'] == username for u in users):
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return None
                
            user = {
                'id': str(len(users) + 1),
                'username': username,
                'password_hash': generate_password_hash(password),
                'is_admin': is_admin,
                'credits': credits
            }
            users.append(user)
            
            f.seek(0)
            json.dump(users, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
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
            ensure_users_file()
            with open(USERS_FILE, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                users = json.load(f)
                
                # Remove user with matching ID
                users = [u for u in users if u['id'] != user_id]
                
                f.seek(0)
                json.dump(users, f, indent=2)
                f.truncate()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
                return True
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}")
            return False

    @staticmethod
    def get_all():
        ensure_users_file()
        with open(USERS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
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
            with open(USERS_FILE, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                users = json.load(f)
                
                for user in users:
                    if user['id'] == self.id:
                        user['credits'] = user.get('credits', 0) + amount
                        self.credits = user['credits']
                        break
                
                f.seek(0)
                json.dump(users, f, indent=2)
                f.truncate()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
                logger.info(f"Added {amount} credits to user {self.username}")
                return True
        except Exception as e:
            logger.error(f"Error adding credits: {str(e)}")
            return False

    def deduct_credits(self, amount):
        """Deduct credits from user account"""
        try:
            with open(USERS_FILE, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                users = json.load(f)
                
                for user in users:
                    if user['id'] == self.id:
                        current_credits = user.get('credits', 0)
                        if current_credits < amount:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                            return False
                        
                        user['credits'] = current_credits - amount
                        self.credits = user['credits']
                        break
                
                f.seek(0)
                json.dump(users, f, indent=2)
                f.truncate()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
                logger.info(f"Deducted {amount} credits from user {self.username}")
                return True
        except Exception as e:
            logger.error(f"Error deducting credits: {str(e)}")
            return False

    def has_sufficient_credits(self, amount):
        """Check if user has sufficient credits"""
        return self.credits >= amount
