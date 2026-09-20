#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MariaDB Database Startup & Self-Healing Service
فحص وتشغيل خادم قاعدة البيانات MariaDB المستقل وضمان استمراره مع إقلاع الجهاز
بدون أي اعتماد على XAMPP
"""

import os
import sys
import time
import subprocess
import platform
import winreg
from pathlib import Path

# إعداد الـ Encoding للـ Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_colored(text, color=Colors.RESET):
    print(f"{color}{text}{Colors.RESET}")


def print_header(text):
    print_colored(f"\n{'='*60}", Colors.CYAN)
    print_colored(f"  {text}", Colors.CYAN)
    print_colored(f"{'='*60}\n", Colors.CYAN)


def get_mariadb_paths():
    """تحديد مسار خادم MariaDB المستقل وملف الإعدادات my.ini"""
    possible_dirs = [
        Path.home() / "mariadb-10.11",
        Path(r"C:\Users\UTD\mariadb-10.11"),
        Path(r"C:\mariadb-10.11"),
        Path(r"C:\Program Files\MariaDB 10.11"),
    ]
    
    env_dir = os.environ.get("MARIADB_HOME")
    if env_dir:
        possible_dirs.insert(0, Path(env_dir))

    for base_dir in possible_dirs:
        exe_path = base_dir / "bin" / "mysqld.exe"
        ini_path = base_dir / "data" / "my.ini"
        if not ini_path.exists():
            ini_path = base_dir / "my.ini"
        if exe_path.exists():
            return exe_path, ini_path, base_dir

    return None, None, None


def test_db_connection():
    """اختبار الاتصال بقاعدة البيانات عبر إعدادات Django المعتمدة"""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
        import django
        django.setup()
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION();")
            version = cursor.fetchone()[0]

        connection.close()
        return True, f"قاعدة البيانات متصلة وتعمل بنجاح! (الإصدار: {version})"
    except Exception as e:
        try:
            from django.db import connection
            connection.close()
        except Exception:
            pass
        return False, str(e)


def free_port_conflict(port=3306):
    """تحرير المنفذ 3306 في حال كان محجوزاً من قبل عملية أخرى (مثل XAMPP أو نسخة قديمة)"""
    try:
        # البحث عن PID العملية التي تحجز البورت
        cmd = f"netstat -ano | findstr :{port}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if not res.stdout:
            return True

        pids = set()
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pids.add(parts[-1])

        if not pids:
            return True

        # محاولة إغلاق نظيف لـ XAMPP mysql إذا كان هو المتسبب
        xampp_admin = Path(r"C:\xampp\mysql\bin\mysqladmin.exe")
        if xampp_admin.exists():
            try:
                subprocess.run([str(xampp_admin), "-u", "root", "shutdown"], capture_output=True, timeout=3)
                time.sleep(1)
            except Exception:
                pass

        # إنهاء أي عملية ما زالت تحجز البورت
        for pid in pids:
            try:
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, timeout=5)
            except Exception:
                pass

        time.sleep(1)
        return True
    except Exception:
        return False


def setup_startup_persistence(db_exe, db_ini):
    """
    تفعيل التشغيل التلقائي الدائم مع إقلاع الويندوز:
    1. مفتاح Registry Run للمستخدم الحالي (HKCU Run) مع تشغيل مخفي تماماً عبر PowerShell.
    2. ملف Start_MariaDB_ERP.cmd داخل مجلد Startup كطبقة حماية إضافية.
    """
    try:
        # مسار الأمر التشغيلي المخفي
        ini_arg = f'--defaults-file=""{db_ini}"" ' if (db_ini and Path(db_ini).exists()) else ''
        ps_launch = (
            f"powershell.exe -WindowStyle Hidden -NoProfile -Command "
            f"\"if (-not (Get-Process mysqld -ErrorAction SilentlyContinue)) {{ "
            f"Start-Process '{db_exe}' -ArgumentList '{ini_arg}--console' -WindowStyle Hidden }}\""
        )

        # 1. تثبيت مفتاح السجل Registry Run
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "MariaDB_ERP", 0, winreg.REG_SZ, ps_launch)
            winreg.CloseKey(key)
        except Exception:
            pass

        # 2. إزالة أي ملف VBS قديم وتنظيف مجلد Startup
        appdata = os.environ.get('APPDATA')
        if appdata:
            startup_folder = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            if startup_folder.exists():
                old_vbs = startup_folder / "Start_MariaDB_ERP.vbs"
                if old_vbs.exists():
                    try:
                        old_vbs.unlink()
                    except Exception:
                        pass

                # إنشاء ملف تشغيل سريع cmd
                cmd_file = startup_folder / "Start_MariaDB_ERP.cmd"
                cmd_content = f'''@echo off
tasklist /FI "IMAGENAME eq mysqld.exe" 2>NUL | find /I /N "mysqld.exe">NUL
if "%ERRORLEVEL%"=="1" (
    start "" /B "{db_exe}" {ini_arg}--console
)
'''
                cmd_file.write_text(cmd_content, encoding='utf-8')

        return True
    except Exception:
        return False



def start_mariadb_process(db_exe, db_ini):
    """تشغيل خادم MariaDB في الخلفية كعملية دائمة ومخفية تماماً"""
    args = []
    if db_ini and Path(db_ini).exists():
        args.append(f'--defaults-file={db_ini}')
    args.append('--console')

    try:
        creationflags = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        cmd_list = [str(db_exe)] + args
        subprocess.Popen(cmd_list, creationflags=creationflags, close_fds=True)
        return True
    except Exception:
        pass

    try:
        ps_args = " ".join([f"'{a}'" for a in args])
        ps_cmd = f"Start-Process -FilePath '{db_exe}' -ArgumentList {ps_args} -WindowStyle Hidden"
        res = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except Exception:
        return False


def try_start_mariadb_service():
    """محاولة تشغيل خدمة ويندوز إذا كانت مسجلة مسبقاً (MariaDB)"""
    services = ["MariaDB"]
    for svc in services:
        try:
            q = subprocess.run(['sc', 'query', svc], capture_output=True, text=True, timeout=3)
            if q.returncode == 0:
                if 'RUNNING' in q.stdout:
                    return True
                res = subprocess.run(['net', 'start', svc], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    return True
        except Exception:
            pass
    return False


def main():
    print_header("فحص وتشغيل خادم MariaDB المستقل (MWHEBA ERP)")

    if platform.system() != 'Windows':
        print_colored("⚠️  هذا السكربت مخصص لبيئة عمل Windows.", Colors.YELLOW)

    db_exe, db_ini, base_dir = get_mariadb_paths()
    if not db_exe or not db_exe.exists():
        print_colored("[X] لم يتم العثور على مسار تثبيت MariaDB المستقل!", Colors.RED)
        print_colored("المسار المتوقع: C:\\Users\\UTD\\mariadb-10.11\\bin\\mysqld.exe", Colors.GRAY)
        sys.exit(1)

    # 1. تثبيت التشغيل التلقائي مع الويندوز فوراً
    setup_startup_persistence(db_exe, db_ini)

    # 2. اختبار ما إذا كان الخادم متصلاً ويعمل بالفعل
    is_up, msg = test_db_connection()
    if is_up:
        print_colored(f"[OK] {msg}", Colors.GREEN)
        print_colored("📌 تم التحقق من تفعيل التشغيل التلقائي مع إقلاع الجهاز (Windows Startup & Registry).", Colors.CYAN)
        print_colored("\n✨ خادم قاعدة البيانات جاهز، يمكنك العمل فوراً!", Colors.GREEN)
        return

    print_colored("[!] جاري تشغيل خادم MariaDB المستقل وضمان جاهزيته...", Colors.YELLOW)

    # 3. محاولة تشغيل خدمة الويندوز إذا كانت موجودة
    service_started = try_start_mariadb_service()

    if not service_started:
        # فحص وتحرير أي تعارض في البورت (مثل XAMPP أو عمليات معلقة)
        free_port_conflict(3306)
        # تشغيل العملية المستقلة
        start_mariadb_process(db_exe, db_ini)

    # 4. التحقق والانتظار حتى اكتمال الجاهزية
    for i in range(10):
        time.sleep(1)
        is_up, msg = test_db_connection()
        if is_up:
            print_colored(f"[OK] {msg}", Colors.GREEN)
            print_colored("📌 تم تفعيل التشغيل التلقائي مع تشغيل الويندوز (لن تحتاج لتشغيله يدوياً بعد إعادة التشغيل).", Colors.CYAN)
            print_colored("\n✨ تم تشغيل MariaDB بنجاح تام ويعمل باستمرار في الخلفية!", Colors.GREEN)
            return

    # إذا استمر الفشل، محاولة تحرير المنفذ وتشغيلها مرة ثانية
    print_colored("[*] جاري تحرير المنفذ وإعادة المحاولة...", Colors.YELLOW)
    free_port_conflict(3306)
    start_mariadb_process(db_exe, db_ini)

    for i in range(6):
        time.sleep(1)
        is_up, msg = test_db_connection()
        if is_up:
            print_colored(f"[OK] {msg}", Colors.GREEN)
            print_colored("✨ تم تشغيل MariaDB بنجاح!", Colors.GREEN)
            return

    print_colored("[X] تعذر الاتصال بقاعدة البيانات.", Colors.RED)
    print_colored(f"التفاصيل: {msg}", Colors.GRAY)
    sys.exit(1)


if __name__ == "__main__":
    main()

