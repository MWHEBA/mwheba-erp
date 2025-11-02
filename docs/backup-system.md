# 💾 نظام النسخ الاحتياطي التلقائي

**الإصدار:** 1.0.0  
**التاريخ:** 2025-11-02  
**الحالة:** مكتمل ✅

---

## 📋 نظرة عامة

نظام النسخ الاحتياطي التلقائي يوفر حماية شاملة للبيانات مع دعم PostgreSQL و SQLite، والرفع التلقائي على AWS S3.

---

## 🚀 الاستخدام

### 1. النسخ الاحتياطي الأساسي

```bash
# نسخ احتياطي بسيط
python manage.py backup_database

# نسخ احتياطي مع الضغط
python manage.py backup_database --compress

# نسخ احتياطي مع الرفع على S3
python manage.py backup_database --compress --upload-s3

# نسخ احتياطي مع تنظيف النسخ القديمة
python manage.py backup_database --compress --cleanup --retention-days 30
```

### 2. النسخ الاحتياطي التلقائي (Cron)

#### Linux/Mac:
```bash
# فتح crontab
crontab -e

# إضافة مهمة يومية في الساعة 2 صباحاً
0 2 * * * cd /path/to/mwheba_erp && /path/to/python manage.py backup_database --compress --upload-s3 --cleanup >> /var/log/mwheba_backup.log 2>&1
```

#### Windows (Task Scheduler):
```powershell
# إنشاء مهمة مجدولة
schtasks /create /tn "MWHEBA_Backup" /tr "C:\path\to\python.exe C:\path\to\mwheba_erp\manage.py backup_database --compress --upload-s3 --cleanup" /sc daily /st 02:00
```

---

## ⚙️ الإعدادات

### متغيرات البيئة (.env)

```env
# مجلد النسخ الاحتياطية المحلية
BACKUP_DIR=backups

# عدد الأيام للاحتفاظ بالنسخ الاحتياطية
BACKUP_RETENTION_DAYS=30

# إعدادات AWS S3 (اختياري)
BACKUP_S3_BUCKET=mwheba-erp-backups
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

---

## 📦 أنواع النسخ الاحتياطي

### PostgreSQL
- يستخدم `pg_dump` لإنشاء نسخة SQL كاملة
- يدعم الضغط باستخدام gzip
- حجم الملف: متوسط إلى كبير (حسب حجم البيانات)

### SQLite
- نسخ مباشر لملف قاعدة البيانات
- سريع وبسيط
- حجم الملف: صغير إلى متوسط

---

## ☁️ الرفع على AWS S3

### المتطلبات:
1. حساب AWS نشط
2. S3 Bucket مُنشأ
3. IAM User مع صلاحيات S3

### الصلاحيات المطلوبة (IAM Policy):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::mwheba-erp-backups",
        "arn:aws:s3:::mwheba-erp-backups/*"
      ]
    }
  ]
}
```

### إنشاء S3 Bucket:
```bash
# باستخدام AWS CLI
aws s3 mb s3://mwheba-erp-backups --region us-east-1

# تفعيل Versioning
aws s3api put-bucket-versioning \
  --bucket mwheba-erp-backups \
  --versioning-configuration Status=Enabled

# تفعيل Lifecycle Policy (حذف تلقائي بعد 90 يوم)
aws s3api put-bucket-lifecycle-configuration \
  --bucket mwheba-erp-backups \
  --lifecycle-configuration file://lifecycle.json
```

---

## 🗑️ تنظيف النسخ القديمة

### تلقائي:
```bash
# حذف النسخ الأقدم من 30 يوم
python manage.py backup_database --cleanup --retention-days 30
```

### يدوي:
```bash
# عرض النسخ الاحتياطية
ls -lh backups/

# حذف نسخة محددة
rm backups/backup_20250101_020000.sql.gz
```

---

## 🔄 استعادة النسخة الاحتياطية

### PostgreSQL:
```bash
# فك ضغط الملف (إذا كان مضغوطاً)
gunzip backup_20250102_020000.sql.gz

# استعادة قاعدة البيانات
psql -h localhost -U postgres -d mwheba_erp < backup_20250102_020000.sql
```

### SQLite:
```bash
# فك ضغط الملف (إذا كان مضغوطاً)
gunzip backup_20250102_020000.db.gz

# استبدال قاعدة البيانات
cp backup_20250102_020000.db db.sqlite3
```

### من S3:
```bash
# تحميل من S3
aws s3 cp s3://mwheba-erp-backups/backups/backup_20250102_020000.sql.gz .

# ثم استعادة كما في الأعلى
```

---

## 📊 مراقبة النسخ الاحتياطي

### سجلات النظام:
```bash
# عرض آخر 50 سطر من السجل
tail -n 50 /var/log/mwheba_backup.log

# متابعة السجل مباشرة
tail -f /var/log/mwheba_backup.log
```

### التحقق من النسخ الاحتياطية:
```bash
# عرض جميع النسخ المحلية
ls -lh backups/

# عرض جميع النسخ على S3
aws s3 ls s3://mwheba-erp-backups/backups/

# حساب حجم جميع النسخ
du -sh backups/
```

---

## ⚠️ أفضل الممارسات

### 1. النسخ الاحتياطي المنتظم
- ✅ نسخ احتياطي يومي على الأقل
- ✅ نسخ احتياطي قبل التحديثات الكبيرة
- ✅ نسخ احتياطي قبل migrations

### 2. التخزين الآمن
- ✅ تخزين النسخ في مكان منفصل عن الخادم
- ✅ استخدام S3 أو خدمة سحابية أخرى
- ✅ تشفير النسخ الاحتياطية الحساسة

### 3. الاختبار الدوري
- ✅ اختبار استعادة النسخة الاحتياطية شهرياً
- ✅ التحقق من سلامة الملفات
- ✅ توثيق عملية الاستعادة

### 4. المراقبة والتنبيهات
- ✅ مراقبة نجاح/فشل النسخ الاحتياطي
- ✅ تنبيهات عند فشل النسخ الاحتياطي
- ✅ مراقبة مساحة التخزين

---

## 🔧 استكشاف الأخطاء

### خطأ: pg_dump not found
```bash
# تثبيت PostgreSQL client
# Ubuntu/Debian
sudo apt-get install postgresql-client

# CentOS/RHEL
sudo yum install postgresql

# Windows
# تحميل من https://www.postgresql.org/download/windows/
```

### خطأ: Permission denied
```bash
# منح صلاحيات للمجلد
chmod 755 backups/

# منح صلاحيات للملفات
chmod 644 backups/*
```

### خطأ: S3 upload failed
```bash
# التحقق من AWS credentials
aws configure list

# اختبار الاتصال بـ S3
aws s3 ls s3://mwheba-erp-backups/
```

---

## 📞 الدعم

للمساعدة أو الإبلاغ عن مشاكل:
- 📧 البريد الإلكتروني: support@mwheba.com
- 📱 الهاتف: +20 XXX XXX XXXX
- 🌐 الموقع: https://mwheba.com

---

**تم إعداد هذا التوثيق بواسطة:** Cascade AI  
**آخر تحديث:** 2025-11-02  
**الحالة:** مكتمل ✅
