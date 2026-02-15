"""
app.py - Serveur FastAPI pour TheologIA
Chatbot RAG Théologie Catholique
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

from config import HOST, PORT, CORPUS_PATH, INVENTAIRE_PATH, OLLAMA_MODEL, RATE_LIMIT_PUBLIC, RATE_LIMIT_CONNECTED
from database import init_db, save_exchange, update_rating, get_user_conversations, get_conversation_messages, delete_conversation
from auth import (
    RegisterRequest, LoginRequest, AuthResponse, UserInfo,
    register, login, get_current_user, require_auth,
)
from rag import init_settings, init_index, query_stream, get_collection_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# === Lifespan ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TheologIA démarrage...")
    init_db()
    init_settings()
    init_index()
    logger.info("TheologIA prêt")
    yield
    logger.info("TheologIA arrêt")


app = FastAPI(title="TheologIA", version="1.0.0", lifespan=lifespan)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Trop de requêtes. Veuillez patienter."},
    )


# === Modèles Pydantic ===

class QuestionRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    chat_history: Optional[list] = None
    age_group: Optional[str] = None
    knowledge_level: Optional[str] = None
    response_length: Optional[str] = None


class ExchangeRequest(BaseModel):
    conversation_id: str
    session_id: Optional[str] = None
    question: str
    response: str
    sources: Optional[list] = None
    age_group: Optional[str] = None
    knowledge_level: Optional[str] = None
    response_time_ms: Optional[int] = 0


class RatingRequest(BaseModel):
    exchange_id: int
    rating: int


# === Auth Routes ===

@app.post("/auth/register", response_model=AuthResponse)
async def route_register(req: RegisterRequest):
    return register(req.email, req.password, req.display_name)


@app.post("/auth/login", response_model=AuthResponse)
async def route_login(req: LoginRequest):
    return login(req.email, req.password)


@app.get("/auth/check")
async def route_check(user: Optional[UserInfo] = Depends(get_current_user)):
    if user:
        return {"authenticated": True, "user_id": user.user_id, "display_name": user.display_name}
    return {"authenticated": False}


@app.post("/auth/logout")
async def route_logout(user: UserInfo = Depends(require_auth)):
    return {"success": True, "message": "Déconnexion réussie"}


# === Chat / RAG ===

@app.post("/ask/stream")
@limiter.limit(RATE_LIMIT_CONNECTED)
async def ask_stream(request: Request, req: QuestionRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Question → réponse SSE streaming avec sources."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question vide")

    return StreamingResponse(
        query_stream(
            question=req.question,
            chat_history=req.chat_history,
            age_group=req.age_group,
            knowledge_level=req.knowledge_level,
            response_length=req.response_length,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# === Conversations (connecté) ===

@app.post("/conversations/exchange")
async def save_exchange_route(req: ExchangeRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Sauvegarde un échange Q/R (public ou connecté)."""
    session_id = f"user:{user.user_id}" if user else (req.session_id or str(uuid.uuid4()))
    user_id = user.user_id if user else None

    exchange_id = save_exchange(
        session_id=session_id,
        conversation_id=req.conversation_id,
        question=req.question,
        response=req.response,
        user_id=user_id,
        sources=req.sources,
        age_group=req.age_group,
        knowledge_level=req.knowledge_level,
        response_time_ms=req.response_time_ms,
        model=OLLAMA_MODEL,
    )
    return {"success": True, "exchange_id": exchange_id}


@app.get("/conversations")
async def list_conversations(user: UserInfo = Depends(require_auth)):
    return get_user_conversations(user.user_id)


@app.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, user: UserInfo = Depends(require_auth)):
    return get_conversation_messages(conv_id, user_id=user.user_id)


@app.delete("/conversations/{conv_id}")
async def delete_conv(conv_id: str, user: UserInfo = Depends(require_auth)):
    delete_conversation(conv_id, user.user_id)
    return {"success": True}


# === Rating ===

@app.post("/rate")
async def rate_exchange(req: RatingRequest):
    """Note un échange (public ou connecté)."""
    try:
        update_rating(req.exchange_id, req.rating)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Corpus ===

@app.get("/corpus")
async def get_corpus():
    """Retourne l'inventaire du corpus."""
    inv_path = Path(INVENTAIRE_PATH)
    if not inv_path.exists():
        return []
    with open(inv_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/corpus/file/{file_path:path}")
async def serve_corpus_file(file_path: str):
    """Sert un PDF du corpus (ouverture inline dans le navigateur)."""
    corpus_root = Path(CORPUS_PATH).resolve()
    full_path = corpus_root / file_path

    # Protection path traversal
    try:
        full_path.resolve().relative_to(corpus_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Accès interdit")

    # Si pas trouvé directement, chercher récursivement par nom de fichier
    if not full_path.exists() or not full_path.is_file():
        filename = Path(file_path).name
        matches = list(corpus_root.rglob(filename))
        if matches:
            full_path = matches[0]
        else:
            raise HTTPException(status_code=404, detail="Fichier non trouvé")

    return FileResponse(
        str(full_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=\"{full_path.name}\""},
    )


# === Health ===

@app.get("/health")
async def health():
    stats = get_collection_stats()
    return {
        "status": "ok",
        "service": "TheologIA",
        "version": "1.0.0",
        **stats,
    }


# === Static Files (SPA) ===
# Monté en dernier pour ne pas cacher les routes API
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
