import os
from pathlib import Path
import environ

# قراءة متغيرات البيئة
env = environ.Env()
env_file = os.path.join(Path(__file__).resolve().parent.parent, '.env')
environ.Env.read_env(env_file)

# استيراد pymysql فقط إذا كنا نستخدم MySQL
if env('DB_ENGINE', default='sqlite') == 'mysql':
    import pymysql
    pymysql.install_as_MySQLdb()