# دليل النشر - Corporate ERP

## نظرة عامة

هذا الدليل يوضح كيفية نشر النظام في بيئة الإنتاج مع جميع التحسينات والتكوينات المطلوبة.

## 📋 متطلبات النظام

### الحد الأدنى للمتطلبات

- **نظام التشغيل**: Ubuntu 20.04 LTS أو أحدث / CentOS 8 أو أحدث
- **الذاكرة**: 4 GB RAM (8 GB مُوصى به)
- **المعالج**: 2 CPU cores (4 cores مُوصى به)
- **التخزين**: 50 GB مساحة فارغة (100 GB مُوصى به)
- **الشبكة**: اتصال إنترنت مستقر

### البرامج المطلوبة

- Python 3.9+
- PostgreSQL 13+
- Redis 6+
- Nginx 1.18+
- Supervisor
- Git

## 🚀 خطوات النشر

### 1. إعداد الخادم

```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت البرامج الأساسية
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib redis-server nginx supervisor git

# تثبيت مكتبات إضافية
sudo apt install -y build-essential libpq-dev python3-dev
```

### 2. إعداد قاعدة البيانات

```bash
# تسجيل الدخول إلى PostgreSQL
sudo -u postgres psql

# إنشاء قاعدة البيانات والمستخدم
CREATE DATABASE corporate_erp;
CREATE USER erp_user WITH PASSWORD 'secure_password_here';
ALTER ROLE erp_user SET client_encoding TO 'utf8';
ALTER ROLE erp_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE erp_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE corporate_erp TO erp_user;
\q
```

### 3. إعداد Redis

```bash
# تحرير تكوين Redis
sudo nano /etc/redis/redis.conf

# إضافة كلمة مرور (اختياري)
requirepass your_redis_password_here

# إعادة تشغيل Redis
sudo systemctl restart redis-server
sudo systemctl enable redis-server
```

### 4. نسخ المشروع

```bash
# إنشاء مستخدم للتطبيق
sudo adduser --system --group --home /opt/corporate_erp erp_app

# التبديل للمستخدم الجديد
sudo -u erp_app -i

# نسخ المشروع
cd /opt/corporate_erp
git clone https://github.com/your-repo/corporate-erp.git .

# إنشاء البيئة الافتراضية
python3 -m venv venv
source venv/bin/activate

# تثبيت المتطلبات
pip install -r requirements.txt
```

### 5. تكوين المتغيرات البيئية

```bash
# إنشاء ملف .env
sudo -u erp_app nano /opt/corporate_erp/.env
```

```env
# إعدادات Django
SECRET_KEY=your_very_secure_secret_key_here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,server-ip

# قاعدة البيانات
DB_ENGINE=postgresql
DB_NAME=corporate_erp
DB_USER=erp_user
DB_PASSWORD=secure_password_here
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# البريد الإلكتروني
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# Sentry (اختياري)
SENTRY_DSN=your-sentry-dsn-here

# إعدادات الأمان
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

### 6. إعداد قاعدة البيانات

```bash
# تطبيق الهجرات
sudo -u erp_app -i
cd /opt/corporate_erp
source venv/bin/activate

python manage.py migrate
python manage.py collectstatic --noinput

# إنشاء مستخدم مدير
python manage.py createsuperuser

# تحميل البيانات الأولية (اختياري)
python manage.py loaddata initial_data.json
```

### 7. تكوين Gunicorn

```bash
# إنشاء ملف تكوين Gunicorn
sudo nano /opt/corporate_erp/gunicorn.conf.py
```

```python
# Gunicorn Configuration
bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2
preload_app = True
user = "erp_app"
group = "erp_app"
tmp_upload_dir = None
errorlog = "/var/log/corporate_erp/gunicorn_error.log"
accesslog = "/var/log/corporate_erp/gunicorn_access.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
loglevel = "info"
```

### 8. تكوين Supervisor

```bash
# إنشاء ملف تكوين Supervisor
sudo nano /etc/supervisor/conf.d/corporate_erp.conf
```

```ini
[program:corporate_erp]
command=/opt/corporate_erp/venv/bin/gunicorn corporate_erp.wsgi:application -c /opt/corporate_erp/gunicorn.conf.py
directory=/opt/corporate_erp
user=erp_app
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/corporate_erp/supervisor.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/opt/corporate_erp/venv/bin"
```

```bash
# إعادة تحميل Supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start corporate_erp
```

### 9. تكوين Nginx

```bash
# إنشاء ملف تكوين Nginx
sudo nano /etc/nginx/sites-available/corporate_erp
```

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;

    # Static Files
    location /static/ {
        alias /opt/corporate_erp/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/corporate_erp/media/;
        expires 1y;
        add_header Cache-Control "public";
    }

    # Health Check
    location /health/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        access_log off;
    }

    # Main Application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    # Rate Limiting
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Rate Limiting Configuration
http {
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
}
```

