from __future__ import annotations

import email
import imaplib
import re
import socket
from datetime import date, datetime, timedelta
from email.header import decode_header
from email.message import EmailMessage, Message
from email.utils import parseaddr
from email.policy import default
from html import unescape

from ..models import EmailAccount
from ..security import decrypt_secret
from .invoice_rules import parse_amount


TRANSPORTADORAS = [
    "AGILGROUP", "BROSLOG", "SIGATRANS", "TCM", "AEROTRAFIC", "SM LOG",
    "TURASSI", "TRANSPANEX", "RW", "GCON", "G-COM", "SANCOEX", "E4LOG",
    "UP", "SUPERGASBRAS", "SUPERGÁSBRAS", "TERLOC", "CONTRANS", "BUONNY",
    "HDI", "SASCAR MICHELIN", "GH", "TRANSGUERRA", "TSJ", "BINHO",
    "JATOLOG", "TRD", "RODOVITOR", "COMAM", "INICIAL", "SM",
]


def friendly_email_error(error: Exception, account: EmailAccount) -> str:
    """Converte respostas técnicas do IMAP em instruções seguras para o usuário."""
    raw_value = error.args[0] if getattr(error, "args", None) else str(error)
    if isinstance(raw_value, bytes):
        raw = raw_value.decode("utf-8", errors="replace")
    else:
        raw = str(raw_value)
    normalized = raw.lower()

    if account.provider in {"outlook", "outlook_desktop"}:
        if "funciona somente no windows" in normalized:
            return "A conexão com o Outlook funciona somente no computador Windows onde o FC SERV está aberto."
        if any(term in normalized for term in ("classe não registrada", "class not registered", "invalid class string", "componente do outlook não está instalado")):
            return "O Outlook clássico não foi encontrado. Instale ou abra o Outlook clássico do Windows e tente novamente."
        if "não foi encontrada no outlook" in normalized:
            return raw.strip()
        if "nenhuma conta foi encontrada" in normalized:
            return "Nenhuma conta foi encontrada no Outlook clássico. Abra o Outlook, adicione a conta e tente novamente."

    if "lookup failed" in normalized:
        return (
            f"A caixa {account.username} não foi localizada no Gmail. Confirme se este é o endereço principal "
            "da conta Google Workspace, e não um apelido. Se a empresa usa Microsoft 365, edite a conta e "
            "selecione Outlook / Microsoft 365."
        )
    if any(term in normalized for term in ("authenticationfailed", "invalid credentials", "login failed", "credentials invalid")):
        if account.provider == "gmail":
            return "O Gmail recusou o acesso. Gere uma nova senha de aplicativo de 16 caracteres e informe o endereço principal completo da conta."
        return "O provedor recusou o usuário ou a senha de aplicativo. Confira as credenciais e tente novamente."
    if isinstance(error, (socket.timeout, TimeoutError)) or "timed out" in normalized:
        return "O servidor de e-mail demorou demais para responder. Verifique a internet e tente novamente."
    if isinstance(error, socket.gaierror) or "name or service not known" in normalized:
        return f"O servidor {account.imap_host} não foi encontrado. Confira o provedor e o endereço IMAP."
    if any(term in normalized for term in ("connection refused", "network is unreachable", "getaddrinfo failed")):
        return "Não foi possível alcançar o servidor de e-mail. Verifique a internet, o servidor IMAP e a porta."

    clean = re.sub(r"\b[0-9a-f]{24,}\b", "", raw, flags=re.I).strip(" b'\"")
    if not clean:
        return "O provedor recusou a conexão sem informar o motivo. Teste novamente ou revise a conta cadastrada."
    return f"O provedor recusou a conexão: {clean[:240]}"


