#!/usr/bin/env python3
"""
Create New Client Script
Generates a full .env file + moves SSH Key to client folder automatically
"""

import sys
import json
import shutil
import secrets
import string
from pathlib import Path
from datetime import datetime


# ── helpers ────────────────────────────────────────────────────────────────

def generate_secret_key(length=50):
    chars = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
    return ''.join(secrets.choice(chars) for _ in range(length))


def ask(prompt, default=None, required=True):
    display = prompt
    if default:
        display += f" (default: {default})"
    display += ": "
    while True:
        value = input(display).strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ''
        print("  ⚠️  This field is required")


# ── SSH Key handling ────────────────────────────────────────────────────────

def handle_ssh_key(client_dir: Path, project_root: Path) -> tuple[str, str]:
    """
    Asks for the key path and moves it to the client folder automatically.
    Returns (ssh_key_path_in_env, ssh_passphrase)
    """
    print()
    print("  Use SSH Key for authentication?")
    print("  [1] Yes - I have an existing key to move")
    print("  [2] No  - I will use password only")
    choice = input("  Choose (1/2): ").strip()

    if choice != '1':
        return '', ''

    # Search for available keys in root and current folder
    common_locations = list(project_root.glob("id_rsa*")) + \
                       list(project_root.glob("*.pem")) + \
                       list((Path.home() / '.ssh').glob("id_rsa*") if (Path.home() / '.ssh').exists() else [])

    # Filter private keys only (no .pub)
    private_keys = [p for p in common_locations if not p.suffix == '.pub' and p.is_file()]

    if private_keys:
        print()
        print("  🔍 Found keys:")
        for i, key in enumerate(private_keys, 1):
            print(f"  [{i}] {key}")
        print(f"  [{len(private_keys)+1}] Different path (enter manually)")
        print()

        sel = input(f"  Select key number (1-{len(private_keys)+1}): ").strip()
        try:
            sel_int = int(sel)
            if 1 <= sel_int <= len(private_keys):
                source_key = private_keys[sel_int - 1]
            else:
                source_key = Path(ask("  Enter full path to key"))
        except ValueError:
            source_key = Path(ask("  Enter full path to key"))
    else:
        source_key = Path(ask("  Enter full path to key"))

    if not source_key.exists():
        print(f"  ⚠️  Key not found: {source_key}")
        print("  Continuing without SSH Key")
        return '', ''

    # Ask whether to copy the key or use it in-place
    print()
    print("  What do you want to do with this key?")
    print(f"  [1] Copy it to the client folder → deployments/{client_dir.name}/ssh_key  (recommended)")
    print(f"  [2] Use it in-place (keep at current path: {source_key})")
    copy_choice = input("  Choose (1/2): ").strip()

    if copy_choice == '2':
        # Use the key in-place - store its path as-is
        # If it's inside the project root, store as relative path; otherwise absolute
        try:
            relative_key_path = str(source_key.relative_to(project_root)).replace('\\', '/')
        except ValueError:
            # Key is outside project root - store absolute path
            relative_key_path = str(source_key).replace('\\', '/')
        print(f"  ✅ SSH_KEY_PATH set to: {relative_key_path}")
        passphrase = ask("  SSH Key Passphrase (leave empty if not protected)", required=False)
        return relative_key_path, passphrase

    # Copy key to client folder
    dest_key = client_dir / "ssh_key"
    dest_pub = client_dir / "ssh_key.pub"

    shutil.copy2(source_key, dest_key)
    print(f"  ✅ Key copied → {dest_key.relative_to(project_root)}")

    # Copy public key if exists
    pub_source = Path(str(source_key) + '.pub')
    if pub_source.exists():
        shutil.copy2(pub_source, dest_pub)
        print(f"  ✅ Public key copied → {dest_pub.relative_to(project_root)}")

    # Ask about deleting source
    print()
    delete = input(f"  Delete original key from ({source_key})? (y/n): ").strip().lower()
    if delete == 'y':
        source_key.unlink()
        if pub_source.exists():
            pub_source.unlink()
        print(f"  🗑️  Original key deleted")

    passphrase = ask("  SSH Key Passphrase (leave empty if not protected)", required=False)

    # Relative path from project_root
    relative_key_path = str(dest_key.relative_to(project_root)).replace('\\', '/')
    return relative_key_path, passphrase