```bash
# تفعيل الموقع
sudo ln -s /etc/nginx/sites-available/corporate_erp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 10. إعداد SSL Certificate

```bash
# تثبيت Certbot
sudo apt install certbot python3-certbot-nginx

# الحصول على شهادة SSL
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# إعداد التجديد التلقائي
sudo crontab -e
# إضافة السطر التالي:
0 12 * * * /usr/bin/certbot renew --quiet
```

## 📊 إعداد المراقبة

### 1. إعداد السجلات

```bash
# إنشاء مجلدات السجلات
sudo mkdir -p /var/log/corporate_erp
sudo chown erp_app:erp_app /var/log/corporate_erp

# إعداد دوران السجلات
sudo cp corporate-erp-logrotate /etc/logrotate.d/
```

### 2. إعداد المراقبة الصحية

```bash
# إضافة فحص صحي إلى crontab
sudo crontab -e
# إضافة:
*/5 * * * * curl -f http://localhost/health/ || echo "Health check failed" | mail -s "Corporate ERP Health Alert" admin@company.com
```

## 🔒 إعدادات الأمان

### 1. جدار الحماية

```bash
# تكوين UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 2. تحديثات الأمان

```bash
# إعداد التحديثات التلقائية
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 3. مراقبة الأمان

```bash
# تثبيت fail2ban
sudo apt install fail2ban

# تكوين fail2ban
sudo nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
action = iptables-multiport[name=ReqLimit, port="http,https", protocol=tcp]
logpath = /var/log/nginx/error.log
maxretry = 10
findtime = 600
bantime = 7200
```

## 📦 النسخ الاحتياطية

### 1. إعداد النسخ الاحتياطية التلقائية

```bash
# إنشاء سكريبت النسخ الاحتياطي
sudo nano /opt/corporate_erp/backup.sh
```

```bash
#!/bin/bash
# Corporate ERP Backup Script

BACKUP_DIR="/var/backups/corporate_erp"
DATE=$(date +%Y%m%d_%H%M%S)
DB_BACKUP="$BACKUP_DIR/db_backup_$DATE.sql"
MEDIA_BACKUP="$BACKUP_DIR/media_backup_$DATE.tar.gz"

# إنشاء مجلد النسخ الاحتياطية
mkdir -p $BACKUP_DIR

# نسخ احتياطية لقاعدة البيانات
pg_dump -h localhost -U erp_user -d corporate_erp > $DB_BACKUP

# ضغط النسخة الاحتياطية
gzip $DB_BACKUP

# نسخ احتياطية للملفات
tar -czf $MEDIA_BACKUP /opt/corporate_erp/media/

# حذف النسخ القديمة (أكثر من 30 يوم)
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

```bash
# جعل السكريبت قابل للتنفيذ
sudo chmod +x /opt/corporate_erp/backup.sh

# إضافة إلى crontab
sudo crontab -e
# إضافة:
0 2 * * * /opt/corporate_erp/backup.sh
```

## 🔧 استكشاف الأخطاء وإصلاحها

### مشاكل شائعة وحلولها

#### 1. خطأ في الاتصال بقاعدة البيانات

```bash
# فحص حالة PostgreSQL
sudo systemctl status postgresql

# فحص السجلات
sudo tail -f /var/log/postgresql/postgresql-13-main.log

# إعادة تشغيل الخدمة
sudo systemctl restart postgresql
```

#### 2. مشاكل في الأداء

```bash
# فحص استخدام الموارد
htop
df -h
free -m

# فحص سجلات الأداء
tail -f /var/log/corporate_erp/performance.log
```

#### 3. مشاكل SSL

```bash
# فحص شهادة SSL
sudo certbot certificates

# تجديد الشهادة يدوياً
sudo certbot renew --dry-run
```

## 📈 تحسين الأداء

### 1. تحسين PostgreSQL

```sql
-- في ملف postgresql.conf
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
```

### 2. تحسين Redis

```bash
# في ملف redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### 3. تحسين Nginx

```nginx
# في ملف nginx.conf
worker_processes auto;
worker_connections 1024;
keepalive_timeout 65;
client_max_body_size 50M;
```

## 📞 الدعم والصيانة

### جهات الاتصال

- **الدعم التقني**: tech-support@company.com
- **الطوارئ**: +20-xxx-xxx-xxxx
- **التوثيق**: https://docs.company.com

### جدولة الصيانة

- **النسخ الاحتياطية**: يومياً في الساعة 2:00 صباحاً
- **تحديثات الأمان**: أسبوعياً يوم الأحد
- **صيانة النظام**: شهرياً في نهاية الشهر

---

**تم إنشاء هذا الدليل كجزء من المهمة 7.4 - إنشاء أدلة النشر والصيانة**
