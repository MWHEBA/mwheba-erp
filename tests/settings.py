"""
إعدادات خاصة بالاختبارات - محسنة لـ pytest
"""
from corporate_erp.settings import *
import os

# قاعدة بيانات للاختبارات - استخدام نفس MySQL
# لكن مع اسم قاعدة بيانات مختلفة للاختبارات
if env("DB_ENGINE", default="sqlite") == "mysql":
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': env("DB_NAME", default="test_corporate_erp"),
            'USER': env("DB_USER"),
            'PASSWORD': env("DB_PASSWORD"),
            'HOST': env("DB_HOST"),
            'PORT': env("DB_PORT"),
            'ATOMIC_REQUESTS': True,
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            'TEST': {
                'NAME': 'test_corporate_erp',
                'CHARSET': 'utf8mb4',
                'COLLATION': 'utf8mb4_unicode_ci',
            }
        }
    }
else:
    # Fallback to SQLite for local testing
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': 'test_db.sqlite3',
            'ATOMIC_REQUESTS': True,
            'OPTIONS': {
                'timeout': 20,
            },
            'TEST': {
                'NAME': 'test_db.sqlite3',
            }
        }
    }

# إعدادات الاختبار
DEBUG = False
TESTING = True

# تسريع الاختبارات
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# تعطيل التخزين المؤقت
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# تعطيل الإيميل
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# إعدادات الأمان للاختبار
SECRET_KEY = 'test-secret-key-for-testing-only'
ALLOWED_HOSTS = ['*']

# تعطيل Celery
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# إعدادات إضافية
USE_TZ = True
TIME_ZONE = 'Africa/Cairo'  # استخدام قيمة ثابتة للاختبارات
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# تبسيط migrations للاختبارات
# MIGRATION_MODULES = {}  # تعطيل هذا لإنشاء الجداول

# إعدادات الملفات المؤقتة
MEDIA_ROOT = os.path.join(BASE_DIR, 'test_media')
STATIC_ROOT = os.path.join(BASE_DIR, 'test_static')

# تعطيل logging للاختبارات
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
    },
}
