from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SetupInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class LoginInput(BaseModel):
    username: str
    password: str


class UserInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class InvoiceInput(BaseModel):
    carrier: str = Field(min_length=1, max_length=120)
    invoice_number: str = Field(min_length=1, max_length=100)
    due_date: date | None = None
    amount: Decimal | None = None
    situation_gko: str = ""
    notes: str = ""


class InvoiceUpdateInput(BaseModel):
    carrier: str = Field(min_length=1, max_length=120)
    invoice_number: str = Field(min_length=1, max_length=100)
    due_date: date | None = None
    amount: Decimal | None = None
    notes: str = ""


class ToggleInput(BaseModel):
    value: bool


class EmailAccountInput(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    provider: str = "outlook"
    imap_host: str = Field(min_length=3, max_length=180)
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(min_length=3, max_length=180)
    password: str = Field(default="", max_length=500)
    unread_only: bool = True
    days_back: int = Field(default=30, ge=1, le=365)
    active: bool = True
