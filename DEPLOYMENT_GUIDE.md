# دليل النشر وتشغيل الإنتاج الشامل — MWHEBA ERP 🚀

> **المرجع التنفيذي لنشر وتشغيل نظام MWHEBA ERP في بيئات الإنتاج الحقيقية**  
> يوثق هذا الدليل آليات النشر الفعلية المعمول بها في المشروع: استضافات **cPanel / CloudLinux (Phusion Passenger)**، وخوادم **Linux VPS (Ubuntu / Nginx / Gunicorn)** المعتمدة على **MySQL 8.0**.

---

## 📋 1. متطلبات النظام الأساسية

### البيئة البرمجية القياسية
- **Python**: 3.11 أو 3.12 أو 3.13 (الموصى به: Python 3.11+)
- **Django**: **5.2 LTS**
- **قاعدة البيانات**: **MySQL 8.0+** أو MariaDB 10.5+ (مع دعم كامل لـ `utf8mb4`)
- **خادم التخزين المؤقت**: Redis 6+ (اختياري للـ Caching والمهام الخلفية)
- **محرك التشغيل**:
  - خيار أ (الأساسي للعملاء): **Phusion Passenger** (عبر cPanel / CloudLinux).
  - خيار ب (الخوادم المخصصة): **Gunicorn + Nginx** (على Ubuntu 22.04 LTS).

---

## 🗄️ 2. إعداد وضبط قاعدة البيانات (MySQL 8.0)

النظام مصمم للعمل مع **MySQL** كقاعدة بيانات الإنتاج القياسية (تم حظر واستئصال PostgreSQL لعدم تطابقه مع كود `corporate_erp/settings.py`).

### أ) إنشاء قاعدة البيانات والمستخدم
قم بتسجيل الدخول إلى سيرفر MySQL:
```bash
mysql -u root -p
```

نفذ استعلامات التهيئة المتوافقة مع معايير المشروع:
```sql
-- 1. إنشاء قاعدة البيانات بترميز utf8mb4 الكامل
CREATE DATABASE mwheba_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. إنشاء مستخدم مخصص مع كلمة مرور قوية
CREATE USER 'mwheba_user'@'localhost' IDENTIFIED BY 'Your_Strong_Password_Here!';

-- 3. منح كافة الصلاحيات على قاعدة البيانات
GRANT ALL PRIVILEGES ON mwheba_erp.* TO 'mwheba_user'@'localhost';

-- 4. تطبيق التغييرات
FLUSH PRIVILEGES;
EXIT;
```

### ب) ضبط خادم MySQL (`my.cnf`)
لضمان استقرار العمليات المحاسبية ومنع اقتطاع النصوص العربية:
```ini
[mysqld]
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
sql_mode = "STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
max_connections = 300
connect_timeout = 60
wait_timeout = 300
interactive_timeout = 300
```

---

## ⚙️ 3. تكوين المتغيرات البيئية (`.env`)

أنشئ ملف `.env` في جذر المشروع ليتطابق مع شروط `corporate_erp/settings.py`:

```env
# إعدادات Django الأساسية
SECRET_KEY=your-production-super-secret-key-change-in-prod
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,127.0.0.1

# محرك وقاعدة البيانات (MySQL حصراً)
DB_ENGINE=mysql
DB_NAME=mwheba_erp
DB_USER=mwheba_user
DB_PASSWORD=Your_Strong_Password_Here!
DB_HOST=127.0.0.1
DB_PORT=3306

# إعدادات التخزين المؤقت (Redis)
REDIS_URL=redis://127.0.0.1:6379/0

# إعدادات الأمان
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
X_FRAME_OPTIONS=DENY
SECURE_HSTS_SECONDS=31536000

# تنبيه هندسي لقواعد الاتصال
# في settings.py تم ضبط CONN_MAX_AGE = 0 لمنع أخطاء Command Out of Sync
# على سيرفرات الاستضافة المشتركة و cPanel، مع تفعيل CONN_HEALTH_CHECKS = True
```

---

## 🌐 4. خيار النشر الأول (الأساسي): cPanel / CloudLinux Passenger

هذا هو الخيار الفعلي المطبق في بيئات عملاء MWHEBA ERP الموثقة في مجلد `deployments/`.

### خطوات النشر عبر cPanel:
1. **إنشاء تطبيق Python من لوحة cPanel**:
   - توجه إلى **Setup Python App**.
   - اختر إصدار Python (3.11 أو 3.12).
   - حدد مسار التطبيق (Application Root): مثلاً `mwheba_erp`.
   - حدد مسار الـ URI (Application URL): النطاق الأساسي أو الفرعي.
