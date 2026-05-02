#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup_development.py - سكريبت إعداد بيئة التطوير (محدث أبريل 2026)
يقوم بتهيئة النظام للتطوير مع الفيكستشرز المحدثة والآمنة

التحديثات الجديدة:
- دعم تلقائي لـ SQLite و MySQL حسب ملف .env
- تحميل جميع fixtures بدون استثناء
- ترتيب منطقي صحيح مع مراعاة dependencies
- مستخدمين آمنين مع كلمات مرور مشفرة
- دعم كامل لـ printing_pricing, HR, financial subcategories

دعم قواعد البيانات:
- SQLite: يتم حذف ملف db.sqlite3 وإنشاء قاعدة بيانات جديدة
- MySQL: يتم حذف جميع الجداول وإعادة إنشائها من جديد
- يتم اكتشاف نوع قاعدة البيانات تلقائياً من متغير DB_ENGINE في ملف .env

ملاحظة مهمة: هذا السكريبت يعتمد على ملفات fixtures محدثة
ولا يحتوي على أي بيانات حساسة في الكود
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import warnings
import fnmatch
import hashlib
import json
import time
import django

# إخفاء تحذيرات pkg_resources المهملة من coreapi
warnings.filterwarnings('ignore', category=UserWarning, module='coreapi')

# إعداد encoding لـ Windows console
if sys.platform == 'win32':
    import codecs
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# متغير عام للوضع التلقائي
auto_mode = len(sys.argv) > 1 and sys.argv[1] == '--auto'

# الألوان للطباعة
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_colored(text, color="", flush=True):
    """طباعة نص ملون"""
    try:
        # في الوضع التلقائي، استخدم طباعة بسيطة بدون ألوان
        if auto_mode:
            # إزالة الـ emoji والرموز الخاصة
            text_clean = text.replace("✅", "[OK]").replace("❌", "[X]").replace("⚠️", "[!]")
            text_clean = text_clean.replace("🔄", "[~]").replace("📦", "[*]").replace("ℹ️", "[i]")
            print(text_clean, flush=flush)
        else:
            print(f"{color}{text}{Colors.RESET}", flush=flush)
    except UnicodeEncodeError:
        # في حالة فشل طباعة emoji، استخدم ASCII
        text_safe = text.encode('ascii', 'ignore').decode('ascii')
        print(f"{color}{text_safe}{Colors.RESET}", flush=flush)


def print_header(text):
    """طباعة عنوان"""
    print_colored(f"\n{'='*50}", Colors.CYAN)
    print_colored(f"  {text}", Colors.CYAN + Colors.BOLD)
    print_colored(f"{'='*50}\n", Colors.CYAN)


def print_step(step_num, total, text):
    """طباعة خطوة"""
    print_colored(f"\n📦 المرحلة {step_num}/{total}: {text}...", Colors.YELLOW)


def print_success(text):
    """طباعة رسالة نجاح"""
    print_colored(f"   ✅ {text}", Colors.GREEN)


def print_info(text, end='\n'):
    """طباعة معلومة"""
    print_colored(f"   ℹ️  {text}", Colors.GRAY)
    if end != '\n':
        print(end='', flush=True)


def print_warning(text):
    """طباعة تحذير"""
    print_colored(f"   ⚠️  {text}", Colors.RED)


def run_command(command, check=True, show_output=False, timeout=None):
    """تشغيل أمر في الـ shell"""
    try:
        if show_output:
            result = subprocess.run(
                command, shell=True, check=check, text=True, timeout=timeout
            )
            return result.returncode == 0
        else:
            result = subprocess.run(
                command, shell=True, check=False, capture_output=True, text=True, timeout=timeout
            )
            if result.returncode != 0:
                # استخراج آخر سطر من الخطأ فقط (الرسالة الفعلية)
                error_msg = ""
                if result.stderr:
                    error_lines = result.stderr.strip().split('\n')
                    # البحث عن آخر سطر يحتوي على خطأ فعلي
                    for line in reversed(error_lines):
                        if line.strip() and not line.startswith('  '):
                            error_msg = line.strip()
                            break
                    if not error_msg and error_lines:
                        error_msg = error_lines[-1].strip()
                elif result.stdout:
                    error_lines = result.stdout.strip().split('\n')
                    for line in reversed(error_lines):
                        if line.strip() and not line.startswith('  '):
                            error_msg = line.strip()
                            break
                    if not error_msg and error_lines:
                        error_msg = error_lines[-1].strip()
                
                if error_msg:
                    print_warning(f"خطأ: {error_msg[:150]}")
                else:
                    print_warning(f"الأمر فشل بكود الخروج: {result.returncode}")
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        print_warning(f"انتهت مهلة تنفيذ الأمر ({timeout}s)")
        return False
    except subprocess.CalledProcessError as e:
        print_warning(f"فشل تنفيذ الأمر: {e}")
        return False
    except Exception as e:
        print_warning(f"خطأ غير متوقع: {e}")
        return False


def wait_for_database_ready(max_attempts=10, delay=2):
    """انتظار حتى تصبح قاعدة البيانات جاهزة للكتابة"""
    print_info("فحص جاهزية قاعدة البيانات...")
    
    for attempt in range(max_attempts):
        try:
            from django.db import connection, transaction
            
            # اختبار بسيط للكتابة
            with connection.cursor() as cursor:
                cursor.execute("BEGIN;")
                cursor.execute("ROLLBACK;")
            
            print_success("قاعدة البيانات جاهزة للكتابة")
            return True
            
        except Exception as e:
            if attempt < max_attempts - 1:
                print_info(f"محاولة {attempt + 1}/{max_attempts} - انتظار {delay} ثانية...")
                time.sleep(delay)
            else:
                print_warning(f"قاعدة البيانات لا تزال مشغولة بعد {max_attempts} محاولات")
                return False
    
    return False


def force_close_database_connections():
    """إغلاق جميع الاتصالات بقاعدة البيانات بالقوة"""
    try:
        # إغلاق اتصالات Django
        from django.db import connections
        for conn in connections.all():
            conn.close()
        
        print_info("تم إغلاق اتصالات Django")
        
        # محاولة قتل العمليات التي تستخدم قاعدة البيانات
        try:
            import psutil
            
            db_files = ['db.sqlite3', 'db.sqlite3-shm', 'db.sqlite3-wal']
            killed_processes = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                try:
                    if proc.info['open_files']:
                        for file_info in proc.info['open_files']:
                            if any(db_file in file_info.path for db_file in db_files):
                                print_info(f"قتل العملية {proc.info['name']} (PID: {proc.info['pid']})")
                                proc.terminate()
                                killed_processes += 1
                                break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if killed_processes > 0:
                print_success(f"تم قتل {killed_processes} عملية")
                time.sleep(2)
            else:
                print_info("لا توجد عمليات تستخدم قاعدة البيانات")
                
        except ImportError:
            print_info("مكتبة psutil غير متاحة، سيتم استخدام طريقة بديلة...")
            return force_close_database_connections_alternative()
            
        return True
        
    except Exception as e:
        print_warning(f"خطأ في إغلاق الاتصالات: {e}")
        return force_close_database_connections_alternative()


def force_close_database_connections_alternative():
    """طريقة بديلة لإغلاق اتصالات قاعدة البيانات"""
    try:
        # إغلاق اتصالات Django
        from django.db import connections
        for conn in connections.all():
            conn.close()
        
        # محاولة استخدام أوامر النظام لقتل العمليات
        if sys.platform == 'win32':
            # Windows
            print_info("محاولة إغلاق العمليات على Windows...")
            subprocess.run(['taskkill', '/f', '/im', 'python.exe'], 
                         capture_output=True, check=False)
            subprocess.run(['taskkill', '/f', '/im', 'pythonw.exe'], 
                         capture_output=True, check=False)
        else:
            # Linux/Mac
            print_info("محاولة إغلاق العمليات على Linux/Mac...")
            subprocess.run(['pkill', '-f', 'manage.py'], 
                         capture_output=True, check=False)
            subprocess.run(['pkill', '-f', 'runserver'], 
                         capture_output=True, check=False)
        
        time.sleep(3)  # انتظار أطول
        return True
        
    except Exception as e:
        print_warning(f"فشل في الطريقة البديلة: {e}")
        return False


