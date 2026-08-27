PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(120) NOT NULL,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(300) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin ON users(role) WHERE role = 'admin';

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(120) NOT NULL DEFAULT 'desconhecido',
    action VARCHAR(180) NOT NULL,
    method VARCHAR(10) NOT NULL,
    path VARCHAR(300) NOT NULL,
    status_code INTEGER NOT NULL,
    ip_address VARCHAR(80) NOT NULL DEFAULT '',
    user_agent VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS email_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label VARCHAR(100) NOT NULL,
    provider VARCHAR(30) NOT NULL,
    imap_host VARCHAR(180) NOT NULL,
    imap_port INTEGER NOT NULL DEFAULT 993,
    username VARCHAR(180) NOT NULL UNIQUE,
    encrypted_password TEXT NOT NULL,
    unread_only BOOLEAN NOT NULL DEFAULT 1,
    days_back INTEGER NOT NULL DEFAULT 30,
    active BOOLEAN NOT NULL DEFAULT 1,
    last_sync_at DATETIME,
    last_error TEXT,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier VARCHAR(120) NOT NULL,
    carrier_key VARCHAR(120) NOT NULL,
    invoice_number VARCHAR(100) NOT NULL,
    normalized_number VARCHAR(100) NOT NULL,
    due_date DATE,
    amount NUMERIC(14, 2),
    inclusion_date DATE NOT NULL,
    gko_released BOOLEAN NOT NULL DEFAULT 0,
    save_posted BOOLEAN NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    situation_gko VARCHAR(80) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    source VARCHAR(30) NOT NULL DEFAULT 'manual',
    source_email VARCHAR(180) NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    message_id VARCHAR(400),
    email_account_id INTEGER REFERENCES email_accounts(id) ON DELETE SET NULL,
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_invoice_carrier_number UNIQUE (carrier_key, normalized_number)
);

CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS ix_invoices_save_posted ON invoices(save_posted);
CREATE INDEX IF NOT EXISTS ix_invoices_gko_released ON invoices(gko_released);
CREATE INDEX IF NOT EXISTS ix_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_username ON audit_logs(username);
