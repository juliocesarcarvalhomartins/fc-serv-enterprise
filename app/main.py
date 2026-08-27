from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import APP_NAME, APP_VERSION, BACKUP_DIR, COOKIE_SECURE, SESSION_HOURS, OWNER_USERNAME, OWNER_INITIAL_PASSWORD
from .database import SessionLocal, create_database, get_db
from .models import AuditLog, EmailAccount, Invoice, Session as UserSession, User
from .schemas import EmailAccountInput, InvoiceInput, InvoiceUpdateInput, LoginInput, SetupInput, ToggleInput, UserInput
from .security import (
    admin_user, owner_user, create_session, current_user, destroy_session, encrypt_secret,
    hash_password, lockout_remaining_seconds, register_failed_login,
    register_successful_login, verify_password,
)
from .services.email_service import fetch_invoices, fetch_outlook_desktop, friendly_email_error, test_connection, test_outlook_desktop, open_outlook_message
from .services.excel_service import export_workbook, import_workbook
from .services.invoice_rules import carrier_key, normalize_invoice_number


OUTLOOK_LOCAL_PROVIDERS = {"outlook", "outlook_desktop"}


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


STATIC_DIR = resource_path("app/static")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_database()
    db = SessionLocal()
    try:
        owner = db.scalar(select(User).where(User.username == OWNER_USERNAME))
        if not owner and (db.scalar(select(func.count(User.id))) or 0) == 0:
            if not OWNER_INITIAL_PASSWORD:
                raise RuntimeError("Defina FC_SERV_OWNER_PASSWORD com pelo menos 8 caracteres antes da primeira execução.")
            owner = User(name="JCZ - Proprietário", username=OWNER_USERNAME, password_hash=hash_password(OWNER_INITIAL_PASSWORD), role="owner", active=True)
            db.add(owner)
            db.commit()
            db.refresh(owner)
            db.add(AuditLog(user_id=owner.id, username=owner.username, action="Conta proprietária inicial criada", method="SYSTEM", path="startup", status_code=200, ip_address="local", user_agent="FC SERV 5.0 BETA"))
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def audit_action(method: str, path: str) -> str:
    if path == "/api/logout": return "Saiu do sistema"
    if path == "/api/excel/import": return "Importou uma planilha"
    if path == "/api/excel/replace": return "Substituiu os dados da planilha Excel"
    if path == "/api/excel/imported": return "Removeu os dados importados do Excel"
    if path == "/api/email/sync": return "Buscou faturas nos e-mails"
    if path.startswith("/api/email-accounts"):
        if path.endswith("/test"): return "Testou uma conta de e-mail"
        return {"POST": "Adicionou uma conta de e-mail", "PUT": "Editou uma conta de e-mail", "DELETE": "Excluiu uma conta de e-mail"}.get(method, "Alterou uma conta de e-mail")
    if path.startswith("/api/users"):
        return "Criou um usuário" if method == "POST" else "Alterou o acesso de um usuário"
    if path.startswith("/api/invoices"):
        if path.endswith("/gko"): return "Alterou o status GKO"
        if path.endswith("/save"): return "Alterou o status SAVE"
        return "Cadastrou uma fatura" if method == "POST" else "Excluiu uma fatura"
    return f"{method} {path}"