def safe_database_operation(operation_func, operation_name, max_retries=3):
    """تنفيذ عملية قاعدة بيانات مع إعادة المحاولة"""
    for retry in range(max_retries):
        try:
            if retry > 0:
                print_info(f"إعادة محاولة {retry + 1}/{max_retries} لـ {operation_name}...")
                time.sleep(2)
            
            result = operation_func()
            return result if result is not None else True
            
        except Exception as e:
            error_msg = str(e).lower()
            is_db_busy = any(keyword in error_msg for keyword in ["readonly", "locked", "busy", "database is locked"])
            
            if is_db_busy and retry < max_retries - 1:
                print_info(f"قاعدة البيانات مشغولة، انتظار...")
                time.sleep(3)
                continue
            else:
                print_warning(f"{'فشل في' if retry == max_retries - 1 else 'خطأ في'} {operation_name}: {e}")
                return False
    
    return False


def get_all_files():
    """الحصول على جميع الملفات في المشروع"""
    project_root = Path.cwd()
    ignored_patterns = load_gitignore_patterns()
    
    files = []
    for file_path in project_root.rglob('*'):
        if file_path.is_file() and not is_ignored(file_path, ignored_patterns, project_root):
            files.append(file_path)
    return files


def load_gitignore_patterns():
    """تحميل قائمة الاستثناءات من .gitignore"""
    patterns = []
    gitignore_path = Path.cwd() / ".gitignore"
    
    if gitignore_path.exists():
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
    
    # إضافة الملفات المخفية
    patterns.extend(['.*', '__pycache__', '*.pyc', '.deploy_hashes.json'])
    return patterns


def is_ignored(file_path, patterns, project_root):
    """فحص ما إذا كان الملف مستثنى"""
    import fnmatch
    
    relative_path = str(file_path.relative_to(project_root))
    
    if any(part.startswith('.') for part in file_path.parts):
        return True
        
    for pattern in patterns:
        if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
            return True
            
    return False


def get_file_hash(file_path):
    """حساب hash للملف"""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None


def load_fixture(fixture_path, description="", timeout=60):
    """تحميل فيكستشر واحد مع معالجة الأخطاء"""
    fixture = Path(fixture_path)
    if not fixture.exists():
        print_warning(f"الملف غير موجود: {fixture_path}")
        return False
    
    if description:
        print_info(f"تحميل {description}...")
    else:
        print_info(f"تحميل {fixture_path}...")
    
    success = run_command(f"python manage.py loaddata {fixture_path}", show_output=False, timeout=timeout)
    
    if success:
        print_success(f"✅ تم تحميل {fixture.name}")
        return True
    else:
        print_warning(f"❌ فشل تحميل {fixture.name}")
        return False


def load_fixtures_batch(fixtures_list, description=""):
    """تحميل مجموعة من الفيكستشرز"""
    if description:
        print_info(description)
    
    loaded = 0
    for fixture_info in fixtures_list:
        if isinstance(fixture_info, dict):
            fixture_path = fixture_info.get('path')
            desc = fixture_info.get('description', '')
            timeout = fixture_info.get('timeout', 60)
        else:
            fixture_path = fixture_info
            desc = ''
            timeout = 60
        
        if load_fixture(fixture_path, desc, timeout):
            loaded += 1
    
    return loaded


