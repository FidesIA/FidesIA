"""
app.py - Serveur FastAPI pour FidesIA
Chatbot RAG Théologie Catholique
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import HOST, PORT, CORPUS_PATH, INVENTAIRE_PATH, OLLAMA_MODEL, RATE_LIMIT_PUBLIC
from database import (
    init_db, save_exchange, update_rating, get_exchange_owner,
    get_user_conversations, get_conversation_messages, delete_conversation,
)
from auth import (
    RegisterRequest, LoginRequest, AuthResponse, UserInfo,
    ForgotPasswordRequest, ResetPasswordRequest,
    register, login, forgot_password, reset_password,
    get_current_user, require_auth,
)
from rag import init_settings, init_index, query_stream, get_collection_stats
from saints import init_saints, get_saint_today, get_saint_by_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# === Security Headers Middleware ===

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# === Lifespan ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FidesIA démarrage...")
    init_db()
    init_settings()
    init_index()
    init_saints()
    logger.info("FidesIA prêt")
    yield
    logger.info("FidesIA arrêt")


app = FastAPI(title="FidesIA", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)

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
    question: str = Field(..., min_length=1, max_length=5000)
    conversation_id: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    chat_history: Optional[list] = None
    age_group: Optional[str] = Field(None, max_length=30)
    knowledge_level: Optional[str] = Field(None, max_length=30)
    response_length: Optional[str] = Field(None, max_length=30)


class ExchangeRequest(BaseModel):
    conversation_id: str = Field(..., max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    question: str = Field(..., max_length=5000)
    response: str = Field(..., max_length=50000)
    sources: Optional[list] = None
    age_group: Optional[str] = Field(None, max_length=30)
    knowledge_level: Optional[str] = Field(None, max_length=30)
    response_time_ms: Optional[int] = Field(0, ge=0, le=600000)


class RatingRequest(BaseModel):
    exchange_id: int = Field(..., gt=0)
    rating: int = Field(..., ge=1, le=5)


# === Auth Routes ===

@app.post("/auth/register", response_model=AuthResponse)
@limiter.limit("5/minute")
async def route_register(request: Request, req: RegisterRequest):
    return register(req.email, req.password, req.display_name)


@app.post("/auth/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def route_login(request: Request, req: LoginRequest):
    return login(req.email, req.password)


@app.get("/auth/check")
async def route_check(user: Optional[UserInfo] = Depends(get_current_user)):
    if user:
        return {"authenticated": True, "user_id": user.user_id, "display_name": user.display_name}
    return {"authenticated": False}


@app.post("/auth/logout")
async def route_logout(user: UserInfo = Depends(require_auth)):
    return {"success": True, "message": "Déconnexion réussie"}


@app.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def route_forgot_password(request: Request, req: ForgotPasswordRequest):
    return forgot_password(req.email)


@app.post("/auth/reset-password")
@limiter.limit("10/minute")
async def route_reset_password(request: Request, req: ResetPasswordRequest):
    return reset_password(req.token, req.password)


# === Chat / RAG ===

@app.post("/ask/stream")
@limiter.limit(RATE_LIMIT_PUBLIC)
async def ask_stream(request: Request, req: QuestionRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Question → réponse SSE streaming avec sources."""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question vide")

    # Limiter l'historique à 20 messages max
    chat_history = (req.chat_history or [])[:20]

    return StreamingResponse(
        query_stream(
            question=question,
            chat_history=chat_history if chat_history else None,
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
async def rate_exchange(req: RatingRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Note un échange. Vérifie que l'échange appartient à l'utilisateur/session."""
    owner = get_exchange_owner(req.exchange_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Échange non trouvé")

    # Vérifier l'appartenance : user connecté ou session anonyme
    if owner["user_id"] and user and owner["user_id"] == user.user_id:
        pass  # OK
    elif not owner["user_id"] and not user:
        pass  # Échange anonyme, accès public
    elif user and owner["user_id"] == user.user_id:
        pass  # OK
    else:
        raise HTTPException(status_code=403, detail="Accès interdit")

    update_rating(req.exchange_id, req.rating)
    return {"success": True}


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
        if not matches:
            raise HTTPException(status_code=404, detail="Fichier non trouvé")
        full_path = matches[0]

    # Re-vérifier path traversal (symlinks, rglob)
    try:
        full_path.resolve().relative_to(corpus_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Accès interdit")

    return FileResponse(
        str(full_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=\"{full_path.name}\""},
    )


# === Saints ===

@app.get("/api/saint-du-jour")
async def saint_du_jour():
    """Retourne le(s) saint(s) fêté(s) aujourd'hui."""
    return get_saint_today()


@app.get("/api/saint/{saint_id}")
async def saint_detail(saint_id: str):
    """Retourne les détails complets d'un saint."""
    saint = get_saint_by_id(saint_id)
    if not saint:
        raise HTTPException(status_code=404, detail="Saint non trouvé")
    return saint


# === Health ===

@app.get("/health")
async def health():
    stats = get_collection_stats()
    return {
        "status": "ok",
        "service": "FidesIA",
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
