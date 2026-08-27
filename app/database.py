from __future__ import annotations

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_settings(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def _ensure_user_lockout_columns() -> None:
    # create_all não adiciona colunas em tabelas já existentes; quem já tinha o
    # app instalado precisa ganhar essas colunas manualmente, sem perder dados.
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        if "failed_attempts" not in existing:
            connection.execute(text("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0"))
        if "locked_until" not in existing:
            connection.execute(text("ALTER TABLE users ADD COLUMN locked_until TIMESTAMP"))


def _ensure_invoice_classification_columns() -> None:
    inspector = inspect(engine)
    if "invoices" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("invoices")}
    with engine.begin() as connection:
        if "invoice_type" not in existing:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN invoice_type VARCHAR(20) NOT NULL DEFAULT 'FREIGHT'"))
        if "classification_confidence" not in existing:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN classification_confidence INTEGER NOT NULL DEFAULT 100"))


def create_database() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_user_lockout_columns()
    _ensure_invoice_classification_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

