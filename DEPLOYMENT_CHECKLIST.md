# ✅ قائمة التحقق قبل النشر - Deployment Checklist

**المشروع:** MWHEBA ERP  
**التاريخ:** 2025-11-02  
**الإصدار:** 1.0.0

---

## 🔴 حرجة - يجب إصلاحها قبل النشر

### 1. إعدادات الأمان
- [ ] **SECRET_KEY** - توليد key جديد وآمن
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] **DEBUG=False** - تعطيل وضع التطوير
- [ ] **ALLOWED_HOSTS** - تحديد الدومينات المسموحة فقط
- [ ] **SECURE_SSL_REDIRECT=True** - إجبار HTTPS
- [ ] **SESSION_COOKIE_SECURE=True** - تأمين cookies
- [ ] **CSRF_COOKIE_SECURE=True** - تأمين CSRF

### 2. قاعدة البيانات
- [ ] استخدام PostgreSQL بدلاً من SQLite
- [ ] إعداد backup تلقائي يومي
- [ ] اختبار استعادة backup
- [ ] تفعيل connection pooling

### 3. كلمات المرور والمفاتيح
- [ ] تغيير **EMAIL_HOST_PASSWORD** من الملف
- [ ] تغيير **DAFTRA_API_KEY** إذا كان مكشوف
- [ ] تأمين ملف `.env` (chmod 600)
- [ ] عدم رفع `.env` على Git

---

## 🟡 مهمة - يُنصح بها بشدة

### 4. الأداء
- [ ] تفعيل **Redis** للـ caching
  ```env
  REDIS_URL=redis://localhost:6379/0
  ```
- [ ] تشغيل `collectstatic`
  ```bash
  python manage.py collectstatic --noinput
  ```
- [ ] تفعيل compression للملفات الثابتة
- [ ] إعداد CDN للملفات الثابتة (اختياري)

### 5. المراقبة والأخطاء
- [ ] تفعيل **Sentry** لتتبع الأخطاء
  ```env
  SENTRY_DSN=https://xxxxx@xxxxx.ingest.sentry.io/xxxxx
  ```
- [ ] إعداد log files
  ```env
  LOG_LEVEL=WARNING
  LOG_FILE=/var/log/mwheba_erp/app.log
  ```
- [ ] إعداد monitoring للخادم (CPU, Memory, Disk)

### 6. النسخ الاحتياطي
- [ ] إعداد cron للنسخ الاحتياطي اليومي
  ```bash
  0 2 * * * cd /path/to/mwheba_erp && python manage.py backup_database --compress --upload-s3 --cleanup
  ```
- [ ] إعداد AWS S3 للنسخ الاحتياطية
- [ ] اختبار استعادة backup مرة واحدة

---

## 🟢 اختيارية - تحسينات إضافية

### 7. الأداء المتقدم
- [ ] إعداد Nginx reverse proxy
- [ ] تفعيل Gzip compression
- [ ] إعداد Browser caching headers
- [ ] تحسين Database indexes

### 8. الأمان المتقدم
- [ ] إعداد Firewall rules
- [ ] تفعيل fail2ban
- [ ] إعداد SSL certificate (Let's Encrypt)
- [ ] تفعيل rate limiting

### 9. المراقبة المتقدمة
- [ ] إعداد uptime monitoring
- [ ] إعداد performance monitoring
- [ ] إعداد alerts للأخطاء الحرجة
- [ ] إعداد Google Analytics (اختياري)

---

## 📋 خطوات النشر

### المرحلة 1: الإعداد المحلي
```bash
# 1. تحديث المكتبات
pip install -r requirements.txt

# 2. إعداد ملف .env للإنتاج
cp .env.production.example .env
# تحرير .env وإضافة القيم الصحيحة

# 3. اختبار الإعدادات
python manage.py check --deploy

# 4. تشغيل migrations
python manage.py migrate

# 5. جمع الملفات الثابتة
python manage.py collectstatic --noinput

# 6. إنشاء superuser
python manage.py createsuperuser
```

### المرحلة 2: النشر على الخادم
```bash
# 1. رفع الملفات على الخادم
rsync -avz --exclude='.env' --exclude='*.pyc' . user@server:/path/to/mwheba_erp/

# 2. تثبيت المكتبات على الخادم
ssh user@server
cd /path/to/mwheba_erp
pip install -r requirements.txt

# 3. إعداد ملف .env على الخادم
nano .env
# إضافة القيم الصحيحة

# 4. تشغيل migrations
python manage.py migrate

# 5. جمع الملفات الثابتة
python manage.py collectstatic --noinput

# 6. إعادة تشغيل الخادم
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

### المرحلة 3: التحقق بعد النشر
```bash
# 1. اختبار الموقع
curl -I https://www.mwheba.co.uk

# 2. التحقق من Redis
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'OK')
>>> cache.get('test')

