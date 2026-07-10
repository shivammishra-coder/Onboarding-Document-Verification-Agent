"""
Central place for environment-driven settings, loaded from .env via python-dotenv.
Mirrors the original Node backend's use of process.env.
"""
import os
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PORT", "5000"))
JWT_SECRET = os.getenv("JWT_SECRET", "change_this_to_a_long_random_string")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_IN_HOURS = float(os.getenv("JWT_EXPIRES_IN_HOURS", "8"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(DATA_DIR, "db.json")

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15MB, matches fraud-check upper bound
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://aimodels.jadeglobal.com:8082")
OLLAMA_USERNAME = os.getenv("OLLAMA_USERNAME", "")
OLLAMA_PASSWORD = os.getenv("OLLAMA_PASSWORD", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")