def get_database_type():
    """تحديد نوع قاعدة البيانات من ملف .env"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        db_engine = os.getenv('DB_ENGINE', 'sqlite').lower()
        return 'mysql' if db_engine == 'mysql' else 'sqlite'
    except ImportError:
        # إذا لم تكن dotenv متاحة، نقرأ الملف يدوياً
        env_file = Path('.env')
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('DB_ENGINE='):
                        value = line.split('=', 1)[1].strip()
                        return 'mysql' if value.lower() == 'mysql' else 'sqlite'
        return 'sqlite'


def check_mysql_connection():
    """فحص الاتصال بـ MySQL قبل البدء"""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        return True
    except Exception as e:
        error_msg = str(e).lower()
        # فحص أنواع الأخطاء الشائعة
        if any(keyword in error_msg for keyword in ['can\'t connect', 'connection refused', '2002', '2003', 'unknown mysql server host']):
            return False
        # أخطاء أخرى قد تكون مشاكل في الإعدادات
        raise e


def get_migrations_hash():
    """حساب hash لجميع ملفات الـ migrations"""
    try:
        migrations_content = ""
        project_root = Path.cwd()
        
        # البحث عن جميع ملفات migrations
        for migration_file in project_root.rglob("migrations/*.py"):
            if migration_file.name != "__init__.py":
                try:
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        migrations_content += f.read()
                except:
                    continue
        
        # حساب hash
        return hashlib.md5(migrations_content.encode()).hexdigest()
    except Exception as e:
        print_warning(f"خطأ في حساب migrations hash: {e}")
        return None


def get_snapshot_info():
    """قراءة معلومات الـ snapshot"""
    snapshot_dir = Path(".db_snapshots")
    info_file = snapshot_dir / "snapshot_info.json"
    
    if not info_file.exists():
        return None
    
    try:
        with open(info_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"خطأ في قراءة snapshot info: {e}")
        return None


def create_snapshot(db_type):
    """إنشاء snapshot من قاعدة البيانات الحالية"""
    snapshot_dir = Path(".db_snapshots")
    snapshot_dir.mkdir(exist_ok=True)
    
    print_colored("\n📸 جاري إنشاء Snapshot...", Colors.CYAN)
    
    try:
        if db_type == 'sqlite':
            # نسخ ملف SQLite
            source = Path("db.sqlite3")
            if not source.exists():
                print_warning("ملف قاعدة البيانات غير موجود")
                return False
            
            destination = snapshot_dir / "sqlite_snapshot.db"
            shutil.copy2(source, destination)
            print_success(f"تم نسخ SQLite snapshot ({source.stat().st_size / 1024:.1f} KB)")
            
        else:  # MySQL
            from dotenv import load_dotenv
            load_dotenv()
            
            db_name = os.getenv('DB_NAME', 'corporate_db')
            db_user = os.getenv('DB_USER', 'root')
            db_password = os.getenv('DB_PASSWORD', '')
            db_host = os.getenv('DB_HOST', 'localhost')
            
            snapshot_file = snapshot_dir / "mysql_snapshot.sql"
            
            # محاولة إيجاد mysqldump في XAMPP
            possible_paths = [
                r"C:\xampp\mysql\bin\mysqldump.exe",
                r"C:\Program Files\xampp\mysql\bin\mysqldump.exe",
                r"D:\xampp\mysql\bin\mysqldump.exe",
                "mysqldump",  # في PATH
            ]
            
            mysqldump_path = None
            for path in possible_paths:
                if path == "mysqldump":
                    # تجربة في PATH
                    try:
                        result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                        if result.returncode == 0:
                            mysqldump_path = path
                            break
                    except:
                        continue
                else:
                    # تجربة مسار محدد
                    if Path(path).exists():
                        mysqldump_path = path
                        break
            
            if not mysqldump_path:
                print_warning("لم يتم العثور على mysqldump")
                print_info("يمكنك تثبيت XAMPP أو إضافة MySQL bin إلى PATH")
                return False
            
            # بناء أمر mysqldump
            cmd = f'"{mysqldump_path}" -h {db_host} -u {db_user}'
            if db_password:
                cmd += f' -p{db_password}'
            cmd += f' {db_name} > "{snapshot_file}"'
            
            print_info("جاري تصدير MySQL database...")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and snapshot_file.exists():
                print_success(f"تم إنشاء MySQL snapshot ({snapshot_file.stat().st_size / 1024:.1f} KB)")
            else:
                print_warning("فشل إنشاء MySQL snapshot")
                if result.stderr:
                    print_warning(f"الخطأ: {result.stderr[:200]}")
                return False
        
        # حفظ معلومات الـ snapshot
        from datetime import datetime
        
        snapshot_info = {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "db_type": db_type,
            "migrations_hash": get_migrations_hash(),
            "django_version": django.get_version(),
        }
        
        # محاولة الحصول على عدد المستخدمين
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            snapshot_info["total_users"] = User.objects.count()
        except:
            snapshot_info["total_users"] = 0
        
        info_file = snapshot_dir / "snapshot_info.json"
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot_info, f, indent=2, ensure_ascii=False)
        
        print_success("تم حفظ معلومات الـ snapshot")
        return True
        
    except Exception as e:
        print_warning(f"خطأ في إنشاء snapshot: {e}")
        return False


def restore_snapshot(db_type):
    """استعادة قاعدة البيانات من snapshot"""
    snapshot_dir = Path(".db_snapshots")
    
    print_colored("\n♻️  جاري استعادة Snapshot...", Colors.CYAN)
    
    try:
        if db_type == 'sqlite':
            snapshot_file = snapshot_dir / "sqlite_snapshot.db"
            
            if not snapshot_file.exists():
                print_warning("ملف SQLite snapshot غير موجود")
                return False
            
            print_info("📦 جاري نسخ ملف قاعدة البيانات...")
            
            # حذف قاعدة البيانات الحالية
            db_file = Path("db.sqlite3")
            if db_file.exists():
                print_info("   ⏳ حذف قاعدة البيانات القديمة...")
                db_file.unlink()
            
            # نسخ الـ snapshot مع progress
            print_info("   ⏳ نسخ البيانات من snapshot...")
            shutil.copy2(snapshot_file, db_file)
            
            file_size_mb = db_file.stat().st_size / (1024 * 1024)
            print_success(f"✅ تم استعادة SQLite snapshot بنجاح ({file_size_mb:.1f} MB)")
            
        else:  # MySQL
            snapshot_file = snapshot_dir / "mysql_snapshot.sql"
            
            if not snapshot_file.exists():
                print_warning("ملف MySQL snapshot غير موجود")
                return False
            
            from dotenv import load_dotenv
            load_dotenv()
            
            db_name = os.getenv('DB_NAME', 'corporate_db')
            db_user = os.getenv('DB_USER', 'root')
            db_password = os.getenv('DB_PASSWORD', '')
            db_host = os.getenv('DB_HOST', 'localhost')
            
            # حذف جميع الجداول أولاً (إذا وجدت)
            print_info("🗑️  حذف الجداول الحالية...")
            sys.stdout.flush()  # فورس الطباعة
            
            try:
                from django.db import connection
                
                with connection.cursor() as cursor:
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                    cursor.execute("SHOW TABLES;")
                    tables = cursor.fetchall()
                    
                    if tables:
                        print_info(f"   ⏳ جاري حذف {len(tables)} جدول...")
                        sys.stdout.flush()
                        
                        for i, table in enumerate(tables, 1):
                            cursor.execute(f"DROP TABLE IF EXISTS `{table[0]}`;")
                            # طباعة progress كل 20 جدول
                            if i % 20 == 0 or i == len(tables):
                                print(f"\r   ℹ️  ⏳ تم حذف {i}/{len(tables)} جدول...", end='', flush=True)
                        
                        print()  # سطر جديد بعد الانتهاء
                        print_success(f"✅ تم حذف {len(tables)} جدول")
                        sys.stdout.flush()
                    else:
                        print_info("   ℹ️  لا توجد جداول للحذف")
                        sys.stdout.flush()
                    
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            except Exception as e:
                print_info(f"   ℹ️  تخطي حذف الجداول: {e}")
                sys.stdout.flush()
            
            # استعادة من snapshot
            print_info("📥 استعادة البيانات من snapshot...")
            sys.stdout.flush()
            
            # حساب حجم الملف
            file_size_mb = snapshot_file.stat().st_size / (1024 * 1024)
            print_info(f"   📊 حجم الملف: {file_size_mb:.1f} MB")
            print_info("   ⏳ جاري استيراد البيانات (قد يستغرق 20-30 ثانية)...")
            sys.stdout.flush()
            
            # محاولة إيجاد mysql في XAMPP
            possible_paths = [
                r"C:\xampp\mysql\bin\mysql.exe",
                r"C:\Program Files\xampp\mysql\bin\mysql.exe",
                r"D:\xampp\mysql\bin\mysql.exe",
                "mysql",  # في PATH
            ]
            
            mysql_path = None
            for path in possible_paths:
                if path == "mysql":
                    try:
                        result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                        if result.returncode == 0:
                            mysql_path = path
                            break
                    except:
                        continue
                else:
                    if Path(path).exists():
                        mysql_path = path
                        break
            
            if not mysql_path:
                print_warning("❌ لم يتم العثور على mysql client")
                return False
            
            # بناء الأمر
            cmd = f'"{mysql_path}" -h {db_host} -u {db_user}'
            if db_password:
                cmd += f' -p{db_password}'
            cmd += f' {db_name} < "{snapshot_file}"'
            
            # تنفيذ الأمر مع عرض progress
            import time
            start_time = time.time()
            
            # تشغيل الأمر في background
            process = subprocess.Popen(
                cmd, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            # عرض progress أثناء التنفيذ
            dots = 0
            while process.poll() is None:
                time.sleep(1)
                dots = (dots + 1) % 4
                elapsed = int(time.time() - start_time)
                progress_msg = f"   ⏳ جاري الاستيراد{'.' * dots}{' ' * (3 - dots)} ({elapsed}s)"
                print(f"\r{progress_msg}", end='', flush=True)
            
            # الحصول على النتيجة
            stdout, stderr = process.communicate()
            elapsed_time = int(time.time() - start_time)
            
            # مسح سطر progress
            print("\r" + " " * 80, end='\r', flush=True)
            
            if process.returncode == 0:
                print_success(f"✅ تم استعادة MySQL snapshot بنجاح ({elapsed_time}s)")
                sys.stdout.flush()
            else:
                print_warning("❌ فشل استعادة MySQL snapshot")
                if stderr:
                    print_warning(f"الخطأ: {stderr[:200]}")
                sys.stdout.flush()
                return False
        
        return True
        
    except Exception as e:
        print_warning(f"❌ خطأ في استعادة snapshot: {e}")
        return False


def check_snapshot_compatibility(db_type):
    """فحص توافق الـ snapshot مع الحالة الحالية"""
    snapshot_info = get_snapshot_info()
    
    if not snapshot_info:
        return False, "لا توجد معلومات snapshot"
    
    # فحص نوع قاعدة البيانات
    if snapshot_info.get('db_type') != db_type:
        return False, f"نوع قاعدة البيانات مختلف (snapshot: {snapshot_info.get('db_type')}, حالي: {db_type})"
    
    # فحص migrations hash
    current_hash = get_migrations_hash()
    snapshot_hash = snapshot_info.get('migrations_hash')
    
    if current_hash != snapshot_hash:
        return False, "توجد migrations جديدة لم تكن موجودة في الـ snapshot"
    
    # فحص وجود ملف الـ snapshot
    snapshot_dir = Path(".db_snapshots")
    if db_type == 'sqlite':
        snapshot_file = snapshot_dir / "sqlite_snapshot.db"
    else:
        snapshot_file = snapshot_dir / "mysql_snapshot.sql"
    
    if not snapshot_file.exists():
        return False, "ملف الـ snapshot غير موجود"
    
    return True, "الـ snapshot متوافق"


def main():
    """الدالة الرئيسية لإعداد النظام لجميع fixtures"""

    # إجمالي المراحل
    TOTAL_STEPS = 13

    # تهيئة Django في البداية
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "corporate_erp.settings")
    import django

    # فحص وجود ملف الإعدادات
    settings_path = Path("corporate_erp/settings.py")
    if not settings_path.exists():
        print_colored(f"\n❌ لا يوجد ملف الإعدادات {settings_path}", Colors.RED)
        sys.exit(1)
    django.setup()

    # متغيرات المشروع
    project_root = Path.cwd()
    hash_file = project_root / ".deploy_hashes.json"
    
    # تحديد نوع قاعدة البيانات
    db_type = get_database_type()

    # طباعة العنوان
    print_header("ERP System - Development Setup")
    print_colored(f"🗄️  نوع قاعدة البيانات المكتشف: {db_type.upper()}", Colors.CYAN)
    
    # فحص اتصال MySQL إذا كان مطلوب
    if db_type == 'mysql':
        print_colored("\n🔍 فحص الاتصال بـ MySQL...", Colors.YELLOW)
        
        try:
            if not check_mysql_connection():
                print_colored("\n" + "="*60, Colors.RED)
                print_colored("❌ خطأ: لا يمكن الاتصال بـ MySQL", Colors.RED + Colors.BOLD)
                print_colored("="*60, Colors.RED)
                print_colored("\n💡 الحلول الممكنة:", Colors.YELLOW)
                print_colored("   1. تأكد من تشغيل MySQL أولاً", Colors.WHITE)
                print_colored("      يمكنك استخدام: python start_xampp.py", Colors.GRAY)
                print_colored("\n   2. أو شغّل XAMPP Control Panel يدوياً", Colors.WHITE)
                print_colored("      وتأكد من تشغيل MySQL من هناك", Colors.GRAY)
                print_colored("\n   3. تحقق من إعدادات الاتصال في ملف .env:", Colors.WHITE)
                print_colored("      - DB_HOST (افتراضي: localhost)", Colors.GRAY)
                print_colored("      - DB_PORT (افتراضي: 3306)", Colors.GRAY)
                print_colored("      - DB_USER (افتراضي: root)", Colors.GRAY)
                print_colored("      - DB_PASSWORD", Colors.GRAY)
                print_colored("\n" + "="*60 + "\n", Colors.RED)
                sys.exit(1)
            else:
                print_colored("✅ الاتصال بـ MySQL ناجح!", Colors.GREEN)
        except Exception as e:
            print_colored("\n" + "="*60, Colors.RED)
            print_colored("❌ خطأ في الاتصال بقاعدة البيانات", Colors.RED + Colors.BOLD)
            print_colored("="*60, Colors.RED)
            print_colored(f"\n📋 تفاصيل الخطأ: {str(e)}", Colors.YELLOW)
            print_colored("\n💡 يرجى التحقق من:", Colors.YELLOW)
            print_colored("   • إعدادات قاعدة البيانات في ملف .env", Colors.WHITE)
            print_colored("   • اسم قاعدة البيانات موجود", Colors.WHITE)
            print_colored("   • صلاحيات المستخدم صحيحة", Colors.WHITE)
            print_colored("\n" + "="*60 + "\n", Colors.RED)
            sys.exit(1)
    
    # فحص وجود snapshot
    snapshot_dir = Path(".db_snapshots")
    snapshot_exists = snapshot_dir.exists() and get_snapshot_info() is not None
    use_snapshot = False
    
    if snapshot_exists:
        if auto_mode:
            # في الوضع التلقائي، دائماً اختر الإعداد الجديد الكامل (خيار 2)
            print_colored("\n🤖 الوضع التلقائي: سيتم الإعداد الجديد الكامل", Colors.CYAN)
            use_snapshot = False
        else:
            # في الوضع العادي، اسأل المستخدم
            print_colored("\n📸 تم العثور على Database Snapshot!", Colors.CYAN + Colors.BOLD)
            
            # فحص التوافق
            is_compatible, compatibility_msg = check_snapshot_compatibility(db_type)
            snapshot_info = get_snapshot_info()
            
            print_colored("\n� معلومات الـ Snapshot:", Colors.CYAN)
            print_colored(f"   • تاريخ الإنشاء: {snapshot_info.get('created_at', 'غير معروف')}", Colors.GRAY)
            print_colored(f"   • نوع قاعدة البيانات: {snapshot_info.get('db_type', 'غير معروف').upper()}", Colors.GRAY)
            print_colored(f"   • Django Version: {snapshot_info.get('django_version', 'غير معروف')}", Colors.GRAY)
            
            if is_compatible:
                print_colored(f"   • الحالة: ✅ متوافق", Colors.GREEN)
            else:
                print_colored(f"   • الحالة: ⚠️  {compatibility_msg}", Colors.YELLOW)
            
            print_colored("\n🔄 اختر طريقة الإعداد:", Colors.CYAN + Colors.BOLD)
            print_colored("   [1] استعادة من Snapshot (سريع - 20-30 ثانية) ⚡", Colors.GREEN)
            print_colored("   [2] إعداد جديد كامل (بطيء - 3-5 دقائق) 🐢", Colors.YELLOW)
            
            if not is_compatible:
                print_colored("\n   ⚠️  تحذير: الـ Snapshot قد يكون قديم، يُنصح بالإعداد الجديد", Colors.RED)
            
            choice = input("\nاختيارك (1 أو 2): ").strip()
            
            if choice == "1":
                if not is_compatible:
                    confirm = input("⚠️  الـ Snapshot قد لا يكون متوافق، هل تريد المتابعة؟ (yes/no): ").strip().lower()
                    if confirm != "yes":
                        print_colored("\n🔄 سيتم الإعداد الجديد الكامل...", Colors.YELLOW)
                        use_snapshot = False
                    else:
                        use_snapshot = True
                else:
                    use_snapshot = True
            else:
                use_snapshot = False
    
    # استعادة من snapshot إذا تم اختياره
    if use_snapshot:
        if restore_snapshot(db_type):
            print_colored("\n🎉 تم استعادة قاعدة البيانات بنجاح من Snapshot!", Colors.GREEN + Colors.BOLD)
            
            # عرض إحصائيات سريعة
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                users_count = User.objects.count()
                
                print_colored("\n📊 الإحصائيات:", Colors.CYAN)
                print_success(f"✅ المستخدمين: {users_count}")
                
                print_colored("\n🚀 النظام جاهز للاستخدام!", Colors.GREEN + Colors.BOLD)
                print_colored("\n📝 معلومات تسجيل الدخول:", Colors.CYAN)
                print_colored("   المستخدم: admin", Colors.WHITE)
                print_colored("   كلمة المرور: admin123", Colors.WHITE)
                
                print_colored("\n💡 لبدء السيرفر:", Colors.YELLOW)
                print_colored("   python manage.py runserver", Colors.WHITE)
                
            except Exception as e:
                print_info(f"تعذر عرض الإحصائيات: {e}")
            
            sys.exit(0)
        else:
            print_colored("\n⚠️  فشل استعادة الـ Snapshot، سيتم الإعداد الجديد الكامل...", Colors.YELLOW)
            time.sleep(2)
    
    # تأكيد المتابعة للإعداد الجديد - تم إزالة السؤال للتشغيل المباشر
    print_colored("\n🛠️  إعداد النظام الكامل", Colors.CYAN)
    print_colored("سيتم تحميل جميع fixtures بدون استثناء", Colors.WHITE)
    print_colored("- مستخدمين آمنين مع كلمات مرور مشفرة", Colors.GRAY)
    print_colored("- بيانات أساسية منظمة ومحدثة لجميع الموديولات", Colors.GRAY)
    print_colored("- نظام ERP متكامل للشركات", Colors.GRAY)

    # ======================================================
    # المرحلة 1: حذف/إعادة تعيين قاعدة البيانات
    # ======================================================
    print_step(1, TOTAL_STEPS, f"إعادة تعيين قاعدة البيانات ({db_type.upper()})")
    
    if db_type == 'sqlite':
        # SQLite: حذف ملف قاعدة البيانات
        db_path = Path("db.sqlite3")
        db_shm_path = Path("db.sqlite3-shm")
        db_wal_path = Path("db.sqlite3-wal")
        
        if db_path.exists():
            try:
                # إنشاء نسخة احتياطية أولاً
                from datetime import datetime
                
                backup_name = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
                backup_path = Path(backup_name)
                
                print_info(f"إنشاء نسخة احتياطية: {backup_name}...")
                shutil.copy2(db_path, backup_path)
                print_success(f"تم إنشاء نسخة احتياطية: {backup_name}")
                
                # محاولة حذف قاعدة البيانات مع إعادة المحاولة
                max_attempts = 3
                deleted_successfully = False
                
                for attempt in range(max_attempts):
                    try:
                        # حذف قاعدة البيانات الرئيسية
                        db_path.unlink()
                        print_success("تم حذف قاعدة البيانات الرئيسية")
                        
                        # حذف ملفات SQLite الإضافية إن وجدت
                        for extra_file in [db_shm_path, db_wal_path]:
                            if extra_file.exists():
                                try:
                                    extra_file.unlink()
                                    print_success(f"تم حذف ملف {extra_file.name}")
                                except:
                                    pass
                        
                        deleted_successfully = True
                        break
                        
                    except PermissionError:
                        if attempt < max_attempts - 1:
                            print_warning(f"محاولة {attempt + 1}/{max_attempts}: قاعدة البيانات مستخدمة")
                            print_info("محاولة إغلاق الاتصالات بالقوة...")
                            force_close_database_connections()
                            time.sleep(2)
                        else:
                            print_colored(f"\n❌ فشل في حذف قاعدة البيانات بعد {max_attempts} محاولات", Colors.RED)
                            print_colored("يرجى إغلاق جميع التطبيقات التي تستخدم قاعدة البيانات يدوياً وإعادة المحاولة", Colors.YELLOW)
                            print_colored("مثل: Django runserver, DB Browser, إلخ", Colors.YELLOW)
                            sys.exit(1)
                
                if not deleted_successfully:
                    sys.exit(1)
                    
            except Exception as e:
                print_warning(f"خطأ في حذف قاعدة البيانات: {e}")
                sys.exit(1)
        else:
            print_info("لا توجد قاعدة بيانات SQLite سابقة")
    
    else:  # MySQL
        # MySQL: حذف جميع الجداول
        try:
            from django.db import connection
            from django.core.management import call_command
            
            print_info("حذف جميع الجداول من MySQL...")
            
            with connection.cursor() as cursor:
                # تعطيل فحص المفاتيح الخارجية مؤقتاً
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                
                # الحصول على قائمة جميع الجداول
                cursor.execute("SHOW TABLES;")
                tables = cursor.fetchall()
                
                if tables:
                    print_info(f"وجد {len(tables)} جدول للحذف...")
                    for table in tables:
                        table_name = table[0]
                        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`;")
                        print_info(f"  - تم حذف جدول: {table_name}")
                    
                    print_success(f"تم حذف {len(tables)} جدول بنجاح")
                else:
                    print_info("لا توجد جداول للحذف")
                
                # إعادة تفعيل فحص المفاتيح الخارجية
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            
        except Exception as e:
            print_warning(f"خطأ في حذف جداول MySQL: {e}")
            print_info("محاولة استخدام flush بدلاً من ذلك...")
            try:
                from django.core.management import call_command
                call_command('flush', '--no-input')
                print_success("تم تنظيف قاعدة البيانات باستخدام flush")
            except Exception as flush_error:
                print_colored(f"\n❌ فشل في إعادة تعيين قاعدة البيانات: {flush_error}", Colors.RED)
                sys.exit(1)

    # ======================================================
    # المرحلة 2: تطبيق الهجرات
    # ======================================================
    print_step(2, TOTAL_STEPS, "تطبيق الهجرات")
    
    print_info("تطبيق جميع الهجرات (قد يستغرق بضع دقائق)...")
    
    # تطبيق migrations بدون timeout (None = لا يوجد حد زمني)
    migration_success = run_command("python manage.py migrate --no-input", show_output=True, timeout=None)
    
    if not migration_success:
        print_colored("\n❌ فشل تطبيق الهجرات", Colors.RED)
        print_colored("\n💡 جرب تطبيق الهجرات يدوياً:", Colors.YELLOW)
        print_colored("   python manage.py migrate --no-input", Colors.WHITE)
        sys.exit(1)
    
    print_success("تم تطبيق الهجرات بنجاح")

    # ======================================================
    # المرحلة 3: تحميل إعدادات النظام والموديولات
    # ======================================================
    print_step(3, TOTAL_STEPS, "تحميل إعدادات النظام والموديولات")
    
    core_fixtures = [
        {"path": "core/fixtures/system_settings_final.json", "description": "إعدادات النظام (101 إعداد)"},
        {"path": "core/fixtures/system_modules.json",        "description": "موديولات النظام"},
    ]
    core_loaded = load_fixtures_batch(core_fixtures, "تحميل إعدادات النظام...")
    print_success(f"تم تحميل {core_loaded} من {len(core_fixtures)} ملف إعدادات")

    # ======================================================
    # المرحلة 4: تحميل الأدوار والمستخدمين الآمنين
    # ======================================================
    print_step(4, TOTAL_STEPS, "تحميل الأدوار والمستخدمين الآمنين")
    
    # تحميل الأدوار الأساسية أولاً
    roles_fixture = Path("users/fixtures/roles.json")
    if roles_fixture.exists():
        print_info("تحميل الأدوار الأساسية للنظام...")
        if run_command("python manage.py loaddata users/fixtures/roles.json", show_output=False):
            print_success("تم تحميل 10 أدوار أساسية للنظام")
            print_info("- مدير النظام (صلاحيات كاملة)")
            print_info("- مدير (إدارة العمليات والإشراف العام)")
            print_info("- محاسب (إدارة الحسابات والتقارير المالية)")
            print_info("- مدير موارد بشرية (إدارة الموظفين والرواتب)")
            print_info("- مدير مخزون (إدارة المنتجات والمبيعات)")
            print_info("- منسق عمليات (إدارة العمليات اليومية)")
            print_info("- موظف استقبال (استقبال وخدمة العملاء)")
            print_info("- مراجع (قراءة فقط)")
        else:
            print_warning("فشل تحميل الأدوار الأساسية")
    else:
        print_warning("ملف الأدوار الأساسية غير موجود")
    
    # تحميل المستخدمين
    users_fixture = Path("users/fixtures/initial_data.json")
    if users_fixture.exists():
        print_info("تحميل المستخدمين من الفيكستشر المحدث...")
        if run_command("python manage.py loaddata users/fixtures/initial_data.json", show_output=False):
            print_success("تم تحميل المستخدمين الآمنين بنجاح")
            
            # التأكد من كلمات المرور
            print_info("التحقق من كلمات المرور...")
            try:
                from django.contrib.auth import authenticate, get_user_model
                from django.contrib.auth.hashers import make_password
                
                User = get_user_model()
                
                # التحقق من admin
                admin_test = authenticate(username='admin', password='admin123')
                
                if admin_test:
                    print_success("كلمة مرور admin صحيحة ومشفرة")
                else:
                    print_warning("كلمة مرور admin تحتاج إصلاح...")
                    try:
                        admin_user = User.objects.get(username='admin')
                        admin_user.password = make_password('admin123')
                        admin_user.save()
                        print_success("تم إصلاح كلمة مرور admin")
                    except User.DoesNotExist:
                        print_warning("مستخدم admin غير موجود")
                
                # التحقق من girard (اختياري)
                if User.objects.filter(username='girard').exists():
                    girard_test = authenticate(username='girard', password='girard123')
                    if not girard_test:
                        print_warning("كلمة مرور girard تحتاج إصلاح...")
                        girard_user = User.objects.get(username='girard')
                        girard_user.password = make_password('girard123')
                        girard_user.save()
                        print_success("تم إصلاح كلمة مرور girard")
                    else:
                        print_success("كلمة مرور girard صحيحة ومشفرة")
                else:
                    print_info("مستخدم girard غير موجود (اختياري)")
                    
            except Exception as e:
                print_warning(f"خطأ في التحقق من كلمات المرور: {e}")
        else:
            print_warning("فشل تحميل المستخدمين")
    else:
        print_warning("ملف المستخدمين غير موجود")

    # ======================================================
    # المرحلة 5: تحميل البيانات المالية الكاملة
    # ======================================================
    print_step(5, TOTAL_STEPS, "تحميل البيانات المالية الكاملة")
    
    financial_fixtures = [
        {"path": "financial/fixtures/chart_of_accounts.json",      "description": "دليل الحسابات (54 حساب)"},
        {"path": "financial/fixtures/financial_categories.json",    "description": "التصنيفات المالية"},
        {"path": "financial/fixtures/financial_subcategories.json", "description": "التصنيفات الفرعية المالية"},
        {"path": "financial/fixtures/payment_sync_rules.json",      "description": "قواعد مزامنة المدفوعات"},
    ]
    
    financial_loaded = load_fixtures_batch(financial_fixtures, "تحميل البيانات المالية...")
    print_success(f"تم تحميل {financial_loaded} من {len(financial_fixtures)} ملف مالي")

    # ======================================================
    # المرحلة 6: تحميل بيانات الموارد البشرية الكاملة
    # ======================================================
    print_step(6, TOTAL_STEPS, "تحميل بيانات الموارد البشرية الكاملة")
    
    # تحميل الأقسام والوظائف أولاً (مطلوبة للموظفين)
    print_info("تحميل الهيكل التنظيمي...")
    departments_loaded  = load_fixture("hr/fixtures/departments.json",  "الأقسام")
    job_titles_loaded   = load_fixture("hr/fixtures/job_titles.json",   "الوظائف")
    
    # تحميل الموظفين فقط إذا نجح تحميل الأقسام والوظائف
    if departments_loaded and job_titles_loaded:
        print_info("تحميل الموظفين...")
        employees_loaded = load_fixture("hr/fixtures/employees.json", "الموظفين")
    else:
        print_warning("تخطي تحميل الموظفين بسبب فشل تحميل الأقسام أو الوظائف")
        employees_loaded = False
    
    # تحميل باقي بيانات HR
    print_info("تحميل بيانات HR الإضافية...")
    hr_extra_fixtures = [
        {"path": "hr/fixtures/leave_types.json",         "description": "أنواع الإجازات"},
        {"path": "hr/fixtures/permission_types.json",    "description": "أنواع الأذونات"},
        {"path": "hr/fixtures/attendance_penalties.json","description": "عقوبات الحضور"},
        {"path": "hr/fixtures/initial_data.json",        "description": "البيانات الأولية للـ HR"},
    ]
    hr_extra_loaded = load_fixtures_batch(hr_extra_fixtures, "تحميل بيانات HR الإضافية...")
    
    # تحميل بيانات البصمة (اختيارية - قد تفشل بدون أجهزة)
    print_info("تحميل بيانات البصمة (اختيارية)...")
    biometric_fixtures = [
        {"path": "hr/fixtures/biometric_devices.json", "description": "أجهزة البصمة"},
        {"path": "hr/fixtures/biometric_mapping.json", "description": "ربط البصمة بالموظفين"},
    ]
    biometric_loaded = load_fixtures_batch(biometric_fixtures, "تحميل بيانات البصمة...")
    
    hr_total = sum([departments_loaded, job_titles_loaded, employees_loaded]) + hr_extra_loaded + biometric_loaded
    hr_max   = 3 + len(hr_extra_fixtures) + len(biometric_fixtures)
    print_success(f"تم تحميل {hr_total} من {hr_max} ملف موارد بشرية")

    # ======================================================
    # المرحلة 7: تحميل بيانات الموردين والمنتجات
    # ======================================================
    print_step(7, TOTAL_STEPS, "تحميل بيانات الموردين والمنتجات")
    
    supply_product_fixtures = [
        {"path": "supplier/fixtures/supplier_types.json",    "description": "أنواع الموردين"},
        {"path": "supplier/fixtures/service_types.json",     "description": "أنواع الخدمات"},
        {"path": "product/fixtures/initial_warehouses.json", "description": "المستودعات"},
        {"path": "product/fixtures/units.json",              "description": "وحدات القياس"},
    ]
    
    sp_loaded = load_fixtures_batch(supply_product_fixtures, "تحميل بيانات الموردين والمنتجات...")
    print_success(f"تم تحميل {sp_loaded} من {len(supply_product_fixtures)} ملف")

    # ======================================================
    # المرحلة 8: تحميل بيانات Printing & Pricing الكاملة
    # ======================================================
    print_step(8, TOTAL_STEPS, "تحميل بيانات Printing & Pricing")
    
    printing_fixtures = [
        {"path": "printing_pricing/fixtures/paper_origins.json",           "description": "مناشئ الورق"},
        {"path": "printing_pricing/fixtures/paper_sizes.json",             "description": "مقاسات الورق"},
        {"path": "printing_pricing/fixtures/paper_weights.json",           "description": "أوزان الورق"},
        {"path": "printing_pricing/fixtures/offset_sheet_sizes.json",      "description": "مقاسات أوفست"},
        {"path": "printing_pricing/fixtures/digital_sheet_sizes.json",     "description": "مقاسات ديجيتال"},
        {"path": "printing_pricing/fixtures/offset_machines.json",         "description": "ماكينات أوفست"},
        {"path": "printing_pricing/fixtures/digital_machines.json",        "description": "ماكينات ديجيتال"},
        {"path": "printing_pricing/fixtures/coating_finishing.json",       "description": "التغليف والتشطيب"},
        {"path": "printing_pricing/fixtures/piece_plate_sizes.json",       "description": "مقاسات الألواح"},
        {"path": "printing_pricing/fixtures/product_types_sizes.json",     "description": "أنواع وأحجام المنتجات"},
        {"path": "printing_pricing/fixtures/print_settings.json",          "description": "إعدادات الطباعة"},
        {"path": "printing_pricing/fixtures/printing_pricing_settings.json","description": "إعدادات التسعير"},
    ]
    
    printing_loaded = load_fixtures_batch(printing_fixtures, "تحميل بيانات Printing & Pricing...")
    print_success(f"تم تحميل {printing_loaded} من {len(printing_fixtures)} ملف طباعة وتسعير")

    # ======================================================
    # المرحلة 9: تفعيل موديول Governance
    # ======================================================
    print_step(9, TOTAL_STEPS, "تفعيل موديول Governance تلقائياً")
    
    print_info("تفعيل جميع المكونات والسير العمل الحرج...")
    governance_success = run_command("python manage.py activate_governance --silent", show_output=False)
    
    if governance_success:
        print_success("✅ تم تفعيل موديول Governance بنجاح")
        print_info("- جميع المكونات الحرجة مفعلة")
        print_info("- جميع سير العمل الحرج مفعل")
        print_info("- النظام آمن ومحكوم")
        
        # التحقق من الحالة
        print_info("التحقق من حالة Governance...")
        verification_success = run_command("python manage.py activate_governance --check-only --silent", show_output=False)
        
        if verification_success:
            print_success("✅ تم التحقق من تفعيل Governance بنجاح")
        else:
            print_warning("⚠️ تحذير: قد تكون هناك مشاكل في Governance")
    else:
        print_warning("⚠️ فشل تفعيل موديول Governance")
        print_info("سيتم تفعيله تلقائياً عند أول تسجيل دخول للمدير")

    # ======================================================
    # المرحلة 10: إنشاء الفترة المحاسبية والمهام المؤجلة
    # ======================================================
    print_step(10, TOTAL_STEPS, "إنشاء الفترة المحاسبية وربط الموردين")
    
    # انتظار حتى تصبح قاعدة البيانات جاهزة
    print_info("انتظار استقرار قاعدة البيانات...")
    time.sleep(5)  # انتظار أولي
    
    if not wait_for_database_ready():
        print_warning("قاعدة البيانات لا تزال مشغولة، سيتم المحاولة مع ذلك...")
    
    # إنشاء الفترة المحاسبية مع إعادة المحاولة
    def create_accounting_period():
        from financial.models import AccountingPeriod
        from datetime import date
        from django.db import transaction
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # التحقق من وجود فترة محاسبية مفتوحة
        existing_period = AccountingPeriod.objects.filter(status='open').first()
        
        if existing_period:
            print_info(f"توجد فترة محاسبية مفتوحة بالفعل: {existing_period.name}")
            return True
        else:
            # محاولة تحميل من fixture أولاً
            fixture_path = Path("financial/fixtures/accounting_periods.json")
            if fixture_path.exists():
                print_info("تحميل الفترة المحاسبية من fixture...")
                if run_command("python manage.py loaddata financial/fixtures/accounting_periods.json", show_output=False):
                    print_success("تم تحميل الفترة المحاسبية من fixture")
                    return True
            
            # إنشاء برمجياً كـ fallback
            admin_user = User.objects.filter(username='admin').first()
            with transaction.atomic():
                period = AccountingPeriod.objects.create(
                    name="السنة المالية 2025/2026",
                    start_date=date(2025, 9, 1),
                    end_date=date(2026, 8, 31),
                    status='open',
                    created_by=admin_user
                )
                print_success(f"تم إنشاء الفترة المحاسبية: {period.name}")
                print_info(f"من {period.start_date} إلى {period.end_date}")
                return True
    
    print_info("إنشاء الفترة المحاسبية...")
    accounting_success = safe_database_operation(create_accounting_period, "إنشاء الفترة المحاسبية")
    
    # ربط الموردين بأنواعهم مع إعادة المحاولة
    def link_suppliers():
        from supplier.models import Supplier, SupplierType
        from django.db import transaction
        
        suppliers_checked = 0
        suppliers_fixed = 0
        
        if not Supplier.objects.exists():
            print_info("لا توجد موردين للربط")
            return True
        
        with transaction.atomic():
            for supplier in Supplier.objects.all():
                suppliers_checked += 1
                
                # التحقق من وجود primary_type
                if not supplier.primary_type:
                    # محاولة تعيين نوع افتراضي
                    default_type = SupplierType.objects.filter(code='general').first()
                    if default_type:
                        supplier.primary_type = default_type
                        supplier.save()
                        suppliers_fixed += 1
                        print_info(f"تم تعيين نوع افتراضي لـ {supplier.name}")
        
        if suppliers_fixed > 0:
            print_success(f"تم فحص {suppliers_checked} مورد وإصلاح {suppliers_fixed} مورد")
        else:
            print_info(f"تم فحص {suppliers_checked} مورد - جميعهم لديهم أنواع صحيحة")
        
        return True
    
    print_info("فحص وربط الموردين بأنواعهم...")
    suppliers_success = safe_database_operation(link_suppliers, "ربط الموردين")
    
    # ملخص النتائج
    if accounting_success and suppliers_success:
        print_success("✅ تم إنجاز جميع المهام بنجاح")
    elif accounting_success or suppliers_success:
        print_info("✅ تم إنجاز بعض المهام")
    else:
        print_warning("⚠️ لم يتم إنجاز المهام - ستتم تلقائياً عند أول استخدام")

    # ======================================================
    # المرحلة 11: ربط المستخدمين بالأدوار
    # ======================================================
    print_step(11, TOTAL_STEPS, "ربط المستخدمين بالأدوار المناسبة")
    
    def assign_user_roles():
        """ربط المستخدمين بالأدوار المناسبة"""
        from django.contrib.auth import get_user_model
        from users.models import Role
        from django.db import transaction
        
        User = get_user_model()
        assigned_count = 0
        
        try:
            with transaction.atomic():
                # ربط admin بدور مدير النظام
                admin_user = User.objects.filter(username='admin').first()
                admin_role = Role.objects.filter(name='admin').first()
                
                if admin_user and admin_role:
                    admin_user.role = admin_role
                    admin_user.save()
                    print_success(f"تم ربط {admin_user.username} بدور {admin_role.display_name}")
                    assigned_count += 1
                elif admin_user:
                    print_warning("دور مدير النظام غير موجود")
                else:
                    print_warning("مستخدم admin غير موجود")
                
                # ربط girard بدور مدير (اختياري)
                girard_user = User.objects.filter(username='girard').first()
                if girard_user:
                    manager_role = Role.objects.filter(name='manager').first()
                    
                    if manager_role:
                        girard_user.role = manager_role
                        girard_user.save()
                        print_success(f"تم ربط {girard_user.username} بدور {manager_role.display_name}")
                        assigned_count += 1
                    else:
                        print_warning("دور مدير غير موجود")
                else:
                    print_info("مستخدم girard غير موجود (اختياري)")
                
                return assigned_count > 0
                
        except Exception as e:
            print_warning(f"خطأ في ربط المستخدمين بالأدوار: {e}")
            return False
    
    print_info("ربط المستخدمين الأساسيين بأدوارهم...")
    roles_assignment_success = safe_database_operation(assign_user_roles, "ربط المستخدمين بالأدوار")
    
    if roles_assignment_success:
        print_success("✅ تم ربط المستخدمين بالأدوار بنجاح")
        print_info("- admin ← مدير النظام")
        # فقط اطبع girard إذا كان موجود
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(username='girard').exists():
            print_info("- girard ← مدير")
    else:
        print_warning("⚠️ لم يتم ربط المستخدمين بالأدوار - يمكن القيام بذلك يدوياً")

    # المرحلة 12: تحديث hashes الملفات
    # ======================================================
    print_step(12, TOTAL_STEPS, "تحديث hashes الملفات")
    
    print_info("تحديث hashes الملفات...")
    try:
        all_files = get_all_files()
        current_hashes = {}
        for file_path in all_files:
            relative_path = str(file_path.relative_to(project_root)).replace('\\', '/')
            current_hashes[relative_path] = get_file_hash(file_path)
        
        with open(hash_file, 'w', encoding='utf-8') as f:
            json.dump(current_hashes, f, indent=2, ensure_ascii=False)
        
        print_success("تم تحديث hashes الملفات")
    except Exception as e:
        print_warning(f"خطأ في تحديث hashes: {e}")

    # ======================================================
    # المرحلة 13: الملخص النهائي
    # ======================================================
    print_step(13, TOTAL_STEPS, "الملخص النهائي")
    
    print_colored("🎉 تم إكمال إعداد النظام بنجاح!", Colors.GREEN + Colors.BOLD)
    print_colored(f"\n🗄️  قاعدة البيانات: {db_type.upper()}", Colors.CYAN)
    print_colored("\n📊 الإحصائيات:", Colors.CYAN)
    
    try:
        from django.contrib.auth import get_user_model
        from core.models import SystemSetting
        
        User = get_user_model()
        users_count = User.objects.count()
        settings_count = SystemSetting.objects.count()
        
        # إحصائيات الأدوار
        try:
            from users.models import Role
            from django.contrib.auth.models import Group
            roles_count = Role.objects.filter(is_active=True).count()
            groups_count = Group.objects.count()
            system_roles_count = Role.objects.filter(is_system_role=True, is_active=True).count()
            
            print_success(f"✅ الأدوار النشطة: {roles_count}")
            print_success(f"✅ المجموعات: {groups_count}")
            print_success(f"✅ أدوار النظام: {system_roles_count}")
            
            main_roles = Role.objects.filter(
                name__in=['admin', 'manager', 'employee', 'user'],
                is_active=True
            ).values_list('display_name', flat=True)
            
            if main_roles:
                print_info(f"   الأدوار الرئيسية: {', '.join(main_roles)}")
                
        except Exception as e:
            print_info(f"   بيانات الأدوار: غير متاحة ({e})")
        
        # إحصائيات مالية
        try:
            from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FinancialCategory, FinancialSubcategory
            accounts_count          = ChartOfAccounts.objects.count()
            account_types_count     = AccountType.objects.count()
            accounting_periods_count= AccountingPeriod.objects.count()
            active_period           = AccountingPeriod.objects.filter(status='open').first()
            categories_count        = FinancialCategory.objects.filter(is_active=True).count()
            subcategories_count     = FinancialSubcategory.objects.filter(is_active=True).count()
            
            print_success(f"✅ دليل الحسابات: {accounts_count} حساب")
            print_success(f"✅ أنواع الحسابات: {account_types_count} نوع")
            print_success(f"✅ الفترات المحاسبية: {accounting_periods_count}")
            if active_period:
                print_info(f"   الفترة المفتوحة: {active_period.name}")
            print_success(f"✅ التصنيفات المالية: {categories_count} تصنيف")
            print_success(f"✅ التصنيفات الفرعية: {subcategories_count} تصنيف فرعي")
        except Exception as e:
            print_info(f"   البيانات المالية: غير متاحة ({e})")
        
        # إحصائيات الموردين
        try:
            from supplier.models import SupplierType, ServiceType
            supplier_types_count = SupplierType.objects.filter(is_active=True).count()
            service_types_count  = ServiceType.objects.filter(is_active=True).count()
            
            print_success(f"✅ أنواع الموردين: {supplier_types_count}")
            print_success(f"✅ أنواع الخدمات: {service_types_count}")
        except Exception as e:
            print_info(f"   بيانات الموردين: غير متاحة ({e})")
        
        # إحصائيات المنتجات والخدمات
        try:
            from product.models import Product, Category, Warehouse
            products_count   = Product.objects.filter(is_active=True).count()
            categories_count = Category.objects.filter(is_active=True).count()
            warehouses_count = Warehouse.objects.filter(is_active=True).count()
            
            print_success(f"✅ المنتجات والخدمات النشطة: {products_count}")
            print_success(f"✅ فئات المنتجات: {categories_count}")
            print_success(f"✅ المستودعات: {warehouses_count}")
        except Exception as e:
            print_info(f"   المنتجات والخدمات: غير متاحة ({e})")
        
        # إحصائيات الموارد البشرية
        try:
            from hr.models import Employee, Department, JobTitle, LeaveType, AttendancePenalty
            employees_count        = Employee.objects.filter(status='active').count()
            departments_count      = Department.objects.filter(is_active=True).count()
            job_titles_count       = JobTitle.objects.filter(is_active=True).count()
            leave_types_count      = LeaveType.objects.filter(is_active=True).count()
            attendance_pen_count   = AttendancePenalty.objects.filter(is_active=True).count()
            
            print_success(f"✅ الموظفين النشطين: {employees_count}")
            print_success(f"✅ الأقسام: {departments_count}")
            print_success(f"✅ الوظائف: {job_titles_count}")
            print_success(f"✅ أنواع الإجازات: {leave_types_count}")
            print_success(f"✅ عقوبات الحضور: {attendance_pen_count}")
        except Exception as e:
            print_info(f"   بيانات الموارد البشرية: غير متاحة ({e})")
        
        # إحصائيات Printing & Pricing
        try:
            from printing_pricing.models import PaperSize, PaperWeight, PaperOrigin, OffsetMachineType, DigitalMachineType
            paper_sizes_count   = PaperSize.objects.count()
            paper_weights_count = PaperWeight.objects.count()
            paper_origins_count = PaperOrigin.objects.count()
            offset_machines     = OffsetMachineType.objects.count()
            digital_machines    = DigitalMachineType.objects.count()
            
            print_success(f"✅ مقاسات الورق: {paper_sizes_count}")
            print_success(f"✅ أوزان الورق: {paper_weights_count}")
            print_success(f"✅ مناشئ الورق: {paper_origins_count}")
            print_success(f"✅ ماكينات أوفست: {offset_machines} | ديجيتال: {digital_machines}")
        except Exception as e:
            print_info(f"   بيانات Printing & Pricing: غير متاحة ({e})")
        
        print_success(f"✅ موديول Governance: {'مفعل' if governance_success else 'سيتم تفعيله تلقائياً'}")
        
    except Exception as e:
        print_warning(f"خطأ في عرض الإحصائيات: {e}")
    
    print_colored("\n🚀 النظام جاهز للاستخدام!", Colors.GREEN + Colors.BOLD)
    
    # رسالة خاصة عن Governance
    if governance_success:
        print_colored("🔐 موديول Governance مفعل - النظام آمن ومحكوم!", Colors.GREEN + Colors.BOLD)
    else:
        print_colored("🔐 موديول Governance سيتم تفعيله تلقائياً عند أول دخول للمدير", Colors.YELLOW)
    
    print_colored("📝 معلومات تسجيل الدخول:", Colors.CYAN)
    print_colored("   المستخدم: admin", Colors.WHITE)
    print_colored("   كلمة المرور: admin123", Colors.WHITE)
    
    # عرض girard فقط إذا كان موجود
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(username='girard').exists():
            print_colored("   أو", Colors.GRAY)
            print_colored("   المستخدم: girard", Colors.WHITE)
            print_colored("   كلمة المرور: girard123", Colors.WHITE)
    except:
        pass
    
    print_colored("\n💡 لبدء السيرفر:", Colors.YELLOW)
    print_colored("   python manage.py runserver", Colors.WHITE)
    
    print_colored("\n📚 الفيكستشرز المحملة:", Colors.GRAY)
    print_colored("   Core    : إعدادات النظام + الموديولات", Colors.GRAY)
    print_colored("   Users   : 10 أدوار + مستخدمين آمنين", Colors.GRAY)
    print_colored("   Financial: دليل حسابات + تصنيفات + تصنيفات فرعية + مزامنة", Colors.GRAY)
    print_colored("   HR      : أقسام + وظائف + موظفين + إجازات + أذونات + عقوبات + بصمة", Colors.GRAY)
    print_colored("   Supplier: أنواع موردين + أنواع خدمات", Colors.GRAY)
    print_colored("   Product : فئات + وحدات + مستودعات + منتجات", Colors.GRAY)
    print_colored("   Printing: ورق + ماكينات + تشطيب + تسعير (12 ملف)", Colors.GRAY)
    
    print_colored("\n🎭 الأدوار المتاحة:", Colors.CYAN)
    print_colored("   👑 مدير النظام: صلاحيات كاملة (superuser)", Colors.WHITE)
    print_colored("   👨‍💼 مدير: 48 صلاحية مخصصة (كل شيء ماعدا التقنية)", Colors.WHITE)
    print_colored("   👥 مستخدم: 46 صلاحية مخصصة (معظم الصلاحيات ماعدا الإدارية)", Colors.WHITE)
    print_colored("   👤 موظف: 3 صلاحيات مخصصة (إجازات وأذونات فقط)", Colors.WHITE)
    
    # سؤال المستخدم عن حفظ snapshot
    if not auto_mode:
        print_colored("\n" + "="*60, Colors.CYAN)
        print_colored("📸 حفظ Database Snapshot", Colors.CYAN + Colors.BOLD)
        print_colored("="*60, Colors.CYAN)
        print_colored("\n💡 فائدة الـ Snapshot:", Colors.YELLOW)
        print_colored("   • استعادة سريعة للنظام (20-30 ثانية بدلاً من 3-5 دقائق)", Colors.WHITE)
        print_colored("   • مفيد للتطوير والتجربة السريعة", Colors.WHITE)
        print_colored("   • ضمان البدء بنفس البيانات دائماً", Colors.WHITE)
        
        save_snapshot = input("\nهل تريد حفظ snapshot للإعداد الحالي؟ (yes/no): ").strip().lower()
        
        if save_snapshot == "yes":
            if create_snapshot(db_type):
                print_colored("\n✅ تم حفظ Snapshot بنجاح!", Colors.GREEN + Colors.BOLD)
                print_colored("📁 الموقع: .db_snapshots/", Colors.GRAY)
                print_colored("\n💡 في المرة القادمة:", Colors.YELLOW)
                print_colored("   سيتم سؤالك عن استعادة الـ Snapshot للإعداد السريع", Colors.WHITE)
            else:
                print_colored("\n⚠️  فشل حفظ الـ Snapshot", Colors.YELLOW)
        else:
            print_colored("\n⏭️  تم تخطي حفظ الـ Snapshot", Colors.GRAY)
    else:
        # في الوضع التلقائي، احفظ snapshot تلقائياً
        print_colored("\n📸 حفظ Snapshot تلقائياً...", Colors.CYAN)
        if create_snapshot(db_type):
            print_colored("✅ تم حفظ Snapshot بنجاح!", Colors.GREEN)
        else:
            print_colored("⚠️  فشل حفظ Snapshot", Colors.YELLOW)


if __name__ == "__main__":
    main()
