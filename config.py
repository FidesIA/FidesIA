"""
config.py - Configuration centralisée pour FidesIA
Charge les variables d'environnement depuis .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === App ===
APP_VERSION = "1.1.0"

# === Chemins ===
BASE_DIR = Path(__file__).parent
CHROMA_PATH = BASE_DIR / os.getenv("CHROMA_PATH", "data/chroma_db")
CORPUS_PATH = BASE_DIR / os.getenv("CORPUS_PATH", "data/corpus")
INVENTAIRE_PATH = BASE_DIR / os.getenv("INVENTAIRE_PATH", "data/inventaire.json")
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/fidesia.db")

# === Ollama ===
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral-large-3:675b-cloud")

# === Embedding ===
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "OrdalieTech/Solon-embeddings-large-0.1")

# === JWT ===
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET manquant ou trop court (min 32 caractères). "
        "Générez-en un : python -c \"import secrets; print(secrets.token_hex(64))\""
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

# === SMTP ===
SMTP_HOST = os.getenv("SMTP_HOST", "")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
except ValueError:
    SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "FidesIA <noreply@fidesia.fr>")
APP_URL = os.getenv("APP_URL", "http://localhost:11438").rstrip("/")

# === Serveur ===
HOST = os.getenv("HOST", "0.0.0.0")
try:
    PORT = int(os.getenv("PORT", "11438"))
except ValueError:
    PORT = 11438

# === Auth ===
MIN_PASSWORD_LENGTH = 8
MAX_CHAT_HISTORY = 20

# === Admin ===
ADMIN_USERS = {e.strip().lower() for e in os.getenv("ADMIN_USERS", "").split(",") if e.strip()}

# === Rate limiting ===
RATE_LIMIT_WRITE = "30/minute"
RATE_LIMIT_READ = "60/minute"

# === RAG ===
SIMILARITY_TOP_K = 8
CONTEXT_TOP_K = 5
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200
LLM_TIMEOUT = 300.0
