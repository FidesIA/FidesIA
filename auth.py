"""
auth.py - Authentification pour TheologIA
Inscription email+password, login JWT, validation session.
"""

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException
from pydantic import BaseModel

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS
from database import create_user, get_user_by_email, get_user_by_id, update_last_login

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# === Modèles Pydantic ===

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    user_id: Optional[int] = None
    display_name: Optional[str] = None


class UserInfo(BaseModel):
    user_id: int
    email: str
    display_name: str


# === Helpers ===

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_jwt(user_id: int, email: str, display_name: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# === Registration & Login ===

def register(email: str, password: str, display_name: str) -> AuthResponse:
    email = email.strip().lower()
    display_name = display_name.strip()

    if not EMAIL_REGEX.match(email):
        return AuthResponse(success=False, message="Format d'email invalide")

    if len(password) < 6:
        return AuthResponse(success=False, message="Le mot de passe doit faire au moins 6 caractères")

    if not display_name or len(display_name) < 2:
        return AuthResponse(success=False, message="Le nom d'affichage doit faire au moins 2 caractères")

    existing = get_user_by_email(email)
    if existing:
        return AuthResponse(success=False, message="Un compte existe déjà avec cet email")

    password_h = hash_password(password)
    user_id = create_user(email, password_h, display_name)
    token = create_jwt(user_id, email, display_name)
    update_last_login(user_id)

    logger.info(f"Inscription: {email} (id={user_id})")
    return AuthResponse(
        success=True,
        message="Compte créé avec succès",
        token=token,
        user_id=user_id,
        display_name=display_name
    )


def login(email: str, password: str) -> AuthResponse:
    email = email.strip().lower()
    user = get_user_by_email(email)

    if not user or not verify_password(password, user["password_hash"]):
        return AuthResponse(success=False, message="Email ou mot de passe incorrect")

    token = create_jwt(user["id"], user["email"], user["display_name"])
    update_last_login(user["id"])

    logger.info(f"Login: {email}")
    return AuthResponse(
        success=True,
        message="Connexion réussie",
        token=token,
        user_id=user["id"],
        display_name=user["display_name"]
    )


# === Dépendances FastAPI ===

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[UserInfo]:
    """
    Extrait l'utilisateur du JWT. Retourne None si anonyme/invalide.
    Mode dégradé : pas d'erreur, juste None.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    payload = decode_jwt(authorization[7:])
    if not payload:
        return None

    return UserInfo(
        user_id=payload["user_id"],
        email=payload["email"],
        display_name=payload["display_name"]
    )


async def require_auth(authorization: Optional[str] = Header(None)) -> UserInfo:
    """Exige une authentification valide."""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user
