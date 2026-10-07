import os
from pathlib import Path
import environ

# قراءة متغيرات البيئة
env = environ.Env()
env_file = os.path.join(Path(__file__).resolve().parent.parent, ".env")
environ.Env.read_env(env_file)

# استيراد pymysql فقط إذا كنا نستخدم MySQL
if env("DB_ENGINE", default="sqlite") == "mysql":
    import pymysql

    pymysql.version_info = (2, 2, 7, "final", 0)
    pymysql.install_as_MySQLdb()

    try:
        from django.db.backends.mysql.base import DatabaseWrapper
        from django.db.backends.mysql.features import DatabaseFeatures
        DatabaseWrapper.check_database_version_supported = lambda self: None
        DatabaseFeatures.can_return_columns_from_insert = property(lambda self: False)
        DatabaseFeatures.can_return_rows_from_bulk_insert = property(lambda self: False)
    except Exception:
        pass

# ✅ PRODUCTION FIX: Import Celery only if available
# This prevents ModuleNotFoundError on cPanel where Celery might not be installed
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery not available - skip initialization
    # Background tasks will not work but the application will start
    pass
