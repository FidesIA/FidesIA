"""
config.py - Configuration centralisée pour TheologIA
Charge les variables d'environnement depuis .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === Chemins ===
BASE_DIR = Path(__file__).parent
CHROMA_PATH = BASE_DIR / os.getenv("CHROMA_PATH", "data/chroma_db")
CORPUS_PATH = BASE_DIR / os.getenv("CORPUS_PATH", "data/corpus")
INVENTAIRE_PATH = BASE_DIR / os.getenv("INVENTAIRE_PATH", "data/inventaire.json")
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/theologIA.db")

# === Ollama ===
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral-large-3:675b-cloud")

# === Embedding ===
EMBEDDING_MODEL = "OrdalieTech/Solon-embeddings-large-0.1"
EMBEDDING_DIM = 1024

# === JWT ===
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

# === Serveur ===
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "11438"))

# === Rate limiting ===
RATE_LIMIT_PUBLIC = "20/minute"
RATE_LIMIT_CONNECTED = "60/minute"

# === RAG ===
SIMILARITY_TOP_K = 8       # Retrieval large
CONTEXT_TOP_K = 5           # Envoyé au LLM après rerank
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200
LLM_TIMEOUT = 300.0         # 5 minutes
