# إعداد نظام الجدولة التلقائية للإشعارات

## الطريقة 1: استخدام django-crontab (موصى بها للبيئات البسيطة)

### 1. تثبيت django-crontab:
```bash
pip install django-crontab
```

### 2. إضافة للـ INSTALLED_APPS في settings.py:
```python
INSTALLED_APPS = [
    # ... التطبيقات الأخرى
    'django_crontab',
]
```

### 3. إضافة إعدادات Cron في settings.py:
```python
# إعدادات Cron Jobs
CRONJOBS = [
    # فحص المخزون المنخفض كل ساعة
    ('0 * * * *', 'core.cron.check_low_stock_alerts', '>> /tmp/cron_stock_alerts.log'),
    
    # فحص الفواتير المستحقة يومياً في الساعة 9 صباحاً
    ('0 9 * * *', 'core.cron.check_due_invoices_alerts', '>> /tmp/cron_invoice_alerts.log'),
    
    # فحص جميع التنبيهات كل 6 ساعات
    ('0 */6 * * *', 'core.cron.check_all_alerts', '>> /tmp/cron_all_alerts.log'),
    
    # تنظيف الإشعارات القديمة أسبوعياً (كل أحد في الساعة 2 صباحاً)
    ('0 2 * * 0', 'core.cron.cleanup_old_notifications', '>> /tmp/cron_cleanup.log'),
]

# تفعيل logging للـ cron
CRONTAB_COMMAND_SUFFIX = '2>&1'
```

### 4. تفعيل Cron Jobs:
```bash
# إضافة الوظائف لـ crontab
python manage.py crontab add

# عرض الوظائف المجدولة
python manage.py crontab show

# إزالة الوظائف
python manage.py crontab remove
```

---

## الطريقة 2: استخدام Windows Task Scheduler (لبيئة Windows)

### 1. إنشاء ملف batch للتنفيذ:
```batch
@echo off
cd /d C:\Users\MohYousif\Desktop\mwheba_erp
python manage.py check_alerts --type=all
```

### 2. جدولة المهمة في Windows:
1. افتح Task Scheduler
2. Create Basic Task
3. اختر التوقيت (كل ساعة مثلاً)
4. اختر "Start a program"
5. حدد ملف الـ batch

---

## الطريقة 3: استخدام Celery Beat (للأنظمة الكبيرة)

### 1. تثبيت Celery:
```bash
pip install celery redis
```

### 2. إنشاء ملف celery.py في مجلد المشروع:
```python
from celery import Celery
from celery.schedules import crontab
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')

app = Celery('mwheba_erp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# جدولة المهام
app.conf.beat_schedule = {
    'check-low-stock-every-hour': {
        'task': 'core.tasks.check_low_stock_alerts',
        'schedule': crontab(minute=0),  # كل ساعة
    },
    'check-due-invoices-daily': {
        'task': 'core.tasks.check_due_invoices_alerts',
        'schedule': crontab(hour=9, minute=0),  # يومياً 9 صباحاً
    },
    'cleanup-old-notifications-weekly': {
        'task': 'core.tasks.cleanup_old_notifications',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),  # أحد 2 صباحاً
    },
}
```

### 3. تشغيل Celery:
```bash
# تشغيل Worker
celery -A mwheba_erp worker -l info

# تشغيل Beat (في terminal منفصل)
celery -A mwheba_erp beat -l info
```

---

## التوصيات:

### للبيئات الصغيرة والمتوسطة:
- استخدم **django-crontab** - بسيط وفعال

### للبيئات الكبيرة والإنتاجية:
- استخدم **Celery Beat** - أكثر مرونة وقوة

### لبيئة Windows التطويرية:
- استخدم **Windows Task Scheduler** - سهل الإعداد

---

## اختبار النظام يدوياً:

```bash
# فحص تنبيهات المخزون
python manage.py check_alerts --type=stock --verbose

# فحص تنبيهات الفواتير
python manage.py check_alerts --type=invoices --verbose

# فحص جميع التنبيهات
python manage.py check_alerts --type=all --verbose
```
