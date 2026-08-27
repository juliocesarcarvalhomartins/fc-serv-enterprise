from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(120), default="desconhecido", index=True)
    action: Mapped[str] = mapped_column(String(180), index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int] = mapped_column(Integer)
    ip_address: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(30), default="outlook")
    imap_host: Mapped[str] = mapped_column(String(180))
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    username: Mapped[str] = mapped_column(String(180), unique=True)
    encrypted_password: Mapped[str] = mapped_column(Text)
    unread_only: Mapped[bool] = mapped_column(Boolean, default=True)
    days_back: Mapped[int] = mapped_column(Integer, default=30)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("carrier_key", "normalized_number", name="uq_invoice_carrier_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier: Mapped[str] = mapped_column(String(120), index=True)
    carrier_key: Mapped[str] = mapped_column(String(120), index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), index=True)
    normalized_number: Mapped[str] = mapped_column(String(100), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    inclusion_date: Mapped[date] = mapped_column(Date, default=date.today)
    gko_released: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    save_posted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    situation_gko: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(30), default="manual")
    invoice_type: Mapped[str] = mapped_column(String(20), default="FREIGHT", index=True)
    classification_confidence: Mapped[int] = mapped_column(Integer, default=100)
    source_email: Mapped[str] = mapped_column(String(180), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    message_id: Mapped[str | None] = mapped_column(String(400), nullable=True, index=True)
    email_account_id: Mapped[int | None] = mapped_column(ForeignKey("email_accounts.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"
    __table_args__ = (UniqueConstraint("email_account_id", "message_id", name="uq_processed_email_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_account_id: Mapped[int | None] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id: Mapped[str] = mapped_column(String(500), index=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    sender: Mapped[str] = mapped_column(String(300), default="")
    processing_status: Mapped[str] = mapped_column(String(30), default="IMPORTED", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class InvoiceHistory(Base):
    __tablename__ = "invoice_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(120), default="sistema")
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class InvoiceAttachment(Base):
    __tablename__ = "invoice_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    storage_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
