import json
import os
import fcntl
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

USERS_FILE = 'data/users.json'

def ensure_users_file():
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump([], f)

class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin=False, reset_token=None, reset_token_expiry=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.reset_token = reset_token
        self.reset_token_expiry = reset_token_expiry

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_reset_token(self, token=None):
        if token is None:
            token = secrets.token_urlsafe(32)
        expiry = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        
        with open(USERS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            for user in users:
                if user['id'] == self.id:
                    user['reset_token'] = token
                    user['reset_token_expiry'] = expiry
                    break
            f.seek(0)
            json.dump(users, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        self.reset_token = token
        self.reset_token_expiry = expiry
        return token

    def reset_password(self, new_password):
        with open(USERS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            for user in users:
                if user['id'] == self.id:
                    user['password_hash'] = generate_password_hash(new_password)
                    user['reset_token'] = None
                    user['reset_token_expiry'] = None
                    break
            f.seek(0)
            json.dump(users, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return True

    @staticmethod
    def verify_reset_token(token):
        with open(USERS_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        for user in users:
            if (user.get('reset_token') == token and 
                user.get('reset_token_expiry') and 
                datetime.fromisoformat(user['reset_token_expiry']) > datetime.utcnow()):
                return User(
                    id=user['id'],
                    username=user['username'],
                    password_hash=user['password_hash'],
                    is_admin=user.get('is_admin', False),
                    reset_token=user.get('reset_token'),
                    reset_token_expiry=user.get('reset_token_expiry')
                )
        return None

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
                reset_token=user.get('reset_token'),
                reset_token_expiry=user.get('reset_token_expiry')
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
                reset_token=user.get('reset_token'),
                reset_token_expiry=user.get('reset_token_expiry')
            )
        return None

    @staticmethod
    def create(username, password, is_admin=False):
        ensure_users_file()
        with open(USERS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            
            if any(u['username'] == username for u in users):
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return None
                
            user = {
                'id': str(len(users) + 1),
                'username': username,
                'password_hash': generate_password_hash(password),
                'is_admin': is_admin,
                'reset_token': None,
                'reset_token_expiry': None
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
                is_admin=user['is_admin']
            )

    @staticmethod
    def delete(user_id):
        with open(USERS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            users = json.load(f)
            users = [u for u in users if u['id'] != user_id]
            f.seek(0)
            json.dump(users, f, indent=2)
            f.truncate()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return True

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
            reset_token=u.get('reset_token'),
            reset_token_expiry=u.get('reset_token_expiry')
        ) for u in users]
