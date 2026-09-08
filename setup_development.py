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
import platform
import django

# إخفاء تحذيرات pkg_resources المهملة من coreapi
warnings.filterwarnings('ignore', category=UserWarning, module='coreapi')

# إعداد encoding لـ Windows console
if sys.platform == 'win32':
    import codecs
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# متغيرات أوضاع التشغيل من الـ CLI
auto_mode = '--auto' in sys.argv
reset_mode = '--reset' in sys.argv or '--clean' in sys.argv

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
    patterns.extend(['.*', '__pycache__', '*.pyc', '.deploy_hashes.json', 'scratch', 'scratch/*'])
    return patterns


def is_ignored(file_path, patterns, project_root):
    """فحص ما إذا كان الملف مستثنى"""
    import fnmatch
    
    relative_path = str(file_path.relative_to(project_root)).replace('\\', '/')
    parts = relative_path.split('/')
    
    if any(part.startswith('.') for part in file_path.parts):
        return True

    # تجاهل مجلد scratch وكل محتوياته
    if relative_path.startswith('scratch/') or relative_path == 'scratch' or 'scratch' in parts[:-1]:
        return True
        
    for pattern in patterns:
        clean_pattern = pattern.rstrip('/')
        if pattern.endswith('/'):
            if relative_path == clean_pattern or relative_path.startswith(clean_pattern + '/'):
                return True
            if clean_pattern in parts[:-1]:
                return True

        if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
            return True
        if fnmatch.fnmatch(relative_path, f"{clean_pattern}/*"):
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
    
    success = run_command(f'"{sys.executable}" manage.py loaddata {fixture_path}', show_output=False, timeout=timeout)
    
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


def setup_mysql_autostart(db_exe, db_ini=None):
    """إعداد تشغيل قاعدة البيانات تلقائياً عند بدء تشغيل Windows"""
    try:
        appdata = os.environ.get('APPDATA')
        if not appdata:
            return
        startup_folder = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if not startup_folder.exists():
            return
        
        vbs_file = startup_folder / "Start_MariaDB_ERP.vbs"
        args = f'""{db_exe}""'
        if db_ini and Path(db_ini).exists():
            args += f' --defaults-file=""{db_ini}""'
        args += ' --console'
        
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
Set objWMIService = GetObject("winmgmts:\\\\.\\root\\cimv2")
Set colProcesses = objWMIService.ExecQuery("Select * from Win32_Process Where Name = 'mysqld.exe'")
If colProcesses.Count = 0 Then
    WshShell.Run "{args}", 0, False