def decode_value(value: str | None) -> str:
    if not value:
        return ""
    result: list[str] = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def identify_carrier(text: str) -> str | None:
    upper = text.upper()
    for carrier in TRANSPORTADORAS:
        if carrier.upper() in upper:
            return carrier
    aliases = {
        "AGIL": "AGILGROUP", "BROS": "BROSLOG", "SIGA": "SIGATRANS",
        "AERO": "AEROTRAFIC", "TURAS": "TURASSI", "TRANSPAN": "TRANSPANEX",
        "G-CON": "GCON", "SUPERGAS": "SUPERGASBRAS", "TRANSGUER": "TRANSGUERRA",
    }
    return next((carrier for pattern, carrier in aliases.items() if pattern in upper), None)


def message_body(message: Message) -> str:
    chunks: list[str] = []
    if message.is_multipart():
        parts = message.walk()
    else:
        parts = [message]
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        raw = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        if part.get_content_type() == "text/html":
            text = re.sub(r"<style[\s\S]*?</style>|<script[\s\S]*?</script>", " ", text, flags=re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = unescape(text)
        chunks.append(text)
    return re.sub(r"\s+", " ", " ".join(chunks))


def _sender_supplier(sender: str) -> str:
    """Cria um nome legível de fornecedor quando ele não está na lista conhecida."""
    display, address = parseaddr(sender)
    display = re.sub(r"[\"']", "", display).strip()
    if display and "@" not in display:
        return display[:120]
    domain = address.split("@", 1)[-1].split(".")[0] if "@" in address else ""
    return domain.replace("-", " ").replace("_", " ").strip().upper()[:120] or "FORNECEDOR"


def _invoice_candidate(subject: str, body: str) -> bool:
    """Aceita somente mensagens com sinais fortes de faturamento e rejeita ruído comum."""
    text = f"{subject} {body[:5000]}".lower()
    blocked = (
        "protocolo_", "protocolo ", "comprovante de pagamento", "confirmação de pagamento",
        "cotação", "orcamento", "orçamento", "pedido de coleta", "agendamento de coleta",
    )
    if any(term in text for term in blocked) and "fatura" not in subject.lower():
        return False
    subject_signals = (
        "fatura", "faturamento", "cobrança de frete", "cobranca de frete",
        "capa de fatura", "sua fatura", "lembrete de vencimento",
    )
    financial_signals = ("boleto", "cobrança", "cobranca", "nota fiscal", "nfse", "nfs-e", "invoice", "vencimento", "valor")
    if not any(term in subject.lower() for term in subject_signals) and not any(term in text for term in financial_signals):
        return False
    # Evita capturar palavras soltas como "faturar" sem número/documento financeiro.
    has_number = bool(re.search(r"(?:fatura|nf(?:-?e)?|invoice|documento|n[º°o])[^\d]{0,25}[A-Z]?[/-]?\d{3,}", text, re.I))
    has_attachment_or_financial = any(term in text for term in ("boleto", "cte", "ct-e", "xml", "pdf", "valor", "vencimento", "vecto", "venc."))
    return has_number or has_attachment_or_financial


def classify_invoice(subject: str, sender: str, body: str, attachments: list[str] | None = None) -> tuple[str, int]:
    """Classifica a cobrança sem depender de um único padrão fixo."""
    text = f"{subject} {sender} {body[:12000]} {' '.join(attachments or [])}".lower()
    freight_terms = {
        "cte": 4, "ct-e": 4, "conhecimento de transporte": 5, "frete": 4,
        "transportadora": 3, "ctrc": 4, "romaneio": 2, "coleta": 2,
        "carregamento": 2, "entrega": 1, "pedágio": 2, "pedagio": 2,
        "rntrc": 4, "placa": 2, "logística": 1, "logistica": 1,
    }
    service_terms = {
        "nfs-e": 5, "nfse": 5, "nota fiscal de serviço": 5, "nota fiscal de servico": 5,
        "prestação de serviço": 4, "prestacao de servico": 4, "serviços prestados": 4,
        "servicos prestados": 4, "mensalidade": 3, "honorários": 3, "honorarios": 3,
        "consultoria": 3, "manutenção": 3, "manutencao": 3, "licença": 3,
        "licenca": 3, "assinatura": 2, "suporte técnico": 3, "suporte tecnico": 3,
        "locação": 2, "locacao": 2, "serviço": 2, "servico": 2,
    }
    freight = sum(weight for term, weight in freight_terms.items() if term in text)
    service = sum(weight for term, weight in service_terms.items() if term in text)
    if freight >= service + 2 and freight >= 3:
        return "FREIGHT", min(99, 65 + freight * 4)
    if service >= freight + 2 and service >= 3:
        return "SERVICE", min(99, 65 + service * 4)
    # Fornecedores de transporte continuam como frete quando houver documento financeiro.
    if freight >= 2 and service == 0:
        return "FREIGHT", 60
    if service >= 2 and freight == 0:
        return "SERVICE", 60
    return "REVIEW", 35


def extract_invoice(message: Message) -> dict | None:
    subject = decode_value(message.get("Subject"))
    sender = decode_value(message.get("From"))
    body = message_body(message)
    if not _invoice_candidate(subject, body):
        return None
    combined = f"{subject} {body}"
    carrier = identify_carrier(f"{subject} {sender} {body[:2500]}") or _sender_supplier(sender)

    number = ""
    patterns = (
        r"fatura\s+(?:n(?:[º°o]|o\.)?|no\.?)\s*[:#-]?\s*([A-Za-z]?[/.-]?\d[\dA-Za-z./-]{2,})",
        r"fatura\s+save\s*[:#-]?\s*([A-Za-z]?[/.-]?\d[\dA-Za-z./-]{2,})",
        r"fatura\s*(?:[:#-]\s*)?([A-Za-z]?[/.-]?\d[\dA-Za-z./-]{2,})",
        r"(?:n[úu]mero\s+da\s+fatura|n[º°o]\s*da?\s*fatura)\s*[:#-]?\s*([A-Za-z0-9./-]+)",
        r"(?:nota\s+fiscal|n[º°o]\s*nf|nf-?e?)\s*[:#-]?\s*([0-9]{3,44})",
        r"(?:invoice|bill)\s*[:#-]?\s*([A-Za-z0-9./-]+)",
        r"\bop\s*[:#-]?\s*([0-9]{3,})",
    )
    for pattern in patterns:
        found = re.search(pattern, combined, flags=re.I)
        if found:
            candidate = found.group(1).strip(" .-:")
            if len(re.sub(r"\W", "", candidate)) >= 3 and not candidate.lower() in {"save", "disponivel", "disponível"}:
                number = candidate
                break
    if not number:
        return None

    due_date = None
    date_patterns = (
        r"(?:vencimento|data\s+de\s+vencimento|vecto|venc\.)\s*[:\s-]*(\d{2}[/-]\d{2}[/-]\d{4})",
        r"(?:vencimento|venc)\s*[:\s-]*(\d{4}-\d{2}-\d{2})",
    )
    for pattern in date_patterns:
        found_date = re.search(pattern, combined, flags=re.I)
        if not found_date:
            continue
        raw_date = found_date.group(1)
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                due_date = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                pass
        if due_date:
            break

    amount = None
    amount_patterns = (
        r"(?:valor\s+total|total\s+da\s+fatura|valor\s+da\s+fatura|valor\s*\(R\$\)|valor)\s*[:\s-]*R?\$?\s*([0-9.]+(?:,[0-9]{2})?)",
        r"R\$\s*([0-9.]+(?:,[0-9]{2})?)",
    )
    for pattern in amount_patterns:
        found_amount = re.search(pattern, combined, flags=re.I)
        if found_amount:
            amount = parse_amount(found_amount.group(1))
            if amount is not None:
                break

    attachments = []
    for part in message.walk():
        filename = decode_value(part.get_filename())
        if filename.lower().endswith((".pdf", ".xml", ".zip", ".xlsx")):
            attachments.append(filename)

    invoice_type, confidence = classify_invoice(subject, sender, body, attachments)

    return {
        "carrier": carrier,
        "invoice_number": number,
        "invoice_type": invoice_type,
        "classification_confidence": confidence,
        "due_date": due_date,
        "amount": amount,
        "notes": "; ".join(f"Anexo: {name}" for name in attachments),
        "source_email": sender,
        "subject": subject,
        "message_id": str(message.get("Message-ID") or "").strip() or None,
    }


def fetch_invoices(account: EmailAccount, limit: int = 1500) -> list[dict]:
    password = decrypt_secret(account.encrypted_password)
    mailbox = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=30)
    try:
        mailbox.login(account.username, password)
        status, _ = mailbox.select("INBOX", readonly=False)
        if status != "OK":
            raise RuntimeError("Não foi possível abrir a caixa de entrada.")
        since = (date.today() - timedelta(days=account.days_back)).strftime("%d-%b-%Y")
        criteria = ["UNSEEN", "SINCE", since]
        status, data = mailbox.search(None, *criteria)
        if status != "OK":
            raise RuntimeError("Não foi possível pesquisar os e-mails.")
        message_ids = list(reversed((data[0] or b"").split()[-limit:]))
        invoices: list[dict] = []
        seen_message_ids: set[str] = set()
        for message_id in message_ids:
            # BODY.PEEK evita leitura prematura; após reconhecer uma fatura válida, marcamos como vista.
            status, parts = mailbox.fetch(message_id, "(BODY.PEEK[])")
            if status != "OK":
                continue
            raw = next((part[1] for part in parts if isinstance(part, tuple)), None)
            if not raw:
                continue
            parsed = email.message_from_bytes(raw, policy=default)
            invoice = extract_invoice(parsed)
            if invoice:
                internet_id = invoice.get("message_id") or f"imap:{message_id.decode(errors='ignore')}"
                if internet_id in seen_message_ids:
                    continue
                seen_message_ids.add(internet_id)
                invoices.append(invoice)
                mailbox.store(message_id, "+FLAGS", "\\Seen")
        return invoices
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass


