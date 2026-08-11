import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

IS_VERCEL = bool(os.getenv("VERCEL"))

if IS_VERCEL:
    RUNTIME_DATA_DIR = Path("/tmp/civicai_data")
    RUNTIME_UPLOAD_DIR = Path("/tmp/civicai_uploads")
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Copy packaged seed JSON files into writable ephemeral storage once.
    packaged = BASE_DIR / "data"
    for filename in ["complaints.json", "users.json", "departments.json", "notifications.json", "analytics.json"]:
        source = packaged / filename
        target = RUNTIME_DATA_DIR / filename
        if source.exists() and not target.exists():
            try:
                shutil.copyfile(source, target)
            except OSError:
                pass
else:
    RUNTIME_DATA_DIR = BASE_DIR / "data"
    RUNTIME_UPLOAD_DIR = BASE_DIR / "static" / "uploads"
    RUNTIME_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-before-deployment")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6KYOm_LaEPEs_269l6S2MPxU2RWhsu11sKB-XVq5UZBtA")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    HF_TOKEN = os.getenv("HF_TOKEN", "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")
    HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    HF_CHAT_URL = os.getenv("HF_CHAT_URL", "https://router.huggingface.co/v1/chat/completions")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-this-password")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024
    UPLOAD_FOLDER = str(RUNTIME_UPLOAD_DIR)
    DATA_DIR = str(RUNTIME_DATA_DIR)
