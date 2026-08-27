from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import LOGIN_LOCKOUT_MINUTES, LOGIN_MAX_ATTEMPTS, SECRET_KEY_PATH, SESSION_HOURS
from .database import get_db
from .models import Session as UserSession, User


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = stored.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _fernet() -> Fernet:
    if SECRET_KEY_PATH.exists():
        key = SECRET_KEY_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        SECRET_KEY_PATH.write_bytes(key)
        try:
            SECRET_KEY_PATH.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


def lockout_remaining_seconds(user: User) -> int:
    """Segundos restantes de bloqueio; 0 se o usuário não está bloqueado."""
    if not user.locked_until:
        return 0
    remaining = (user.locked_until - utc_now()).total_seconds()
    return max(0, int(remaining))


def register_failed_login(db: Session, user: User) -> None:
    user.failed_attempts += 1
    if user.failed_attempts >= LOGIN_MAX_ATTEMPTS:
        user.locked_until = utc_now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        user.failed_attempts = 0
    db.commit()


def register_successful_login(db: Session, user: User) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = utc_now()
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.add(UserSession(token_hash=token_hash, user_id=user.id, expires_at=now + timedelta(hours=SESSION_HOURS)))
    db.commit()
    return token


def destroy_session(db: Session, token: str | None) -> None:
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    db.commit()


def current_user(
    fatura_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not fatura_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Faça login para continuar.")
    token_hash = hashlib.sha256(fatura_session.encode()).hexdigest()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash, UserSession.expires_at > utc_now()))
    if not session or not session.user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida ou expirada.")
    return session.user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso permitido somente à administração.")
    return user


def owner_user(user: User = Depends(current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Área exclusiva do proprietário.")
    return user
