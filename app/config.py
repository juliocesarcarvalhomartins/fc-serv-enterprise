from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "FC SERV Enterprise BETA"
APP_VERSION = "5.0.0-beta.1"
LEGACY_DATA_DIR_NAME = "Fatura Control Pro"


def _default_data_dir() -> Path:
    override = os.getenv("FATURA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home())
        # Mantém o diretório antigo para preservar banco, usuários, backups e chaves.
        return base / LEGACY_DATA_DIR_NAME
    return Path.home() / ".fatura-control-pro"


DATA_DIR = _default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "fatura_control.db"
SECRET_KEY_PATH = DATA_DIR / "secret.key"
EXPORT_DIR = DATA_DIR / "Exportações"
BACKUP_DIR = DATA_DIR / "Backups"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH.as_posix()}")
SESSION_HOURS = int(os.getenv("FATURA_SESSION_HOURS", "12"))
COOKIE_SECURE = os.getenv("FATURA_COOKIE_SECURE", "0") == "1"
LOGIN_MAX_ATTEMPTS = int(os.getenv("FATURA_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("FATURA_LOGIN_LOCKOUT_MINUTES", "15"))

OWNER_USERNAME = os.getenv("FC_SERV_OWNER_USERNAME", "jcz").strip().lower()
OWNER_INITIAL_PASSWORD = os.getenv("FC_SERV_OWNER_PASSWORD", "")
