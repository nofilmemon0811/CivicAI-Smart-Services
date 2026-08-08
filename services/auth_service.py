from pathlib import Path
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from utils.json_database import JSONDatabase
from config import Config


class AuthService:
    """Small JSON-backed authentication service for the hackathon demo."""

    def __init__(self):
        path = Path(Config.DATA_DIR) / "users.json"
        self.db = JSONDatabase(str(path), [])
        self._ensure_admin()
        self._ensure_demo_citizen()

    def _ensure_admin(self):
        username = Config.ADMIN_USERNAME.lower().strip()
        existing = self.db.find(username, "username")
        if not existing:
            self.db.add({
                "username": username,
                "name": "CivicAI Administrator",
                "email": "admin@civicai.local",
                "password_hash": generate_password_hash(Config.ADMIN_PASSWORD),
                "role": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        elif not existing.get("password_hash"):
            existing["password_hash"] = generate_password_hash(Config.ADMIN_PASSWORD)
            existing["role"] = "admin"
            self.db.update(username, existing, "username")

    def _ensure_demo_citizen(self):
        existing = self.db.find("citizen", "username")
        if not existing:
            self.db.add({
                "username": "citizen",
                "name": "Demo Citizen",
                "email": "citizen@civicai.local",
                "password_hash": generate_password_hash("civic123"),
                "role": "citizen",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        elif not existing.get("password_hash"):
            existing["password_hash"] = generate_password_hash("civic123")
            existing["role"] = "citizen"
            self.db.update("citizen", existing, "username")

    def get_user(self, username):
        if not username:
            return None
        return self.db.find(username.lower().strip(), "username")

    def authenticate(self, username, password):
        user = self.get_user(username)
        if not user:
            return None
        if not check_password_hash(user.get("password_hash", ""), password):
            return None
        return user

    def register(self, username, name, email, password):
        username = username.lower().strip()
        email = email.lower().strip()

        if not username or not name or not email or not password:
            raise ValueError("All fields are required.")
        if len(username) < 3:
            raise ValueError("Username must contain at least 3 characters.")
        if not username.replace("_", "").isalnum():
            raise ValueError("Username may contain letters, numbers and underscores only.")
        if len(password) < 6:
            raise ValueError("Password must contain at least 6 characters.")
        if self.get_user(username):
            raise ValueError("That username is already registered.")

        for existing in self.db.get_all():
            if existing.get("email", "").lower() == email:
                raise ValueError("That email is already registered.")

        user = {
            "username": username,
            "name": name.strip()[:80],
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": "citizen",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.add(user)
        return user
