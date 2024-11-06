from models.users import User

def init_admin():
    # Check if any admin user exists
    users = User.get_all()
    admin_exists = any(user.is_admin for user in users)
    
    if not admin_exists:
        # Create default admin user
        admin = User.create(
            username="admin",
            password="admin123",
            is_admin=True
        )
        if admin:
            print("Default admin user created:")
            print("Username: admin")
            print("Password: admin123")
            print("Please change the password after first login!")
        else:
            print("Failed to create admin user")
    else:
        print("Admin user already exists")

if __name__ == "__main__":
    init_admin()
