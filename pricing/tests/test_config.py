"""
إعدادات اختبارات نظام التسعير
Pricing System Test Configuration
"""
import os
import django
from django.conf import settings

# إعدادات pytest
PYTEST_CONFIG = {
    'testpaths': ['pricing/tests'],
    'python_files': ['test_*.py', '*_test.py'],
    'python_classes': ['Test*', '*Test', '*Tests'],
    'python_functions': ['test_*'],
    'addopts': [
        '--verbose',
        '--tb=short',
        '--strict-markers',
        '--disable-warnings',
        '--cov=pricing',
        '--cov-report=term-missing',
        '--cov-report=html'
    ],
    'markers': {
        'slow': 'اختبارات بطيئة التنفيذ',
        'integration': 'اختبارات التكامل',
        'unit': 'اختبارات الوحدة',
        'api': 'اختبارات الـ API',
        'view': 'اختبارات الواجهات',
        'service': 'اختبارات الخدمات',
        'model': 'اختبارات النماذج',
        'form': 'اختبارات النماذج',
        'javascript': 'اختبارات JavaScript',
        'selenium': 'اختبارات Selenium',
        'performance': 'اختبارات الأداء',
        'security': 'اختبارات الأمان'
    }
}

# إعدادات Django للاختبارات
TEST_SETTINGS = {
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    },
    'CACHES': {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    },
    'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
    'CELERY_TASK_ALWAYS_EAGER': True,
    'CELERY_TASK_EAGER_PROPAGATES': True,
    'STATICFILES_STORAGE': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    'SECRET_KEY': 'test-secret-key-for-testing-only',
    'DEBUG': True,
    'ALLOWED_HOSTS': ['*'],
    'USE_TZ': True,
    'TIME_ZONE': 'Africa/Cairo',
    'LANGUAGE_CODE': 'ar',
    'USE_I18N': True,
    'USE_L10N': True,
}

# تعطيل migrations للسرعة
MIGRATION_MODULES = {
    'pricing': None,
    'client': None,
    'supplier': None,
    'product': None,
    'financial': None,
    'purchase': None,
    'sale': None,
    'users': None,
    'core': None,
    'utils': None,
}

# فلترة التحذيرات
FILTERWARNINGS = [
    'ignore::UserWarning',
    'ignore::DeprecationWarning',
    'ignore::PendingDeprecationWarning',
    'ignore::django.utils.deprecation.RemovedInDjango40Warning',
    'ignore::django.utils.deprecation.RemovedInDjango41Warning',
]

def setup_test_environment():
    """إعداد بيئة الاختبار"""
    # إعداد Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
    
    if not settings.configured:
        django.setup()
    
    # تطبيق إعدادات الاختبار
    for key, value in TEST_SETTINGS.items():
        setattr(settings, key, value)
    
    # تعطيل migrations
    settings.MIGRATION_MODULES.update(MIGRATION_MODULES)
    
    return True

def get_test_database_config():
    """الحصول على إعدادات قاعدة بيانات الاختبار"""
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'OPTIONS': {
            'timeout': 20,
        },
        'TEST': {
            'NAME': ':memory:',
        }
    }

def get_coverage_config():
    """الحصول على إعدادات التغطية"""
    return {
        'source': ['pricing'],
        'omit': [
            '*/migrations/*',
            '*/tests/*',
            '*/venv/*',
            '*/env/*',
            'manage.py',
            '*/settings/*',
            '*/wsgi.py',
            '*/asgi.py',
        ],
        'exclude_lines': [
            'pragma: no cover',
            'def __repr__',
            'if self.debug:',
            'if settings.DEBUG',
            'raise AssertionError',
            'raise NotImplementedError',
            'if 0:',
            'if __name__ == .__main__.:',
            'class .*\bProtocol\):',
            '@(abc\.)?abstractmethod',
        ]
    }

# إعدادات Selenium
SELENIUM_CONFIG = {
    'implicit_wait': 10,
    'page_load_timeout': 30,
    'script_timeout': 30,
    'window_size': (1920, 1080),
    'headless': True,
    'chrome_options': [
        '--headless',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-images',
        '--disable-javascript',
    ],
    'firefox_options': [
        '--headless',
        '--disable-gpu',
        '--no-sandbox',
    ]
}

# إعدادات اختبارات الأداء
PERFORMANCE_CONFIG = {
    'max_response_time': 2.0,  # ثانية
    'max_db_queries': 10,
    'max_memory_usage': 100,  # MB
    'load_test_users': 10,
    'load_test_duration': 30,  # ثانية
}

# إعدادات اختبارات الأمان
SECURITY_CONFIG = {
    'test_sql_injection': True,
    'test_xss': True,
    'test_csrf': True,
    'test_authentication': True,
    'test_authorization': True,
    'test_data_validation': True,
}

# بيانات الاختبار الافتراضية
DEFAULT_TEST_DATA = {
    'user': {
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'testpass123',
        'first_name': 'Test',
        'last_name': 'User'
    },
    'client': {
        'name': 'عميل تجريبي',
        'email': 'client@test.com',
        'phone': '01234567890',
        'address': 'عنوان تجريبي'
    },
    'supplier': {
        'name': 'مورد تجريبي',
        'email': 'supplier@test.com',
        'phone': '01234567890',
        'address': 'عنوان المورد'
    },
    'paper_types': [
        {'name': 'ورق أبيض', 'weight': 80, 'price_per_kg': 15.00},
        {'name': 'ورق مقوى', 'weight': 300, 'price_per_kg': 25.00},
        {'name': 'ورق ملون', 'weight': 80, 'price_per_kg': 18.00}
    ],
    'paper_sizes': [
        {'name': 'A4', 'width': 21.0, 'height': 29.7},
        {'name': 'A3', 'width': 29.7, 'height': 42.0},
        {'name': 'A5', 'width': 14.8, 'height': 21.0}
    ],
    'plate_sizes': [
        {'name': '70x100', 'width': 70.0, 'height': 100.0, 'price': 200.00},
        {'name': '50x70', 'width': 50.0, 'height': 70.0, 'price': 150.00}
    ]
}

# مسارات الملفات
TEST_PATHS = {
    'test_files': 'pricing/tests/',
    'coverage_html': 'htmlcov/',
    'coverage_xml': 'coverage.xml',
    'test_reports': 'test_reports/',
    'screenshots': 'test_screenshots/',
    'logs': 'test_logs/'
}

def create_test_directories():
    """إنشاء مجلدات الاختبار"""
    import os
    from pathlib import Path
    
    base_dir = Path(__file__).parent.parent.parent
    
    for path_name, path_value in TEST_PATHS.items():
        full_path = base_dir / path_value
        full_path.mkdir(parents=True, exist_ok=True)
    
    return True

def get_test_runner_config():
    """الحصول على إعدادات مشغل الاختبارات"""
    return {
        'TEST_RUNNER': 'django.test.runner.DiscoverRunner',
        'TEST_NON_SERIALIZED_APPS': ['pricing'],
        'TEST_SERIALIZE': False,
        'TEST_CHARSET': 'utf8',
        'TEST_COLLATION': None,
    }
