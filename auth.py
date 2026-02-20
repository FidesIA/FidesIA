"""
auth.py - Authentification pour FidesIA
Inscription email+password, login JWT (révocable), validation session.
"""

import hashlib
import re
import secrets
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException
from pydantic import BaseModel

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_DAYS, APP_URL, MIN_PASSWORD_LENGTH
from database import (
    create_user, get_user_by_email, get_user_by_id, update_last_login,
    save_reset_token, get_reset_token, delete_reset_token, update_user_password,
    blacklist_jwt, is_jwt_blacklisted,
)
from email_utils import send_reset_email

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
DISPLAY_NAME_REGEX = re.compile(r"^[\w\s\u00C0-\u024F'.-]+$")

# Hash factice pour prévenir les timing attacks sur login
_DUMMY_HASH = bcrypt.hashpw(b"dummy-timing-constant", bcrypt.gensalt(rounds=12)).decode()


def _mask_email(email: str) -> str:
    """Masque un email pour les logs RGPD : j***@e***.com"""
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    local = parts[0][0] + "***" if parts[0] else "***"
    domain_parts = parts[1].split(".")
    domain = domain_parts[0][0] + "***" if domain_parts[0] else "***"
    tld = domain_parts[-1] if len(domain_parts) > 1 else ""
    return f"{local}@{domain}.{tld}"


def _hash_token(token: str) -> str:
    """SHA-256 hash pour stocker les reset tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


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
    jti: Optional[str] = None
    exp: Optional[datetime] = None


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


def _validate_password(password: str) -> Optional[str]:
    """Valide la complexité du mot de passe. Retourne un message d'erreur ou None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères"
    if not re.search(r"[a-zA-Z]", password):
        return "Le mot de passe doit contenir au moins une lettre"
    if not re.search(r"\d", password):
        return "Le mot de passe doit contenir au moins un chiffre"
    return None


def _sanitize_display_name(name: str) -> str:
    """Nettoie le nom d'affichage (supprime les caractères dangereux)."""
    name = name.strip()
    name = re.sub(r"[<>&\"']", "", name)
    return name[:50]


def create_jwt(user_id: int, email: str, display_name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Vérifie la blacklist
        jti = payload.get("jti")
        if jti and is_jwt_blacklisted(jti):
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# === Registration & Login ===

def register(email: str, password: str, display_name: str) -> AuthResponse:
    email = email.strip().lower()
    display_name = _sanitize_display_name(display_name)

    if not EMAIL_REGEX.match(email):
        return AuthResponse(success=False, message="Format d'email invalide")

    pwd_error = _validate_password(password)
    if pwd_error:
        return AuthResponse(success=False, message=pwd_error)

    if not display_name or len(display_name) < 2 or len(display_name) > 50:
        return AuthResponse(success=False, message="Le nom d'affichage doit faire entre 2 et 50 caractères")

    if len(email) > 254:
        return AuthResponse(success=False, message="Adresse email trop longue")

    existing = get_user_by_email(email)
    if existing:
        # Message générique pour ne pas révéler l'existence du compte
        return AuthResponse(success=False, message="Impossible de créer le compte. Vérifiez vos informations ou connectez-vous.")

    password_h = hash_password(password)
    user_id = create_user(email, password_h, display_name)
    token = create_jwt(user_id, email, display_name)
    update_last_login(user_id)

    logger.info(f"Inscription: {_mask_email(email)} (id={user_id})")
    return AuthResponse(
        success=True,
        message="Compte créé avec succès",
        token=token,
        user_id=user_id,
        display_name=display_name,
    )


def login(email: str, password: str) -> AuthResponse:
    email = email.strip().lower()
    user = get_user_by_email(email)

    if not user:
        verify_password(password, _DUMMY_HASH)
        return AuthResponse(success=False, message="Email ou mot de passe incorrect")

    if not verify_password(password, user["password_hash"]):
        return AuthResponse(success=False, message="Email ou mot de passe incorrect")

    token = create_jwt(user["id"], user["email"], user["display_name"])
    update_last_login(user["id"])

    logger.info(f"Login: {_mask_email(email)}")
    return AuthResponse(
        success=True,
        message="Connexion réussie",
        token=token,
        user_id=user["id"],
        display_name=user["display_name"],
    )


# === Mot de passe oublié ===

def forgot_password(email: str) -> dict:
    """Génère un token de réinitialisation et envoie l'email. Retourne toujours succès."""
    email = email.strip().lower()
    user = get_user_by_email(email)

    if user:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        save_reset_token(user["id"], token_hash, expires_at)

        reset_url = f"{APP_URL}/reset-password.html?token={token}"
        send_reset_email(email, user["display_name"], reset_url)
        logger.info(f"Reset token généré pour {_mask_email(email)}")
    else:
        logger.info(f"Forgot password pour email inconnu")

    return {"success": True, "message": "Si cette adresse est enregistrée, un email a été envoyé."}


def reset_password(token: str, new_password: str) -> dict:
    """Réinitialise le mot de passe à partir d'un token valide."""
    pwd_error = _validate_password(new_password)
    if pwd_error:
        return {"success": False, "message": pwd_error}

    token_hash = _hash_token(token)
    token_data = get_reset_token(token_hash)
    if not token_data:
        return {"success": False, "message": "Lien invalide ou expiré"}

    expires_at = datetime.fromisoformat(token_data["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        delete_reset_token(token_hash)
        return {"success": False, "message": "Ce lien a expiré. Veuillez refaire une demande."}

    password_h = hash_password(new_password)
    update_user_password(token_data["user_id"], password_h)
    delete_reset_token(token_hash)

    logger.info(f"Mot de passe réinitialisé pour user_id={token_data['user_id']}")
    return {"success": True, "message": "Mot de passe modifié avec succès"}


# === Dépendances FastAPI ===

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[UserInfo]:
    if not authorization or not authorization.startswith("Bearer "):
        return None

    payload = decode_jwt(authorization[7:])
    if not payload:
        return None

    return UserInfo(
        user_id=payload["user_id"],
        email=payload["email"],
        display_name=payload["display_name"],
        jti=payload.get("jti"),
        exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
    )


async def require_auth(authorization: Optional[str] = Header(None)) -> UserInfo:
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
