"""
auth.py - Authentification pour FidesIA
Inscription email+password, login JWT, validation session.
"""

import re
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException
from pydantic import BaseModel

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS, APP_URL
from database import (
    create_user, get_user_by_email, get_user_by_id, update_last_login,
    save_reset_token, get_reset_token, delete_reset_token, update_user_password,
)
from email_utils import send_reset_email

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Hash factice pour prévenir les timing attacks sur login
_DUMMY_HASH = bcrypt.hashpw(b"dummy-timing-constant", bcrypt.gensalt(rounds=12)).decode()


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


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


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

    if not display_name or len(display_name) < 2 or len(display_name) > 50:
        return AuthResponse(success=False, message="Le nom d'affichage doit faire entre 2 et 50 caractères")

    if len(email) > 254:
        return AuthResponse(success=False, message="Adresse email trop longue")

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

    if not user:
        # Appel bcrypt factice pour prévenir la timing attack
        verify_password(password, _DUMMY_HASH)
        return AuthResponse(success=False, message="Email ou mot de passe incorrect")

    if not verify_password(password, user["password_hash"]):
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


# === Mot de passe oublié ===

def forgot_password(email: str) -> dict:
    """Génère un token de réinitialisation et envoie l'email. Retourne toujours succès."""
    email = email.strip().lower()
    user = get_user_by_email(email)

    if user:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        save_reset_token(user["id"], token, expires_at)

        reset_url = f"{APP_URL}/reset-password.html?token={token}"
        send_reset_email(email, user["display_name"], reset_url)
        logger.info(f"Reset token généré pour {email}")
    else:
        logger.info(f"Forgot password pour email inconnu: {email}")

    return {"success": True, "message": "Si cette adresse est enregistrée, un email a été envoyé."}


def reset_password(token: str, new_password: str) -> dict:
    """Réinitialise le mot de passe à partir d'un token valide."""
    if len(new_password) < 6:
        return {"success": False, "message": "Le mot de passe doit faire au moins 6 caractères"}

    token_data = get_reset_token(token)
    if not token_data:
        return {"success": False, "message": "Lien invalide ou expiré"}

    expires_at = datetime.fromisoformat(token_data["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        delete_reset_token(token)
        return {"success": False, "message": "Ce lien a expiré. Veuillez refaire une demande."}

    password_h = hash_password(new_password)
    update_user_password(token_data["user_id"], password_h)
    delete_reset_token(token)

    logger.info(f"Mot de passe réinitialisé pour user_id={token_data['user_id']}")
    return {"success": True, "message": "Mot de passe modifié avec succès"}


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