# 3. التحقق من Sentry
# إرسال رسالة تجريبية من Sentry dashboard

# 4. اختبار النسخ الاحتياطي
python manage.py backup_database --compress

# 5. مراقبة logs
tail -f /var/log/mwheba_erp/app.log
```

---

## 🔍 التحقق النهائي

### الأمان
- [ ] ✅ DEBUG=False
- [ ] ✅ SECRET_KEY آمن ومختلف عن التطوير
- [ ] ✅ HTTPS مفعل
- [ ] ✅ Security headers مفعلة
- [ ] ✅ ملف .env محمي (chmod 600)

### الأداء
- [ ] ✅ Redis يعمل
- [ ] ✅ Static files محملة
- [ ] ✅ Database optimized
- [ ] ✅ Caching مفعل

### الموثوقية
- [ ] ✅ Sentry يعمل
- [ ] ✅ Backup تلقائي مجدول
- [ ] ✅ Logs تعمل
- [ ] ✅ Monitoring مفعل

### الوظائف
- [ ] ✅ تسجيل الدخول يعمل
- [ ] ✅ البريد الإلكتروني يعمل
- [ ] ✅ جميع الصفحات تعمل
- [ ] ✅ لا توجد أخطاء في logs

---

## 📞 في حالة المشاكل

### مشكلة: الموقع لا يعمل
1. تحقق من logs: `tail -f /var/log/nginx/error.log`
2. تحقق من Gunicorn: `sudo systemctl status gunicorn`
3. تحقق من .env: `cat .env | grep DEBUG`

### مشكلة: Static files لا تظهر
1. تشغيل: `python manage.py collectstatic --noinput`
2. تحقق من STATIC_ROOT في .env
3. تحقق من Nginx configuration

### مشكلة: Database errors
1. تحقق من DATABASE_URL في .env
2. تشغيل: `python manage.py migrate`
3. تحقق من صلاحيات قاعدة البيانات

### مشكلة: Redis لا يعمل
1. تحقق من Redis: `redis-cli ping`
2. تشغيل Redis: `sudo systemctl start redis`
3. تحقق من REDIS_URL في .env

---

## 📊 ملخص الحالة الحالية

### ✅ جاهز
- [x] الكود نظيف ومنظم
- [x] Tests شاملة (315+ اختبار)
- [x] Documentation كاملة
- [x] Redis configuration جاهز
- [x] Sentry configuration جاهز
- [x] Backup system جاهز

### ⚠️ يحتاج إصلاح
- [ ] **SECRET_KEY** - توليد key جديد
- [ ] **DEBUG** - تغيير إلى False
- [ ] **Security settings** - تفعيل HTTPS settings
- [ ] **Database** - التحويل إلى PostgreSQL
- [ ] **Redis** - تثبيت وتشغيل Redis server
- [ ] **Sentry** - الحصول على DSN وتفعيله

---

## 🎯 الخطوات التالية

1. **اليوم:**
   - [ ] توليد SECRET_KEY جديد
   - [ ] إعداد ملف .env للإنتاج
   - [ ] اختبار على staging environment

2. **قبل النشر:**
   - [ ] تثبيت Redis على الخادم
   - [ ] إعداد PostgreSQL
   - [ ] إعداد Sentry account
   - [ ] إعداد AWS S3 للbackups

3. **بعد النشر:**
   - [ ] مراقبة logs لمدة 24 ساعة
   - [ ] اختبار جميع الوظائف
   - [ ] التحقق من Backup التلقائي
   - [ ] مراقبة Sentry dashboard

---

**آخر تحديث:** 2025-11-02  
**الحالة:** جاهز للنشر بعد إصلاح النقاط الحرجة ⚠️