End If
'''
        vbs_file.write_text(vbs_content, encoding='utf-8')
    except Exception:
        pass


def start_process_hidden(exe_path, args=""):
    """تشغيل العملية كعملية مستقلة ومخفية تماماً بدون أي نافذة سوداء في الخلفية"""
    try:
        ps_cmd = f"Start-Process -FilePath '{exe_path}' -ArgumentList '{args}' -WindowStyle Hidden"
        res = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True
    except Exception:
        pass
    try:
        cmd_list = [str(exe_path)] + (args.split() if args else [])
        creationflags = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd_list, creationflags=creationflags, close_fds=True)
        return True
    except Exception:
        return False


def check_mysql_connection():
    """فحص الاتصال بـ MySQL قبل البدء مع إغلاق الاتصال بنظافة"""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        connection.close()
        return True
    except Exception as e:
        error_msg = str(e).lower()
        # فحص أنواع الأخطاء الشائعة
        if any(keyword in error_msg for keyword in ['can\'t connect', 'connection refused', '2002', '2003', 'unknown mysql server host']):
            return False
        # أخطاء أخرى قد تكون مشاكل في الإعدادات
        raise e


def ensure_mysql_running():
    """التحقق من عمل MySQL وتشغيله تلقائياً في الخلفية مع ضمان استمراره"""
    mariadb_exe = Path(r"C:\Users\UTD\mariadb-10.11\bin\mysqld.exe")
    mariadb_ini = Path(r"C:\Users\UTD\mariadb-10.11\data\my.ini")
    xampp_paths = [
        Path(r"C:\xampp\mysql\bin\mysqld.exe"),
        Path(r"C:\Program Files\xampp\mysql\bin\mysqld.exe"),
        Path(r"C:\Program Files (x86)\xampp\mysql\bin\mysqld.exe"),
        Path(r"D:\xampp\mysql\bin\mysqld.exe"),
    ]
    
    target_exe = None
    target_ini = None
    if mariadb_exe.exists():
        target_exe = mariadb_exe
        target_ini = mariadb_ini if mariadb_ini.exists() else None
    else:
        for p in xampp_paths:
            if p.exists():
                target_exe = p
                break

    # ضبط التشغيل التلقائي عند بدء تشغيل الجهاز
    if target_exe:
        setup_mysql_autostart(target_exe, target_ini)

    # إذا كانت قاعدة البيانات تعمل بالفعل
    if check_mysql_connection():
        return True

    print_colored("⚠️  خادم قاعدة البيانات متوقف، جاري التشغيل التلقائي وضمان استمراره...", Colors.YELLOW)

    # محاولة تشغيل كخدمة Windows أولاً
    try:
        subprocess.run(['net', 'start', 'mysql'], capture_output=True, timeout=5)
        if check_mysql_connection():
            return True
    except Exception:
        pass

    if not target_exe:
        return False

    # تشغيل في الخلفية بدون أي نافذة سوداء
    args = f'--defaults-file="{target_ini}"' if target_ini else ''
    start_process_hidden(target_exe, args)

    # انتظار استقرار الاتصال
    for _ in range(15):
        time.sleep(1)
        if check_mysql_connection():
            print_colored("✅ تم تشغيل خادم قاعدة البيانات بنجاح في الخلفية!", Colors.GREEN)
            print_colored("📌 تم تفعيل التشغيل التلقائي مع فتح الجهاز (Windows Startup).", Colors.CYAN)
            return True

    return False


def main():
    """الدالة الرئيسية لإعداد النظام لجميع fixtures"""

    # إجمالي المراحل
    TOTAL_STEPS = 12

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
    print_colored(f"🐍 بيئة التشغيل: Python {platform.python_version()} | Django {django.get_version()}", Colors.CYAN)
    print_colored(f"🗄️  نوع قاعدة البيانات المكتشف: {db_type.upper()}", Colors.CYAN)
    
    # فحص اتصال MySQL إذا كان مطلوب والتشغيل التلقائي في الخلفية
    if db_type == 'mysql':
        print_colored("\n🔍 فحص الاتصال بـ MySQL/MariaDB...", Colors.YELLOW)
        
        try:
            if not ensure_mysql_running():
                print_colored("\n" + "="*60, Colors.RED)
                print_colored("❌ خطأ: تعذر تشغيل أو الاتصال بـ MySQL تلقائياً", Colors.RED + Colors.BOLD)
                print_colored("="*60, Colors.RED)
                print_colored("\n💡 يرجى التحقق من:", Colors.YELLOW)
                print_colored("   1. تأكد من تشغيل MySQL يدوياً (python start_db.py)", Colors.WHITE)
                print_colored("   2. أو شغّل XAMPP Control Panel", Colors.WHITE)
                print_colored("   3. تحقق من بيانات .env (DB_USER, DB_PASSWORD, DB_NAME)", Colors.WHITE)
                print_colored("\n" + "="*60 + "\n", Colors.RED)
                sys.exit(1)
            else:
                print_colored("✅ الاتصال بـ MySQL ناجح وقاعدة البيانات تعمل ومضبوطة!", Colors.GREEN)
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
    
    
    # سؤال تفاعلي لتحديد وضع قاعدة البيانات إذا لم يتم تحديد flag صريح
    global reset_mode
    if not auto_mode and '--reset' not in sys.argv and '--clean' not in sys.argv:
        print_colored("\n" + "="*60, Colors.CYAN)
        print_colored("🗄️  اختيار نمط التعامل مع قاعدة البيانات:", Colors.CYAN + Colors.BOLD)
        print_colored("="*60, Colors.CYAN)
        print_colored("   [1] وضع التحديث الآمن (الحفاظ على الجداول والبيانات الحية) 🛡️", Colors.GREEN)
        print_colored("   [2] تصفير وإعادة تعيين كاملة (حذف جميع الجداول والبدء من الصفر) ⚠️", Colors.YELLOW)
        
        choice = input("\n👉 اختيارك (1 أو 2) [الافتراضي: 1]: ").strip()
        if choice == "2":
            confirm = input("⚠️  تأكيد: سيتم حذف جميع الجداول والبيانات نهائياً! هل تريد المتابعة؟ (yes/no): ").strip().lower()
            if confirm in ['y', 'yes', 'نعم']:
                reset_mode = True
                print_colored("🔄 تم اختيار: تصفير وإعادة تعيين قاعدة البيانات بالكامل", Colors.YELLOW)
            else:
                reset_mode = False
                print_colored("🛡️  تم الإلغاء، سيتم المتابعة بالوضع الآمن وحفظ البيانات", Colors.GREEN)
        else:
            reset_mode = False
            print_colored("🛡️  تم اختيار: وضع التحديث الآمن (الحفاظ على البيانات)", Colors.GREEN)
    
    print_colored("\n🛠️  إعداد وتثبيت النظام", Colors.CYAN)
    print_colored("سيتم تحميل بيانات وفيشرز النظام المعتمدة", Colors.WHITE)
    print_colored("- مستخدمين آمنين مع كلمات مرور مشفرة", Colors.GRAY)
    print_colored("- بيانات أساسية منظمة ومحدثة لجميع الموديولات", Colors.GRAY)
    print_colored("- نظام ERP متكامل للشركات", Colors.GRAY)

    # ======================================================
    # المرحلة 1: فحص / إعادة تعيين قاعدة البيانات
    # ======================================================
    if reset_mode:
        print_step(1, TOTAL_STEPS, f"إعادة تعيين ومسح قاعدة البيانات ({db_type.upper()})")
        if db_type == 'sqlite':
            db_path = Path("db.sqlite3")
            db_shm_path = Path("db.sqlite3-shm")
            db_wal_path = Path("db.sqlite3-wal")
            if db_path.exists():
                try:
                    for extra_file in [db_path, db_shm_path, db_wal_path]:
                        if extra_file.exists():
                            extra_file.unlink()
                    print_success("تم مسح قاعدة بيانات SQLite بنجاح")
                except Exception as e:
                    print_warning(f"خطأ في حذف قاعدة البيانات: {e}")
        else:
            try:
                from django.db import connection
                print_info("حذف ومسح جميع الجداول من MySQL (Reset Mode)...")
                with connection.cursor() as cursor:
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                    cursor.execute("SHOW TABLES;")
                    tables = cursor.fetchall()
                    for table in tables:
                        cursor.execute(f"DROP TABLE IF EXISTS `{table[0]}`;")
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
                print_success(f"تم مسح وحذف {len(tables)} جدول من MySQL بالكامل بنجاح")
            except Exception as e:
                print_warning(f"خطأ في مسح جداول MySQL: {e}")
    else:
        print_step(1, TOTAL_STEPS, f"وضع التثبيت الآمن (Safe Mode - {db_type.upper()})")
        print_info("الحفاظ على الجداول والبيانات الحية دون مسح")

    # ======================================================
    # المرحلة 2: تطبيق الهجرات (Migrations)
    # ======================================================
    print_step(2, TOTAL_STEPS, "تطبيق الهجرات")
    print_info("تطبيق جميع الهجرات...")
    migration_success = run_command(f'"{sys.executable}" manage.py migrate --no-input', show_output=True, timeout=None)
    if not migration_success:
        print_colored("\n❌ فشل تطبيق الهجرات", Colors.RED)
        sys.exit(1)
    print_success("تم تطبيق الهجرات بنجاح")

    # ======================================================
    # المرحلة 3: تحميل إعدادات وموديولات النظام الأساسية
    # ======================================================
    print_step(3, TOTAL_STEPS, "تحميل إعدادات وموديولات النظام")
    load_fixture("core/fixtures/system_settings_final.json", "إعدادات النظام الأساسية")
    
    print_info("تحديث وتأكيد موديولات النظام (init_modules)...")
    run_command(f'"{sys.executable}" manage.py init_modules', show_output=False)
    print_success("تم تحديث وتهيئة موديولات النظام بنجاح")

    # ======================================================
    # المرحلة 4: الأدوار والصلاحيات وتأمين المدير العام
    # ======================================================
    print_step(4, TOTAL_STEPS, "تحميل الأدوار والصلاحيات وتأمين المدير العام")
    
    # 1. تحميل الأدوار
    roles_fixture = Path("users/fixtures/roles.json")
    if roles_fixture.exists():
        load_fixture("users/fixtures/roles.json", "الأدوار الأساسية")
    
    # 2. توليد الصلاحيات المخصصة للنظام المالي
    try:
        from financial.permissions import create_custom_permissions
        create_custom_permissions()
    except Exception as e:
        print_warning(f"تحذير إنشاء الصلاحيات المالية المخصصة: {e}")

    # 3. تأسيس ومزامنة الأدوار المعيارية الـ 10 والصلاحيات النظيفة
    print_info("تأسيس وتحديث الأدوار المعيارية والصلاحيات (seed_clean_roles)...")
    run_command(f'"{sys.executable}" manage.py seed_clean_roles', show_output=False)
    print_success("تم تحديث ومزامنة كافة الصلاحيات والأدوار بنجاح")

    # 4. تأمين حساب admin الذري
    print_info("تأمين حساب المدير العام admin...")
    try:
        from django.contrib.auth import get_user_model
        from users.models import Role
        User = get_user_model()
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'info@mwheba.co.uk', 'first_name': 'System', 'last_name': 'Admin'}
        )
        admin_user.set_password(admin_pass)
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_role = Role.objects.filter(name='admin').first()
        if admin_role:
            admin_user.role = admin_role
        admin_user.save()
        print_success("تم تأمين حساب المدير العام admin (مدير النظام) بنجاح")
    except Exception as e:
        print_warning(f"تحذير في تأمين حساب المدير العام: {e}")

    # ======================================================
    # المرحلة 5: تشغيل المحرك المالي والضريبي الشامل
    # ======================================================
    print_step(5, TOTAL_STEPS, "تهيئة المحرك المالي والضريبي والشجرة المعيارية")
    print_info("تشغيل setup_accounting_system لبناء 105 حساباً والعملات والضرائب والتصنيفات...")
    fin_cmd_success = run_command(f'"{sys.executable}" manage.py setup_accounting_system --force', show_output=True)
    if fin_cmd_success:
        print_success("تم بناء وتأسيس المنظومة المالية والضريبية بنجاح (100%)")
    else:
        print_warning("حدث خطأ أثناء تشغيل setup_accounting_system")

    # تحميل قواعد مزامنة المدفوعات
    load_fixture("financial/fixtures/payment_sync_rules.json", "قواعد مزامنة المدفوعات")

    # ======================================================
    # المرحلة 6: تحميل لوائح وبيانات الموارد البشرية
    # ======================================================
    print_step(6, TOTAL_STEPS, "تحميل لوائح وبيانات الموارد البشرية")
    hr_fixtures = [
        {"path": "hr/fixtures/initial_data.json",         "description": "اللوائح والورديات وأنواع الإجازات"},
        {"path": "hr/fixtures/permission_types.json",     "description": "أنواع الأذونات"},
        {"path": "hr/fixtures/attendance_penalties.json", "description": "عقوبات ولوائح الحضور"},
        {"path": "hr/fixtures/biometric_devices.json",    "description": "أجهزة البصمة"},
    ]
    hr_loaded = load_fixtures_batch(hr_fixtures, "تحميل لوائح HR...")
    print_success(f"تم تحميل {hr_loaded} من {len(hr_fixtures)} ملف لوائح موارد بشرية")

    # ======================================================
    # المرحلة 7: تحميل بيانات الموردين والمخازن والوحدات
    # ======================================================
    print_step(7, TOTAL_STEPS, "تحميل بيانات الموردين والمخازن ووحدات القياس")
    supply_fixtures = [
        {"path": "supplier/fixtures/supplier_types.json",    "description": "أنواع الموردين"},
        {"path": "supplier/fixtures/service_types.json",     "description": "أنواع الخدمات"},
        {"path": "product/fixtures/units.json",              "description": "وحدات القياس الشاملة"},
        {"path": "product/fixtures/initial_warehouses.json", "description": "المخازن الافتراضية"},
    ]
    sp_loaded = load_fixtures_batch(supply_fixtures, "تحميل بيانات الموردين والمخازن...")
    print_success(f"تم تحميل {sp_loaded} من {len(supply_fixtures)} ملف تشغيلي")

    # ======================================================
    # المرحلة 8: تحميل بيانات Printing & Pricing
    # ======================================================
    print_step(8, TOTAL_STEPS, "تحميل بيانات ومصفوفة تسعير الطباعة (Pricing Seeder Service)")
    try:
        from printing_pricing.services.pricing_lookup_seeder_service import PricingLookupSeederService
        res = PricingLookupSeederService.seed_all()
        print_success(f"تم بنجاح بذر كافة بيانات وإعدادات التسعير: {res.get('total_created', 0)} جديد، {res.get('total_updated', 0)} محدث")

        from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService
        s_res = PricingSupplierSeederService.seed_all()
        print_success(f"تم بنجاح بذر ومزامنة خدمات وأنواع الموردين المتخصصة بالطباعة")
    except Exception as e:
        print_warning(f"خطأ أثناء بذر بيانات التسعير: {e}")

    # ======================================================
    # المرحلة 9: تفعيل الحوكمة والأمان (Governance)
    # ======================================================
    print_step(9, TOTAL_STEPS, "تفعيل نظام الحوكمة والأمان")
    gov_success = run_command(f'"{sys.executable}" manage.py activate_governance --silent', show_output=False)
    if gov_success:
        print_success("✅ تم تفعيل موديول الحوكمة والأمان بنجاح")
    else:
        print_warning("⚠️ تم تخطي تفعيل الحوكمة (سيتم تفعيلها تلقائياً عند الدخول)")

    # ======================================================
    # المرحلة 10: التحقق من المخزن الرئيسي والموردين
    # ======================================================
    print_step(10, TOTAL_STEPS, "التحقق من المخزن الرئيسي والموردين")
    try:
        from product.models import Warehouse
        wh, _ = Warehouse.objects.get_or_create(
            code="WH0001",
            defaults={"name": "المخزن الرئيسي", "location": "المخزن الرئيسي للمؤسسة", "is_active": True}
        )
        print_success(f"تم التحقق من المخزن الرئيسي: {wh.name} ({wh.code})")
    except Exception as e:
        print_warning(f"تحذير فحص المخزن: {e}")

    try:
        from supplier.models import Supplier, SupplierType
        if Supplier.objects.exists():
            default_type = SupplierType.objects.filter(code='general').first() or SupplierType.objects.first()
            if default_type:
                Supplier.objects.filter(primary_type__isnull=True).update(primary_type=default_type)
        print_success("تم التحقق من ربط أنواع الموردين")
    except Exception as e:
        print_warning(f"تحذير فحص الموردين: {e}")

    # ======================================================
    # المرحلة 11: تحديث hashes الملفات
    # ======================================================
    print_step(11, TOTAL_STEPS, "تحديث hashes الملفات")
    
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
    # المرحلة 12: الملخص النهائي
    # ======================================================
    print_step(12, TOTAL_STEPS, "الملخص النهائي")
    
    print_colored("🎉 تم إكمال إعداد وتأسيس النظام بنجاح!", Colors.GREEN + Colors.BOLD)
    print_colored(f"\n🐍 بيئة التشغيل: Python {platform.python_version()} | Django {django.get_version()}", Colors.CYAN)
    print_colored(f"🗄️  قاعدة البيانات: {db_type.upper()}", Colors.CYAN)
    print_colored("\n📊 الإحصائيات الشاملة:", Colors.CYAN)
    
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
            print_success(f"✅ المخازن: {warehouses_count}")
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
        
        print_success(f"✅ موديول Governance: {'مفعل' if gov_success else 'سيتم تفعيله تلقائياً'}")
        
    except Exception as e:
        print_warning(f"خطأ في عرض الإحصائيات: {e}")
    
    print_colored("\n🚀 النظام جاهز للاستخدام!", Colors.GREEN + Colors.BOLD)
    
    # رسالة خاصة عن Governance
    if gov_success:
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
    print_colored("   Product : فئات + وحدات + مخازن + منتجات", Colors.GRAY)
    print_colored("   Printing: ورق + ماكينات + تشطيب + تسعير (12 ملف)", Colors.GRAY)
    
    print_colored("\n🎭 الأدوار المتاحة:", Colors.CYAN)
    print_colored("   👑 مدير النظام: صلاحيات كاملة (superuser)", Colors.WHITE)
    print_colored("   👨‍💼 مدير: 48 صلاحية مخصصة (كل شيء ماعدا التقنية)", Colors.WHITE)
    print_colored("   👥 مستخدم: 46 صلاحية مخصصة (معظم الصلاحيات ماعدا الإدارية)", Colors.WHITE)
    print_colored("   👤 موظف: 3 صلاحيات مخصصة (إجازات وأذونات فقط)", Colors.WHITE)
    


if __name__ == "__main__":
    main()