# ── .env.production generator ──────────────────────────────────────────────

def generate_env_file(data: dict) -> str:
    d          = data
    client_id  = d['client_id']
    domain     = d['domain']
    year       = datetime.now().year

    return f"""# ============================================================
# Django Core Settings
# ============================================================
SECRET_KEY={d['secret_key']}

DEBUG=False

ALLOWED_HOSTS={domain},www.{domain}

SITE_URL=https://{domain}

# ============================================================
# Database Configuration
# ============================================================
DB_ENGINE=mysql
DB_NAME={d['db_name']}
DB_USER={d['db_user']}
DB_PASSWORD={d['db_password']}
DB_HOST=localhost
DB_PORT=3306
DB_CONN_MAX_AGE=0

# ============================================================
# Static & Media Files
# ============================================================
STATIC_URL=/static/
STATIC_ROOT=staticfiles
MEDIA_URL=/media/
MEDIA_ROOT=media

# ============================================================
# Cache Configuration
# ============================================================
REDIS_URL=
REDIS_ENABLED=False

# ============================================================
# Celery Configuration
# ============================================================
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
CELERY_TASK_ALWAYS_EAGER=True

# ============================================================
# Logging & Monitoring
# ============================================================
LOG_LEVEL=WARNING
LOG_FILE=
LOG_RETENTION_DAYS=30
SENTRY_DSN=
MONITORING_ENABLED=True
ALERT_EMAIL_ENABLED=True
DEFAULT_ALERT_EMAIL={d['email']}
ENABLE_ERROR_TRACKING=True
ENABLE_BASIC_MONITORING=True

# ============================================================
# Security Settings
# ============================================================
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Strict
CSRF_COOKIE_HTTPONLY=True
SESSION_COOKIE_AGE=1800

SECURITY_HEADERS_ENABLED=True
SECURE_BROWSER_XSS_FILTER=True
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS=DENY
SECURE_REFERRER_POLICY=strict-origin-when-cross-origin

# ============================================================
# Rate Limiting
# ============================================================
RATE_LIMIT_ENABLED=True
API_RATE_LIMIT_AUTH=10/min
API_RATE_LIMIT_OPERATIONS=100/hour
API_RATE_LIMIT_AUTH_REQUESTS=1000
API_RATE_LIMIT_AUTH_WINDOW=3600
API_RATE_LIMIT_ANON_REQUESTS=50
API_RATE_LIMIT_ANON_WINDOW=3600
API_RATE_LIMIT_WEBHOOK_REQUESTS=50
API_RATE_LIMIT_WEBHOOK_WINDOW=3600

# ============================================================
# CORS Configuration
# ============================================================
CORS_ALLOWED_ORIGINS=https://{domain},https://www.{domain}
CORS_ALLOW_CREDENTIALS=True

# ============================================================
# Email Configuration
# ============================================================
EMAIL_BACKEND=utils.email_backend.SSLEmailBackend
EMAIL_HOST={d['email_host']}
EMAIL_PORT=587
EMAIL_USE_SSL=False
EMAIL_USE_TLS=True
EMAIL_HOST_USER={d['email']}
EMAIL_HOST_PASSWORD={d['email_password']}
DEFAULT_FROM_EMAIL={d['email']}
SERVER_EMAIL={d['email']}
EMAIL_TIMEOUT=30

# ============================================================
# Data Protection & Backup
# ============================================================
BACKUP_STORAGE_TYPE=local
BACKUP_LOCAL_DIR=backups
BACKUP_RETENTION_DAYS=30
BACKUP_ENABLE_ENCRYPTION=True
BACKUP_ENABLE_NOTIFICATIONS=True
BACKUP_NOTIFICATION_EMAILS={d['email']}
BACKUP_STORAGE_WARNING_THRESHOLD=80
BACKUP_STORAGE_CRITICAL_THRESHOLD=90

# S3 Backup (optional - enable when needed)
# BACKUP_STORAGE_TYPE=s3
# BACKUP_S3_BUCKET=
# BACKUP_S3_ACCESS_KEY=
# BACKUP_S3_SECRET_KEY=
# BACKUP_S3_REGION=us-east-1

# ============================================================
# Data Encryption
# ============================================================
ENABLE_FIELD_ENCRYPTION=True
ENCRYPTION_MASTER_KEY=
ENCRYPTION_KEY_FILE=encryption.key
ENCRYPTION_KEY_ROTATION_DAYS=90

# ============================================================
# Data Retention & Compliance
# ============================================================
DATA_RETENTION_ARCHIVE_ENABLED=True
DATA_RETENTION_NOTIFICATIONS_ENABLED=True
DATA_RETENTION_POLICY_DAYS=2555
GDPR_COMPLIANCE_ENABLED=True
PERSONAL_DATA_ENCRYPTION=True
DATA_ANONYMIZATION_ENABLED=True
ANONYMIZATION_SALT={generate_secret_key(32)}
DATA_PROTECTION_MONITORING_ENABLED=True

# ============================================================
# Webhook Security
# ============================================================
WEBHOOK_ENABLE_IP_WHITELIST=true
WEBHOOK_ENABLE_SIGNATURE_VALIDATION=true
WEBHOOK_SIGNATURE_ALGORITHM=sha256
WEBHOOK_REQUIRE_HTTPS=true
WEBHOOK_DEFAULT_SECRET={generate_secret_key(40)}
WEBHOOK_FINANCIAL_SECRET={generate_secret_key(40)}
WEBHOOK_PAYMENTS_SECRET={generate_secret_key(40)}
WEBHOOK_STUDENTS_SECRET={generate_secret_key(40)}

# ============================================================
# Data Reconciliation
# ============================================================
RECONCILIATION_ENABLE_DAILY=true
RECONCILIATION_TIME=02:00
RECONCILIATION_VARIANCE_PERCENTAGE=0.01
RECONCILIATION_VARIANCE_AMOUNT=1.00
RECONCILIATION_RETENTION_DAYS=60
RECONCILIATION_ENABLE_EMAIL_REPORTS=true
RECONCILIATION_REPORT_RECIPIENTS={d['email']}
RECONCILIATION_ALERT_RECIPIENTS={d['email']}

# ============================================================
# Integration Health Monitoring
# ============================================================
INTEGRATION_ENABLE_HEALTH_CHECKS=true
INTEGRATION_HEALTH_CHECK_INTERVAL=300
INTEGRATION_ALERT_ON_CRITICAL=true
INTEGRATION_ALERT_ON_WARNING=false
INTEGRATION_HEALTH_ALERT_RECIPIENTS={d['email']}

# ============================================================
# Audit Trail
# ============================================================
AUDIT_ENABLE_FINANCIAL=true
AUDIT_ENABLE_API=true
AUDIT_ENABLE_WEBHOOK=true
AUDIT_RETENTION_DAYS=180
AUDIT_ENABLE_REAL_TIME_ALERTS=true

# ============================================================
# Performance Optimization - Signal Control
# ============================================================
ENABLE_AUDIT_SIGNALS=False
ENABLE_LOGGING_SIGNALS=False
ENABLE_NOTIFICATION_SIGNALS=False

# ============================================================
# Celery Beat Schedule
# ============================================================
CELERY_BEAT_SCHEDULE_BACKUP_DAILY=false
CELERY_BEAT_SCHEDULE_BACKUP_WEEKLY=false
CELERY_BEAT_SCHEDULE_RETENTION_CLEANUP=false
CELERY_BEAT_SCHEDULE_VALIDATION=false

# ============================================================
# Bridge Agent Configuration
# ============================================================
BRIDGE_AGENTS=ZKTeco:{client_id}-zkteco-{generate_secret_key(20)}-{year}

# ============================================================
# SSH Deployment Configuration
# ============================================================
SSH_HOST={d['ssh_host']}
SSH_PORT={d['ssh_port']}
SSH_USER={d['ssh_user']}
SSH_PASSWORD={d['ssh_password']}
SSH_KEY_PATH={d['ssh_key']}
SSH_KEY_PASSPHRASE={d['ssh_passphrase']}
SSH_REMOTE_PATH={d['remote_path']}

# ============================================================
# Superuser Configuration
# ============================================================
SUPERUSER_USERNAME={d['su_username']}
SUPERUSER_EMAIL={d['su_email']}
SUPERUSER_PASSWORD={d['su_password']}
SUPERUSER_FIRST_NAME={d['su_first']}
SUPERUSER_LAST_NAME={d['su_last']}
"""