def test_connection(account: EmailAccount) -> None:
    password = decrypt_secret(account.encrypted_password)
    mailbox = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=30)
    try:
        mailbox.login(account.username, password)
        status, _ = mailbox.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("Login aceito, mas a caixa de entrada não pôde ser aberta.")
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass


def _outlook_smtp_address(account) -> str:
    address = str(getattr(account, "SmtpAddress", "") or "").strip()
    if address:
        return address.lower()
    try:
        entry = account.CurrentUser.AddressEntry
        exchange_user = entry.GetExchangeUser() if entry else None
        return str(getattr(exchange_user, "PrimarySmtpAddress", "") or "").strip().lower()
    except Exception:
        return ""


def _outlook_inboxes(namespace, username: str | None = None) -> list:
    """Retorna a caixa solicitada ou todas as caixas do perfil do Outlook."""
    requested = (username or "").strip().lower()
    if requested == "outlook-local@local":
        requested = ""

    inboxes: list = []
    seen_stores: set[str] = set()
    if requested:
        accounts = namespace.Accounts
        for account_index in range(1, accounts.Count + 1):
            outlook_account = accounts.Item(account_index)
            if _outlook_smtp_address(outlook_account) != requested:
                continue
            store = outlook_account.DeliveryStore
            store_id = str(getattr(store, "StoreID", "") or requested)
            if store_id not in seen_stores:
                inboxes.append(store.GetDefaultFolder(6))  # olFolderInbox
                seen_stores.add(store_id)
        if not inboxes:
            raise RuntimeError(
                f"A conta {username} não foi encontrada no Outlook clássico. "
                "Abra o Outlook nesse computador, adicione a conta e tente novamente."
            )
        return inboxes

    stores = namespace.Stores
    for store_index in range(1, stores.Count + 1):
        store = stores.Item(store_index)
        try:
            store_id = str(getattr(store, "StoreID", "") or store_index)
            if store_id in seen_stores:
                continue
            inboxes.append(store.GetDefaultFolder(6))  # olFolderInbox
            seen_stores.add(store_id)
        except Exception:
            continue
    if not inboxes:
        raise RuntimeError("Nenhuma conta foi encontrada no Outlook clássico.")
    return inboxes


