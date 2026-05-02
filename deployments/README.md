# نظام إدارة النسخ المتعددة - Multi-Deployment System

## الهدف
إدارة نسخ متعددة من النظام لعملاء مختلفين من source code واحد.

## البنية

```
deployments/
├── README.md                        ← هذا الملف
├── clients.json                     ← قائمة جميع العملاء
├── create_client.py                 ← سكريپت إنشاء عميل جديد
├── baraka/                          ← مجلد عميل Baraka
│   ├── .env.production             ← إعدادات الإنتاج (محمي من Git)
│   ├── deploy_logs/                ← سجلات النشر الخاصة بالعميل
│   └── notes.md                    ← ملاحظات العميل
└── template/                        ← قالب لعميل جديد
    └── .env.production.template
```

---

## الاستخدام اليومي

### عرض العملاء
```bash
python deploy.py --list-clients
```

### النشر لعميل
```bash
# اختبار الاتصال أولاً
python deploy.py --client baraka --mode test

# النشر العادي (رفع المعدل فقط - افتراضي)
python deploy.py --client baraka

# رفع جميع الملفات (للنشر الأول)
python deploy.py --client baraka --mode all
```

### أوضاع النشر

| الوضع | متى تستخدمه |
|-------|-------------|
| `test` | اختبار الاتصال |
| `modified` | النشر اليومي (افتراضي) |
| `all` | النشر الأول أو إعادة نشر كاملة |
| `sync` | رفع مع تخطي المطابق |
| `remote` | مقارنة مع السيرفر |
| `status` | عرض الحالة فقط |

---

## إضافة عميل جديد

### الطريقة السهلة (موصى بها)
```bash
python deployments/create_client.py
```

### الطريقة اليدوية
```bash
# 1. نسخ القالب
cp -r deployments/template deployments/new_client

# 2. تعديل الإعدادات
nano deployments/new_client/.env.production

# 3. إضافة في clients.json
nano deployments/clients.json
```

---

## سير العمل الموصى به

### النشر اليومي
```bash
# 1. انشر للعميل
python deploy.py --client baraka

# 2. تحقق من الموقع
# افتح https://baraka.mwheba.co.uk
```

### النشر الأول لعميل جديد
```bash
# 1. إنشاء العميل
python deployments/create_client.py

# 2. اختبار الاتصال
python deploy.py --client new_client --mode test

# 3. رفع جميع الملفات
python deploy.py --client new_client --mode all

# 4. على السيرفر
ssh user@server
cd /path/to/deployment
source venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

---

## الأمان

- جميع ملفات `.env` في `deployments/` محمية من Git تلقائياً
- احتفظ بنسخة احتياطية من ملفات `.env` في مكان آمن
- استخدم كلمات مرور قوية ومختلفة لكل عميل
- استخدم SSH Keys بدلاً من كلمات المرور عند الإمكان
- غيّر `SECRET_KEY` لكل عميل

---

## استكشاف الأخطاء

**"العميل غير موجود"**
```bash
python deploy.py --list-clients
```

**"فشل الاتصال SSH"**
```bash
python deploy.py --client baraka --mode test
# راجع: SSH_HOST, SSH_PORT, SSH_USER, SSH_PASSWORD في .env.production
```

**"خطأ في المصادقة"**
- تحقق من `SSH_PASSWORD` أو `SSH_KEY_PATH`
- جرب يدوياً: `ssh user@host -p port`