def request_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@app.middleware("http")
async def audit_mutations(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith("/api/") and path not in {"/api/login", "/api/setup"}:
        db = SessionLocal()
        try:
            user = None
            token = request.cookies.get("fatura_session")
            if token:
                import hashlib
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
                user = session.user if session else None
            db.add(AuditLog(
                user_id=user.id if user else None,
                username=user.username if user else "não autenticado",
                action=audit_action(request.method, path), method=request.method, path=path,
                status_code=response.status_code, ip_address=request_ip(request),
                user_agent=(request.headers.get("user-agent") or "")[:500],
            ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    return response


def clean_username(value: str) -> str:
    return value.strip().lower()


def invoice_dict(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "carrier": invoice.carrier,
        "invoice_number": invoice.invoice_number,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "amount": float(invoice.amount) if invoice.amount is not None else None,
        "inclusion_date": invoice.inclusion_date.isoformat(),
        "gko_released": invoice.gko_released,
        "save_posted": invoice.save_posted,
        "status": invoice.status,
        "situation_gko": invoice.situation_gko,
        "notes": invoice.notes,
        "source": invoice.source,
        "invoice_type": invoice.invoice_type,
        "classification_confidence": invoice.classification_confidence,
        "source_email": invoice.source_email,
        "subject": invoice.subject,
        "message_id": invoice.message_id,
        "has_source_email": bool(invoice.message_id or invoice.subject),
        "created_at": invoice.created_at.isoformat(),
    }


def account_dict(account: EmailAccount) -> dict:
    last_error = account.last_error
    if last_error and "lookup failed" in last_error.lower():
        last_error = friendly_email_error(RuntimeError(last_error), account)
    return {
        "id": account.id,
        "label": account.label,
        "provider": account.provider,
        "imap_host": account.imap_host,
        "imap_port": account.imap_port,
        "username": account.username,
        "password_configured": bool(account.encrypted_password) and account.provider not in OUTLOOK_LOCAL_PROVIDERS,
        "connection_type": "outlook_local" if account.provider in OUTLOOK_LOCAL_PROVIDERS else "imap",
        "unread_only": account.unread_only,
        "days_back": account.days_back,
        "active": account.active,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "last_error": last_error,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(
        STATIC_DIR / "fc-serv-logo.ico",
        media_type="image/x-icon",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/health")
def health():
    return {"ok": True, "name": APP_NAME, "version": APP_VERSION}


@app.get("/api/setup/status")
def setup_status(db: Session = Depends(get_db)):
    return {"required": (db.scalar(select(func.count(User.id))) or 0) == 0}


@app.post("/api/setup")
def setup(payload: SetupInput, response: Response, request: Request, db: Session = Depends(get_db)):
    if (db.scalar(select(func.count(User.id))) or 0) > 0:
        raise HTTPException(status_code=409, detail="A conta proprietária inicial já foi criada.")
    user = User(
        name=payload.name.strip(),
        username=clean_username(payload.username),
        password_hash=hash_password(payload.password),
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(AuditLog(user_id=user.id, username=user.username, action="Criou a conta proprietária", method="POST", path="/api/setup", status_code=200, ip_address=request_ip(request), user_agent=(request.headers.get("user-agent") or "")[:500]))
    token = create_session(db, user)
    response.set_cookie("fatura_session", token, httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=SESSION_HOURS * 3600)
    return {"ok": True, "user": {"id": user.id, "name": user.name, "username": user.username, "role": user.role}}


@app.post("/api/login")
def login(payload: LoginInput, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == clean_username(payload.username)))

    if user:
        remaining = lockout_remaining_seconds(user)
        if remaining > 0:
            db.add(AuditLog(user_id=user.id, username=user.username, action="Login bloqueado temporariamente", method="POST", path="/api/login", status_code=429, ip_address=request_ip(request), user_agent=(request.headers.get("user-agent") or "")[:500]))
            db.commit()
            minutes = max(1, (remaining + 59) // 60)
            raise HTTPException(status_code=429, detail=f"Muitas tentativas erradas. Tente novamente em {minutes} minuto(s).")

    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        if user and user.active:
            register_failed_login(db, user)
        db.add(AuditLog(user_id=user.id if user else None, username=clean_username(payload.username), action="Tentativa de login recusada", method="POST", path="/api/login", status_code=401, ip_address=request_ip(request), user_agent=(request.headers.get("user-agent") or "")[:500]))
        db.commit()
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
    register_successful_login(db, user)
    db.add(AuditLog(user_id=user.id, username=user.username, action="Entrou no sistema", method="POST", path="/api/login", status_code=200, ip_address=request_ip(request), user_agent=(request.headers.get("user-agent") or "")[:500]))
    token = create_session(db, user)
    response.set_cookie("fatura_session", token, httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=SESSION_HOURS * 3600)
    return {"ok": True, "user": {"id": user.id, "name": user.name, "username": user.username, "role": user.role}}


@app.post("/api/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    destroy_session(db, request.cookies.get("fatura_session"))
    response.delete_cookie("fatura_session")
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "username": user.username, "role": user.role}


@app.get("/api/dashboard")
def dashboard(_user: User = Depends(current_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Invoice.id))) or 0
    pending = db.scalar(select(func.count(Invoice.id)).where(Invoice.save_posted.is_(False))) or 0
    completed = db.scalar(select(func.count(Invoice.id)).where(Invoice.save_posted.is_(True))) or 0
    gko_pending = db.scalar(select(func.count(Invoice.id)).where(Invoice.gko_released.is_(False), Invoice.save_posted.is_(False))) or 0
    return {"total": total, "pending": pending, "completed": completed, "gko_pending": gko_pending}


@app.get("/api/invoices")
def list_invoices(
    bucket: str = Query(default="pending", pattern="^(pending|completed|all)$"),
    search: str = "",
    invoice_type: str = Query(default="FREIGHT", pattern="^(FREIGHT|SERVICE|REVIEW|ALL)$"),
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Invoice)
    if invoice_type != "ALL":
        query = query.where(Invoice.invoice_type == invoice_type)
    if bucket == "pending":
        query = query.where(Invoice.save_posted.is_(False))
    elif bucket == "completed":
        query = query.where(Invoice.save_posted.is_(True))
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(or_(Invoice.carrier.ilike(term), Invoice.invoice_number.ilike(term), Invoice.source_email.ilike(term)))
    invoices = db.scalars(query.order_by(Invoice.created_at.desc()).limit(2000)).all()
    return [invoice_dict(item) for item in invoices]




@app.get("/api/invoices/monthly-summary")
def monthly_summary(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    month: int = Query(default=date.today().month, ge=1, le=12),
    carrier: str = "",
    status: str = "all",
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Invoice).where(func.extract("year", Invoice.inclusion_date) == year, func.extract("month", Invoice.inclusion_date) == month)
    if carrier.strip():
        query = query.where(Invoice.carrier.ilike(f"%{carrier.strip()}%"))
    if status == "pending":
        query = query.where(Invoice.save_posted.is_(False))
    elif status == "completed":
        query = query.where(Invoice.save_posted.is_(True))
    invoices = db.scalars(query.order_by(Invoice.inclusion_date.desc(), Invoice.created_at.desc()).limit(5000)).all()
    total_amount = sum(float(i.amount or 0) for i in invoices)
    completed = sum(1 for i in invoices if i.save_posted)
    overdue = sum(1 for i in invoices if i.due_date and i.due_date < date.today() and not i.save_posted)
    return {
        "year": year, "month": month, "count": len(invoices), "total_amount": total_amount,
        "completed": completed, "pending": len(invoices)-completed, "overdue": overdue,
        "average": total_amount / len(invoices) if invoices else 0,
        "invoices": [invoice_dict(i) for i in invoices],
    }


@app.post("/api/invoices/{invoice_id}/open-outlook")
def open_invoice_in_outlook(invoice_id: int, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    message_id = (invoice.message_id or "").strip().strip("<>")
    prefix = "outlook-"
    if not message_id.startswith(prefix):
        raise HTTPException(status_code=400, detail="Esta fatura não possui uma referência do Outlook clássico.")
    try:
        open_outlook_message(message_id[len(prefix):])
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True}


@app.get("/api/invoices/{invoice_id}/email-link")
def invoice_email_link(invoice_id: int, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    account = db.get(EmailAccount, invoice.email_account_id) if invoice.email_account_id else None
    provider = account.provider if account else ""
    username = account.username if account else ""
    message_id = (invoice.message_id or "").strip().strip("<>")
    subject = (invoice.subject or "").strip()

    from urllib.parse import quote
    if provider == "gmail":
        query = f"rfc822msgid:{message_id}" if message_id else f'subject:"{subject}"'
        auth = f"?authuser={quote(username)}" if username else ""
        return {"url": f"https://mail.google.com/mail/u/0/#search/{quote(query)}{auth}", "provider": "gmail"}
    if provider in OUTLOOK_LOCAL_PROVIDERS:
        query = subject or message_id
        return {"url": f"https://outlook.office.com/mail/search?q={quote(query)}", "provider": "outlook_desktop"}
    if message_id or subject:
        query = message_id or subject
        return {"url": f"https://mail.google.com/mail/u/0/#search/{quote(query)}", "provider": provider or "email"}
    raise HTTPException(status_code=404, detail="Esta fatura não possui referência ao e-mail original.")


@app.post("/api/invoices", status_code=201)
def create_invoice(payload: InvoiceInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    number_key = normalize_invoice_number(payload.invoice_number)
    if not number_key:
        raise HTTPException(status_code=400, detail="Número da fatura inválido.")
    invoice = Invoice(
        carrier=payload.carrier.strip(),
        carrier_key=carrier_key(payload.carrier),
        invoice_number=payload.invoice_number.strip(),
        normalized_number=number_key,
        due_date=payload.due_date,
        amount=payload.amount,
        situation_gko=payload.situation_gko.strip(),
        notes=payload.notes.strip(),
        source="manual",
        created_by_id=user.id,
    )
    db.add(invoice)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esta fatura já está cadastrada para a transportadora.")
    db.refresh(invoice)
    return invoice_dict(invoice)


@app.patch("/api/invoices/{invoice_id}")
def update_invoice(invoice_id: int, payload: InvoiceUpdateInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    number_key = normalize_invoice_number(payload.invoice_number)
    if not number_key:
        raise HTTPException(status_code=400, detail="Número da fatura inválido.")
    invoice.carrier = payload.carrier.strip()
    invoice.carrier_key = carrier_key(payload.carrier)
    invoice.invoice_number = payload.invoice_number.strip()
    invoice.normalized_number = number_key
    invoice.due_date = payload.due_date
    invoice.amount = payload.amount
    invoice.notes = payload.notes.strip()
    invoice.created_by_id = user.id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma fatura com este número para a transportadora.")
    db.refresh(invoice)
    return invoice_dict(invoice)


@app.patch("/api/invoices/{invoice_id}/gko")
def set_gko(invoice_id: int, payload: ToggleInput, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    if not payload.value and invoice.save_posted:
        raise HTTPException(status_code=400, detail="Remova o lançamento SAVE antes de retirar a liberação GKO.")
    invoice.gko_released = payload.value
    invoice.situation_gko = "OK" if payload.value else "PENDENTE"
    db.commit()
    return invoice_dict(invoice)


@app.patch("/api/invoices/{invoice_id}/save")
def set_save(invoice_id: int, payload: ToggleInput, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    if payload.value and not invoice.gko_released:
        raise HTTPException(status_code=400, detail="Libere o status GKO antes de marcar o SAVE.")
    invoice.save_posted = payload.value
    invoice.status = "COMPLETED" if payload.value else "PENDING"
    db.commit()
    return invoice_dict(invoice)


@app.patch("/api/invoices/{invoice_id}/classification")
def set_classification(invoice_id: int, payload: dict, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    value = str(payload.get("value", "")).upper()
    if value not in {"FREIGHT", "SERVICE", "REVIEW"}:
        raise HTTPException(status_code=400, detail="Classificação inválida.")
    invoice.invoice_type = value
    invoice.classification_confidence = 100
    db.commit()
    return invoice_dict(invoice)


@app.delete("/api/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    db.delete(invoice)
    db.commit()
    return {"ok": True}


@app.get("/api/email-accounts")
def list_accounts(_admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [account_dict(item) for item in db.scalars(select(EmailAccount).order_by(EmailAccount.label)).all()]


@app.post("/api/email-accounts", status_code=201)
def create_account(payload: EmailAccountInput, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if payload.provider not in OUTLOOK_LOCAL_PROVIDERS and not payload.password:
        raise HTTPException(status_code=400, detail="Informe a senha ou senha de aplicativo.")
    account = EmailAccount(
        label=payload.label.strip(), provider=payload.provider, imap_host=payload.imap_host.strip(),
        imap_port=payload.imap_port, username=payload.username.strip(),
        encrypted_password=encrypt_secret(payload.password) if payload.password and payload.provider not in OUTLOOK_LOCAL_PROVIDERS else "", unread_only=payload.unread_only,
        days_back=payload.days_back, active=payload.active,
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Essa conta de e-mail já está cadastrada.")
    db.refresh(account)
    return account_dict(account)


@app.put("/api/email-accounts/{account_id}")
def update_account(account_id: int, payload: EmailAccountInput, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    account = db.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    account.label = payload.label.strip()
    account.provider = payload.provider
    account.imap_host = payload.imap_host.strip()
    account.imap_port = payload.imap_port
    account.username = payload.username.strip()
    account.unread_only = payload.unread_only
    account.days_back = payload.days_back
    account.active = payload.active
    if account.provider in OUTLOOK_LOCAL_PROVIDERS:
        # Outlook local usa a sessão já autenticada do Windows e não guarda senha.
        account.encrypted_password = ""
    elif payload.password:
        account.encrypted_password = encrypt_secret(payload.password)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Essa conta de e-mail já está cadastrada.")
    return account_dict(account)


@app.post("/api/email-accounts/{account_id}/test")
def test_email_account(account_id: int, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    account = db.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    try:
        if account.provider in OUTLOOK_LOCAL_PROVIDERS:
            username = account.username if account.provider == "outlook" else None
            test_outlook_desktop(username)
        else:
            test_connection(account)
    except Exception as error:
        account.last_error = friendly_email_error(error, account)
        db.commit()
        raise HTTPException(status_code=400, detail=account.last_error)
    if account.provider in OUTLOOK_LOCAL_PROVIDERS:
        # Remove uma senha antiga somente depois de confirmar a nova conexão local.
        account.encrypted_password = ""
    account.last_error = None
    db.commit()
    message = "Outlook conectado com sucesso." if account.provider in OUTLOOK_LOCAL_PROVIDERS else "Conexão realizada com sucesso."
    return {"ok": True, "message": message}


@app.delete("/api/email-accounts/{account_id}")
def delete_account(account_id: int, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    account = db.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    db.delete(account)
    db.commit()
    return {"ok": True}


@app.post("/api/email/sync")
def sync_email(_user: User = Depends(current_user), db: Session = Depends(get_db)):
    accounts = db.scalars(select(EmailAccount).where(EmailAccount.active.is_(True))).all()
    if not accounts:
        raise HTTPException(status_code=400, detail="Cadastre ao menos uma conta de e-mail ativa.")
    inserted = duplicates = 0
    errors: list[str] = []
    existing = {(carrier, number) for carrier, number in db.execute(select(Invoice.carrier_key, Invoice.normalized_number)).all()}
    for account in accounts:
        try:
            if account.provider in OUTLOOK_LOCAL_PROVIDERS:
                username = account.username if account.provider == "outlook" else None
                found = fetch_outlook_desktop(account.days_back, account.unread_only, username=username)
                account.encrypted_password = ""
            else:
                found = fetch_invoices(account)
            batch: set[tuple[str, str]] = set()
            for item in found:
                key = (carrier_key(item["carrier"]), normalize_invoice_number(item["invoice_number"]))
                if not key[1] or key in existing or key in batch:
                    duplicates += 1
                    continue
                db.add(Invoice(
                    carrier=item["carrier"], carrier_key=key[0], invoice_number=item["invoice_number"],
                    normalized_number=key[1], due_date=item["due_date"], amount=item["amount"],
                    notes=item["notes"], source="email", source_email=item["source_email"],
                    invoice_type=item.get("invoice_type", "REVIEW"), classification_confidence=item.get("classification_confidence", 35),
                    subject=item["subject"], message_id=item["message_id"], email_account_id=account.id,
                ))
                batch.add(key)
                existing.add(key)
                inserted += 1
            account.last_sync_at = datetime.now(UTC).replace(tzinfo=None)
            account.last_error = None
        except Exception as error:
            account.last_error = friendly_email_error(error, account)
            errors.append(f"{account.label}: {account.last_error}")
    db.commit()
    return {"inserted": inserted, "duplicates": duplicates, "errors": errors, "accounts": len(accounts)}


@app.post("/api/excel/import")
async def import_excel(file: UploadFile = File(...), user: User = Depends(admin_user), db: Session = Depends(get_db)):
    filename = Path(file.filename or "planilha.xlsx").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Envie uma planilha no formato .xlsx.")
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="A planilha deve ter no máximo 30 MB.")
    backup_path = BACKUP_DIR / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{filename}"
    backup_path.write_bytes(content)
    try:
        result = await run_in_threadpool(import_workbook, db, backup_path, user.id)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error))
    return {**result, "backup": backup_path.name}


@app.get("/api/excel/status")
def excel_status(_admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Invoice.id)).where(Invoice.source == "excel")) or 0
    return {"imported_invoices": count}


@app.post("/api/excel/replace")
async def replace_excel(file: UploadFile = File(...), user: User = Depends(admin_user), db: Session = Depends(get_db)):
    filename = Path(file.filename or "planilha.xlsx").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Envie uma planilha no formato .xlsx.")
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="A planilha deve ter no máximo 30 MB.")

    uploaded_path = BACKUP_DIR / f"substituta-{datetime.now():%Y%m%d-%H%M%S-%f}-{filename}"
    uploaded_path.write_bytes(content)
    previous_count = db.scalar(select(func.count(Invoice.id)).where(Invoice.source == "excel")) or 0
    recovery_path = BACKUP_DIR / f"antes-substituir-excel-{datetime.now():%Y%m%d-%H%M%S-%f}.xlsx"
    recovery_path.write_bytes(await run_in_threadpool(export_workbook, db))
    try:
        db.execute(delete(Invoice).where(Invoice.source == "excel"))
        result = await run_in_threadpool(import_workbook, db, uploaded_path, user.id)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"A planilha antiga foi mantida. {error}")
    return {**result, "removed": previous_count, "backup": recovery_path.name}


@app.delete("/api/excel/imported")
def remove_excel_invoices(_admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Invoice.id)).where(Invoice.source == "excel")) or 0
    if not count:
        return {"removed": 0, "backup": None}
    recovery_path = BACKUP_DIR / f"antes-remover-excel-{datetime.now():%Y%m%d-%H%M%S-%f}.xlsx"
    recovery_path.write_bytes(export_workbook(db))
    db.execute(delete(Invoice).where(Invoice.source == "excel"))
    db.commit()
    return {"removed": count, "backup": recovery_path.name}


@app.get("/api/excel/export")
def export_excel(_user: User = Depends(current_user), db: Session = Depends(get_db)):
    content = export_workbook(db)
    filename = f"Controle_de_Faturas_{datetime.now():%Y-%m-%d}.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/users")
def list_users(_admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [
        {"id": item.id, "name": item.name, "username": item.username, "role": item.role, "active": item.active, "created_at": item.created_at.isoformat()}
        for item in db.scalars(select(User).order_by(User.name)).all()
    ]


@app.post("/api/users", status_code=201)
def create_user(payload: UserInput, _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    user = User(name=payload.name.strip(), username=clean_username(payload.username), password_hash=hash_password(payload.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esse nome de usuário já existe.")
    db.refresh(user)
    return {"id": user.id, "name": user.name, "username": user.username, "role": user.role, "active": user.active}


@app.patch("/api/users/{user_id}/active")
def set_user_active(user_id: int, payload: ToggleInput, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.role == "owner":
        raise HTTPException(status_code=400, detail="O proprietário não pode ser desativado.")
    user.active = payload.value
    if not payload.value:
        db.query(UserSession).filter(UserSession.user_id == user.id).delete()
    db.commit()
    return {"ok": True, "active": user.active}


@app.get("/api/audit-logs")
def list_audit_logs(limit: int = Query(default=500, ge=1, le=2000), _owner: User = Depends(owner_user), db: Session = Depends(get_db)):
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [{
        "id": item.id, "username": item.username, "action": item.action,
        "method": item.method, "path": item.path, "status_code": item.status_code,
        "ip_address": item.ip_address, "created_at": item.created_at.isoformat(),
    } for item in logs]