def fetch_outlook_desktop(
    days_back: int = 30,
    unread_only: bool = True,
    limit: int = 1000,
    username: str | None = None,
) -> list[dict]:
    """Lê uma conta específica ou todas as caixas do Outlook clássico do Windows."""
    if __import__("sys").platform != "win32":
        raise RuntimeError("A integração com o Outlook instalado funciona somente no Windows.")
    try:
        import pythoncom
        import win32com.client
    except ImportError as error:
        raise RuntimeError("O componente do Outlook não está instalado. Execute novamente o instalador.") from error

    pythoncom.CoInitialize()
    try:
        namespace = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        cutoff = datetime.now() - timedelta(days=days_back)
        invoices: list[dict] = []
        for inbox in _outlook_inboxes(namespace, username):
            try:
                items = inbox.Items
                items.Sort("[ReceivedTime]", True)
            except Exception:
                continue
            checked = 0
            for item_index in range(1, items.Count + 1):
                if checked >= limit:
                    break
                item = items.Item(item_index)
                if getattr(item, "Class", None) != 43:  # olMail
                    continue
                checked += 1
                try:
                    received = item.ReceivedTime
                    if getattr(received, "tzinfo", None):
                        received = received.replace(tzinfo=None)
                    if received < cutoff:
                        break
                    if unread_only and not bool(item.UnRead):
                        continue
                    message = EmailMessage()
                    message["Subject"] = str(item.Subject or "")
                    sender = str(getattr(item, "SenderEmailAddress", "") or "")
                    message["From"] = sender
                    message["Message-ID"] = f"<outlook-{item.EntryID}>"
                    message.set_content(str(item.Body or ""))
                    invoice = extract_invoice(message)
                    if not invoice:
                        continue
                    pdfs: list[str] = []
                    attachments = item.Attachments
                    for attachment_index in range(1, attachments.Count + 1):
                        name = str(attachments.Item(attachment_index).FileName or "")
                        if name.lower().endswith(".pdf"):
                            pdfs.append(name)
                    if pdfs:
                        invoice["notes"] = "; ".join(f"PDF: {name}" for name in pdfs)
                    invoices.append(invoice)
                    # Marca como lido somente depois de reconhecer uma fatura válida.
                    item.UnRead = False
                    item.Save()
                except Exception:
                    continue
        return invoices
    finally:
        pythoncom.CoUninitialize()


def test_outlook_desktop(username: str | None = None) -> None:
    if __import__("sys").platform != "win32":
        raise RuntimeError("A integração com o Outlook instalado funciona somente no Windows.")
    try:
        import pythoncom
        import win32com.client
    except ImportError as error:
        raise RuntimeError("O componente do Outlook não está instalado.") from error
    pythoncom.CoInitialize()
    try:
        namespace = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        _outlook_inboxes(namespace, username)
    finally:
        pythoncom.CoUninitialize()


def open_outlook_message(entry_id: str) -> None:
    """Abre a mensagem original no Outlook clássico instalado no mesmo Windows."""
    if __import__("sys").platform != "win32":
        raise RuntimeError("A abertura direta no Outlook funciona somente no Windows.")
    try:
        import pythoncom
        import win32com.client
    except ImportError as error:
        raise RuntimeError("O componente do Outlook não está instalado.") from error
    pythoncom.CoInitialize()
    try:
        namespace = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        item = namespace.GetItemFromID(entry_id)
        item.Display(False)
    finally:
        pythoncom.CoUninitialize()
