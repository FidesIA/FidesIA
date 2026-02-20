"""
app.py - Serveur FastAPI pour FidesIA
Chatbot RAG Théologie Catholique
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import (
    HOST, PORT, CORPUS_PATH, INVENTAIRE_PATH, OLLAMA_MODEL,
    APP_VERSION, MAX_CHAT_HISTORY, RATE_LIMIT_WRITE, RATE_LIMIT_READ,
)
from database import (
    init_db, save_exchange, update_rating, get_exchange_owner,
    get_user_conversations, get_conversation_messages, delete_exchange, delete_conversation,
    check_conversation_owner, blacklist_jwt,
    cleanup_expired_tokens, cleanup_expired_blacklist,
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


# === Pure ASGI Security Headers Middleware ===

class SecurityHeadersMiddleware:
    """Pure ASGI middleware (no BaseHTTPMiddleware overhead)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy",
                     b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                     b"img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                     b"frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"x-permitted-cross-domain-policies", b"none"),
                ]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


# === Corpus Cache ===

class _CorpusCache:
    """Cache inventaire.json en mémoire avec TTL."""

    def __init__(self, ttl: int = 300):
        self._data = None
        self._loaded_at = 0.0
        self._ttl = ttl

    def get(self) -> list:
        now = time.monotonic()
        if self._data is not None and (now - self._loaded_at) < self._ttl:
            return self._data
        inv_path = Path(INVENTAIRE_PATH)
        if not inv_path.exists():
            self._data = []
        else:
            with open(inv_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        self._loaded_at = now
        return self._data


_corpus_cache = _CorpusCache(ttl=300)

# === PDF file index (avoid rglob on each request) ===
_pdf_index: dict[str, Path] = {}


def _build_pdf_index():
    """Index all PDF filenames → full paths at startup."""
    corpus_root = Path(CORPUS_PATH).resolve()
    if not corpus_root.exists():
        return
    for pdf in corpus_root.rglob("*.pdf"):
        _pdf_index[pdf.name] = pdf


# === Lifespan ===

@asynccontextmanager
_ready = False


async def lifespan(app: FastAPI):
    global _ready
    logger.info("FidesIA démarrage...")
    init_db()
    asyncio.get_event_loop().run_in_executor(None, _heavy_init)
    yield
    logger.info("FidesIA arrêt")


def _heavy_init():
    global _ready
    init_settings()
    init_index()
    init_saints()
    _build_pdf_index()
    _ready = True
    logger.info("FidesIA prêt")


app = FastAPI(title="FidesIA", version=APP_VERSION, lifespan=lifespan)
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

class ChatHistoryItem(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=10000)


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    conversation_id: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    chat_history: Optional[List[ChatHistoryItem]] = None
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
    session_id: Optional[str] = Field(None, max_length=100)


# === Auth Routes ===

@app.post("/auth/register", response_model=AuthResponse)
@limiter.limit("5/minute")
async def route_register(request: Request, req: RegisterRequest):
    return await asyncio.to_thread(register, req.email, req.password, req.display_name)


@app.post("/auth/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def route_login(request: Request, req: LoginRequest):
    return await asyncio.to_thread(login, req.email, req.password)


@app.get("/auth/check")
@limiter.limit(RATE_LIMIT_READ)
async def route_check(request: Request, user: Optional[UserInfo] = Depends(get_current_user)):
    if user:
        return {"authenticated": True, "user_id": user.user_id, "display_name": user.display_name}
    return {"authenticated": False}


@app.post("/auth/logout")
async def route_logout(user: UserInfo = Depends(require_auth)):
    # Blacklist le JWT pour un vrai logout
    if user.jti and user.exp:
        blacklist_jwt(user.jti, user.exp.isoformat())
    return {"success": True, "message": "Déconnexion réussie"}


@app.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def route_forgot_password(request: Request, req: ForgotPasswordRequest):
    return await asyncio.to_thread(forgot_password, req.email)


@app.post("/auth/reset-password")
@limiter.limit("10/minute")
async def route_reset_password(request: Request, req: ResetPasswordRequest):
    return await asyncio.to_thread(reset_password, req.token, req.password)


# === Chat / RAG ===

@app.post("/ask/stream")
@limiter.limit(RATE_LIMIT_WRITE)
async def ask_stream(request: Request, req: QuestionRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Question → réponse SSE streaming avec sources."""
    if not _ready:
        raise HTTPException(status_code=503, detail="Service en cours de chargement, veuillez patienter")
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question vide")

    chat_history = None
    if req.chat_history:
        chat_history = [{"role": m.role, "content": m.content} for m in req.chat_history[:MAX_CHAT_HISTORY]]

    return StreamingResponse(
        query_stream(
            question=question,
            chat_history=chat_history,
            age_group=req.age_group,
            knowledge_level=req.knowledge_level,
            response_length=req.response_length,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# === Conversations (connecté) ===

@app.post("/conversations/exchange")
@limiter.limit(RATE_LIMIT_WRITE)
async def save_exchange_route(request: Request, req: ExchangeRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Sauvegarde un échange Q/R (public ou connecté)."""
    session_id = f"user:{user.user_id}" if user else (req.session_id or str(uuid.uuid4()))
    user_id = user.user_id if user else None

    # IDOR fix: vérifier que la conversation appartient bien à l'utilisateur
    if user_id:
        existing = check_conversation_owner(req.conversation_id, user_id)
        # Autorise si c'est une nouvelle conversation OU si elle appartient à cet user
        if existing is False:
            # Vérifier si d'autres messages existent pour cette conv avec un AUTRE user
            from database import _db
            with _db() as conn:
                row = conn.execute(
                    "SELECT user_id FROM exchanges WHERE conversation_id = ? AND user_id IS NOT NULL LIMIT 1",
                    (req.conversation_id,),
                ).fetchone()
                if row and row["user_id"] != user_id:
                    raise HTTPException(status_code=403, detail="Accès interdit à cette conversation")

    exchange_id = await asyncio.to_thread(
        save_exchange,
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
@limiter.limit(RATE_LIMIT_READ)
async def list_conversations(request: Request, user: UserInfo = Depends(require_auth)):
    return await asyncio.to_thread(get_user_conversations, user.user_id)


@app.get("/conversations/{conv_id}/messages")
@limiter.limit(RATE_LIMIT_READ)
async def get_messages(request: Request, conv_id: str, user: UserInfo = Depends(require_auth)):
    return await asyncio.to_thread(get_conversation_messages, conv_id, user_id=user.user_id)


@app.delete("/exchanges/{exchange_id}")
@limiter.limit(RATE_LIMIT_WRITE)
async def delete_exchange_route(request: Request, exchange_id: int, user: UserInfo = Depends(require_auth)):
    """Supprime un échange individuel (soft delete)."""
    owner = await asyncio.to_thread(get_exchange_owner, exchange_id)
    if not owner or owner["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Accès interdit")
    await asyncio.to_thread(delete_exchange, exchange_id, user.user_id)
    return {"success": True}


@app.delete("/conversations/{conv_id}")
@limiter.limit(RATE_LIMIT_WRITE)
async def delete_conv(request: Request, conv_id: str, user: UserInfo = Depends(require_auth)):
    await asyncio.to_thread(delete_conversation, conv_id, user.user_id)
    return {"success": True}


# === Rating ===

@app.post("/rate")
@limiter.limit(RATE_LIMIT_WRITE)
async def rate_exchange(request: Request, req: RatingRequest, user: Optional[UserInfo] = Depends(get_current_user)):
    """Note un échange. Vérifie l'appartenance."""
    owner = await asyncio.to_thread(get_exchange_owner, req.exchange_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Échange non trouvé")

    if user and owner["user_id"] and owner["user_id"] == user.user_id:
        pass  # Utilisateur connecté, son propre échange
    elif not owner["user_id"] and not user and req.session_id and owner["session_id"] == req.session_id:
        pass  # Échange anonyme, même session
    elif not owner["user_id"] and user:
        pass  # User connecté note un échange qui n'avait pas de user (transition)
    else:
        raise HTTPException(status_code=403, detail="Accès interdit")

    await asyncio.to_thread(update_rating, req.exchange_id, req.rating)
    return {"success": True}


# === Corpus ===

@app.get("/corpus")
@limiter.limit(RATE_LIMIT_READ)
async def get_corpus(request: Request):
    """Retourne l'inventaire du corpus (cached)."""
    return _corpus_cache.get()


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

    # Chercher dans l'index pré-construit si pas trouvé directement
    if not full_path.exists() or not full_path.is_file():
        filename = Path(file_path).name
        indexed_path = _pdf_index.get(filename)
        if not indexed_path or not indexed_path.exists():
            raise HTTPException(status_code=404, detail="Fichier non trouvé")
        full_path = indexed_path

    # Re-vérifier path traversal
    try:
        full_path.resolve().relative_to(corpus_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Accès interdit")

    return FileResponse(
        str(full_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{full_path.name}\"",
            "Cache-Control": "public, max-age=86400",
        },
    )


# === Saints ===

@app.get("/api/saint-du-jour")
@limiter.limit(RATE_LIMIT_READ)
async def saint_du_jour(request: Request):
    """Retourne le(s) saint(s) fêté(s) aujourd'hui."""
    return get_saint_today()


@app.get("/api/saint/{saint_id}")
@limiter.limit(RATE_LIMIT_READ)
async def saint_detail(request: Request, saint_id: str):
    """Retourne les détails complets d'un saint."""
    saint = get_saint_by_id(saint_id)
    if not saint:
        raise HTTPException(status_code=404, detail="Saint non trouvé")
    return saint


# === Health ===

@app.get("/health")
async def health():
    if not _ready:
        return {"status": "loading", "service": "FidesIA", "version": APP_VERSION}
    stats = get_collection_stats()
    return {
        "status": "ok",
        "service": "FidesIA",
        "version": APP_VERSION,
        **stats,
    }


# === Cleanup (tokens/blacklist expirés) ===

@app.post("/admin/cleanup")
async def admin_cleanup(user: UserInfo = Depends(require_auth)):
    """Nettoyage des tokens expirés (admin seulement pour l'instant)."""
    await asyncio.to_thread(cleanup_expired_tokens)
    await asyncio.to_thread(cleanup_expired_blacklist)
    return {"success": True, "message": "Nettoyage effectué"}


# === Static Files (SPA) ===
# Monté en dernier pour ne pas cacher les routes API
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