2. **رفع الكود وملفات المشروع**:
   - رفع الكود المصدري داخل مجلد التطبيق.
3. **ضبط ملف `passenger_wsgi.py`**:
   تأكد من وجود ملف `passenger_wsgi.py` في جذر المشروع بهذا المحتوى القياسي:
   ```python
   import os
   import sys

   # تحديد مسار المشروع والبيئة الافتراضية
   app_path = os.path.dirname(os.path.abspath(__file__))
   sys.path.insert(0, app_path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'corporate_erp.settings'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
4. **تثبيت الاعتماديات عبر SSH أو cPanel Terminal**:
   ```bash
   source /home/username/virtualenv/mwheba_erp/3.11/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
5. **تطبيق الميجريشن وتجميع الملفات الثابتة**:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
6. **إعادة تشغيل التطبيق**:
   - الضغط على **Restart** من واجهة cPanel Python App، أو إنشاء ملف لإعادة التشغيل:
     ```bash
     touch tmp/restart.txt
     ```

---

## 🖥️ 5. خيار النشر الثاني: خادم Linux VPS مخصص (Ubuntu 22.04 LTS)

### أ) تثبيت الحزم الأساسية على السيرفر
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev default-libmysqlclient-dev pkg-config mysql-server redis-server nginx supervisor git
```

### ب) إعداد بيئة التطبيق
```bash
sudo mkdir -p /var/www/mwheba_erp
sudo chown -R $USER:$USER /var/www/mwheba_erp
cd /var/www/mwheba_erp

# استنساخ الكود وإنشاء البيئة الافتراضية
git clone https://github.com/your-repo/mwheba-erp.git .
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# إعداد ملف .env وتطبيق الميجريشن
cp .env.example .env
# قم بتعديل بيانات الداتابيز في .env
python manage.py migrate
python manage.py collectstatic --noinput
```

### ج) تكوين Gunicorn (`/etc/systemd/system/gunicorn.service`)
```ini
[Unit]
Description=gunicorn daemon for MWHEBA ERP
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/mwheba_erp
ExecStart=/var/www/mwheba_erp/venv/bin/gunicorn \
          --access-logfile /var/log/mwheba_erp/access.log \
          --error-logfile /var/log/mwheba_erp/error.log \
          --workers 3 \
          --bind unix:/run/gunicorn_mwheba.sock \
          corporate_erp.wsgi:application

[Install]
WantedBy=multi-user.target
```

### د) تكوين Nginx (`/etc/nginx/sites-available/mwheba_erp`)
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    client_max_body_size 50M;

    location /static/ {
        alias /var/www/mwheba_erp/staticfiles/;
        expires 30d;
        access_log off;
    }

    location /media/ {
        alias /var/www/mwheba_erp/media/;
        expires 7d;
        access_log off;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn_mwheba.sock;
    }
}
```

---

## ⏱️ 6. تشغيل المهام الخلفية المجدولة (Celery Worker & Beat)

لتشغيل معالجة سجلات البصمات كل 5 دقائق والتسويات المالية عبر Supervisor:

```ini
; /etc/supervisor/conf.d/mwheba_celery.conf

[program:mwheba_celery_worker]
command=/var/www/mwheba_erp/venv/bin/celery -A corporate_erp worker -l info -Q notifications,reports,accounting,bulk_processing
directory=/var/www/mwheba_erp
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/mwheba_erp/celery_worker.log

[program:mwheba_celery_beat]
command=/var/www/mwheba_erp/venv/bin/celery -A corporate_erp beat -l info
directory=/var/www/mwheba_erp
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/mwheba_erp/celery_beat.log
```

---

## 🔒 7. خطة النسخ الاحتياطي التلقائي (MySQL Backup Automation)

سكريبت النسخ الاحتياطي اليومي لقاعدة بيانات MySQL:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/mwheba_erp"
DATE=$(date +"%Y%m%d_%H%M%S")
mkdir -p $BACKUP_DIR

# أخذ نسخة احتياطية مشفرة بـ mysqldump
mysqldump -u mwheba_user -p'Your_Strong_Password_Here!' --single-transaction --quick --routines mwheba_erp | gzip > "$BACKUP_DIR/db_backup_$DATE.sql.gz"

# الاحتفاظ بنسخ آخر 30 يوماً فقط
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +30 -delete
```
قم بجدولة السكريبت في `crontab` ليعمل يومياً في تمام الساعة 2:00 صباحاً.
