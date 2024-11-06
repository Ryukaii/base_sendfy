import json
import os
import fcntl
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
    def __init__(self, id, username, password_hash, is_admin=False):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin

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
                is_admin=user.get('is_admin', False)
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
                is_admin=user.get('is_admin', False)
            )
        return None

    @staticmethod
    def create(username, password, is_admin=False):
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
                'is_admin': is_admin
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
            is_admin=u.get('is_admin', False)
        ) for u in users]