# ── main flow ───────────────────────────────────────────────────────────────

def create_client():
    project_root    = Path(__file__).parent.parent
    deployments_dir = Path(__file__).parent
    clients_file    = deployments_dir / "clients.json"

    print()
    print("=" * 60)
    print("  🏢  Create New Client")
    print("=" * 60)

    # ── 1. Basic Info ────────────────────────────────────────
    print()
    print("── 1. Basic Information ────────────────────────────")
    client_id   = ask("Client ID (English, no spaces)").lower().replace(' ', '_')
    client_name = ask("Client name", default=client_id)
    domain      = ask("Domain (e.g. mwheba.co.uk)")
    description = ask("Short description", default=f"ERP system for {client_name}", required=False)

    client_dir = deployments_dir / client_id
    client_exists = client_dir.exists()
    if client_exists:
        print(f"\n⚠️  Client '{client_id}' already exists at: {client_dir}")
        overwrite = input("  Update clients.json entry for this client? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("❌ Cancelled")
            return False

    # Create folder early because handle_ssh_key needs it
    client_dir.mkdir(parents=True, exist_ok=True)

    # ── 2. SSH ──────────────────────────────────────────────
    print()
    print("── 2. SSH Settings ─────────────────────────────────")
    ssh_host     = ask("Server address (IP or Domain)")
    ssh_port     = ask("SSH port", default="22")
    ssh_user     = ask("SSH username")
    ssh_password = ask("SSH password (leave empty if using Key)", required=False)

    # Move key automatically
    ssh_key, ssh_passphrase = handle_ssh_key(client_dir, project_root)

    remote_path = ask("Remote path on server (e.g. /home/user/project)")

    # ── 3. Database ──────────────────────────────────────────
    print()
    print("── 3. Database ─────────────────────────────────────")
    db_name     = ask("Database name", default=f"{client_id}_erp")
    db_user     = ask("Database user", default=f"{client_id}_erp")
    db_password = ask("Database password")

    # ── 4. Email ─────────────────────────────────────────────
    print()
    print("── 4. Email Configuration ──────────────────────────")
    email          = ask("Email address", default=f"info@{domain}")
    email_host     = ask("SMTP Host", default=f"mail.{domain}")
    email_password = ask("Email password")

    # ── 5. Superuser ─────────────────────────────────────────
    print()
    print("── 5. Superuser Credentials ────────────────────────")
    su_username = ask("Admin username", default="admin")
    su_email    = ask("Admin email", default=email)
    su_password = ask("Admin password")
    su_first    = ask("First name", default="System")
    su_last     = ask("Last name", default="Administrator")

    # ── Notes ────────────────────────────────────────────────
    print()
    notes = ask("Additional notes (optional)", required=False)

    # ── Summary ──────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  📋  Summary")
    print("=" * 60)
    print(f"  ID          : {client_id}")
    print(f"  Name        : {client_name}")
    print(f"  Domain      : {domain}")
    print(f"  Server      : {ssh_host}:{ssh_port}  ({ssh_user})")
    print(f"  SSH Key     : {ssh_key or 'None (password only)'}")
    print(f"  Remote Path : {remote_path}")
    print(f"  DB          : {db_name} / {db_user}")
    print(f"  Email       : {email}")
    print(f"  Superuser   : {su_username} / {su_email}")
    print("=" * 60)
    print()

    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        # Remove folder if it was just created and is empty
        if client_dir.exists() and not any(client_dir.iterdir()):
            client_dir.rmdir()
        print("❌ Cancelled")
        return False

    # ── Create files ─────────────────────────────────────────
    try:
        data = dict(
            client_id=client_id, domain=domain,
            secret_key=generate_secret_key(50),
            db_name=db_name, db_user=db_user, db_password=db_password,
            ssh_host=ssh_host, ssh_port=ssh_port, ssh_user=ssh_user,
            ssh_password=ssh_password, ssh_key=ssh_key, ssh_passphrase=ssh_passphrase,
            remote_path=remote_path,
            email=email, email_host=email_host, email_password=email_password,
            su_username=su_username, su_email=su_email, su_password=su_password,
            su_first=su_first, su_last=su_last,
        )

        # clients.json - first to ensure it's always updated
        clients_data = {}
        if clients_file.exists():
            clients_data = json.loads(clients_file.read_text(encoding='utf-8'))
        clients_data.setdefault('clients', {})[client_id] = {
            "name": client_name,
            "domain": domain,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "remote_path": remote_path,
            "description": description,
            "active": True,
            "created_date": datetime.now().strftime('%Y-%m-%d'),
            "notes": notes,
        }
        clients_file.write_text(
            json.dumps(clients_data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        print(f"\n  ✅ {clients_file.relative_to(project_root)}")

        # .env
        env_path = client_dir / ".env"
        env_path.write_text(generate_env_file(data), encoding='utf-8')
        print(f"  ✅ {env_path.relative_to(project_root)}")

        # passenger_wsgi.py
        wsgi_path = client_dir / "passenger_wsgi.py"
        wsgi_path.write_text(f"""import os
import sys
import gc

# مسار المشروع
PROJECT_PATH = '{remote_path}'
sys.path.insert(0, PROJECT_PATH)

# اسم settings
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'corporate_erp.settings'
)

# Reduce GC frequency - default (700,10,10) is fine for shared hosting
gc.set_threshold(700, 10, 10)

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
""", encoding='utf-8')
        print(f"  ✅ {wsgi_path.relative_to(project_root)}")

        # notes.md
        key_info = f"- **SSH Key**: `{ssh_key}`" if ssh_key else "- **SSH Auth**: Password only"
        notes_path = client_dir / "notes.md"
        notes_path.write_text(f"""# Deployment Notes - {client_name}

## Client Info
- **Name**: {client_name}
- **Domain**: {domain}
- **Created**: {datetime.now().strftime('%Y-%m-%d')}

## Server
- **IP**: {ssh_host}
- **Port**: {ssh_port}
- **User**: {ssh_user}
- **Path**: {remote_path}
{key_info}

## Database
- **Database**: {db_name}
- **User**: {db_user}

## Email
- **Address**: {email}
- **SMTP**: {email_host}:587

## Superuser
- **Username**: {su_username}
- **Email**: {su_email}

## Notes
{notes if notes else 'No additional notes'}

## Checklist
- [ ] Create database on server
- [ ] Create email account
- [ ] Upload files (first deploy)
- [ ] Run migrations
- [ ] Create superuser
- [ ] Test the system
""", encoding='utf-8')
        print(f"  ✅ {notes_path.relative_to(project_root)}")

        print()
        print("=" * 60)
        print("  🎉  Client created successfully!")
        print("=" * 60)
        print()
        print("  Next steps:")
        print(f"  1. Test connection : python deploy.py --client {client_id} --mode test")
        print(f"  2. First deploy    : python deploy.py --client {client_id} --mode all")
        print()
        print("  ⚠️  Keep a backup of .env in a safe place outside Git")
        print()
        return True

    except Exception as e:
        print(f"\n❌ Error during creation: {e}")
        return False


if __name__ == "__main__":
    try:
        success = create_client()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled")
        sys.exit(1)
