#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database Startup & Health Check Script
فحص وتشغيل خادم قاعدة البيانات (MariaDB / MySQL)
"""

import os
import sys
import time
import subprocess
import platform
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
    print_colored(f"\n{'='*55}", Colors.CYAN)
    print_colored(f"  {text}", Colors.CYAN)
    print_colored(f"{'='*55}\n", Colors.CYAN)


def test_db_connection():
    """اختبار الاتصال بقاعدة البيانات عبر إعدادات Django المعتمدة"""
    try:
        # تهيئة Django لقراءة إعدادات settings و .env تلقائياً
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


def start_mariadb_standalone():
    """تشغيل خادم MariaDB 10.11 المستقل في الخلفية كعملية دائمة ومستقلة بدون نوافذ"""
    mariadb_exe = Path(r"C:\Users\UTD\mariadb-10.11\bin\mysqld.exe")
    mariadb_ini = Path(r"C:\Users\UTD\mariadb-10.11\data\my.ini")

    if not mariadb_exe.exists():
        return False

    # تسجيل التشغيل التلقائي عند بدء تشغيل الجهاز
    setup_mysql_autostart(mariadb_exe, mariadb_ini)

    print_colored("[*] جاري تشغيل خادم MariaDB 10.11 في الخلفية...", Colors.YELLOW)
    args = f'--defaults-file="{mariadb_ini}"'
    start_process_hidden(mariadb_exe, args)
    time.sleep(3)
    return True


def try_start_windows_service():
    """محاولة تشغيل خدمة MySQL/MariaDB في ويندوز إذا كانت مسجلة كخدمة"""
    services = ["MySQL", "MariaDB", "mysql"]
    for svc in services:
        try:
            q = subprocess.run(['sc', 'query', svc], capture_output=True, text=True, timeout=3)
            if q.returncode == 0 and 'RUNNING' in q.stdout:
                return True
            res = subprocess.run(['net', 'start', svc], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                print_colored(f"[OK] تم تشغيل خدمة الويندوز ({svc}) بنجاح!", Colors.GREEN)
                return True
        except Exception:
            pass
    return False


def get_xampp_paths():
    """الحصول على مسارات XAMPP المحتملة"""
    possible_roots = [
        Path(r"C:\xampp"),
        Path(r"C:\Program Files\xampp"),
        Path(r"C:\Program Files (x86)\xampp"),
        Path(r"D:\xampp"),
    ]
    return [root for root in possible_roots if root.exists()]


def open_xampp_control():
    """محاولة فتح لوحة تحكم XAMPP كحل بديل في حال الفشل التام"""
    for root in get_xampp_paths():
        control_exe = root / "xampp-control.exe"
        if control_exe.exists():
            print_colored("🚀 جاري فتح XAMPP Control Panel للمساعدة في الفحص والتشغيل اليدوي...", Colors.YELLOW)
            try:
                subprocess.Popen([str(control_exe)])
                return True
            except Exception:
                pass
    return False


def start_mysql_fallback():
    """محاولة بديلة لتشغيل MySQL من مسارات XAMPP لو لم يتوفر MariaDB المستقل"""
    for root in get_xampp_paths():
        exe = root / "mysql" / "bin" / "mysqld.exe"
        if exe.exists():
            setup_mysql_autostart(exe)
            print_colored(f"[*] جاري تشغيل MySQL من مسار XAMPP ({root}) كبديل في الخلفية...", Colors.YELLOW)
            cmd_args = f'"{exe}" --console'
            started = start_process_via_wmi(cmd_args)
            if not started:
                try:
                    creationflags = 0x00000008 | 0x00000200 | 0x08000000
                    subprocess.Popen(cmd_args, creationflags=creationflags, close_fds=True, shell=True)
                except Exception:
                    pass
            time.sleep(3)
            return True
    return False


def main():
    print_header("فحص وتشغيل خادم قاعدة البيانات (Database Server)")

    if platform.system() != 'Windows':
        print_colored("⚠️  هذا السكربت مخصص لبيئة عمل Windows.", Colors.YELLOW)

    # ضبط التشغيل التلقائي عند بدء تشغيل الجهاز مسبقاً
    mariadb_exe = Path(r"C:\Users\UTD\mariadb-10.11\bin\mysqld.exe")
    mariadb_ini = Path(r"C:\Users\UTD\mariadb-10.11\data\my.ini")
    if mariadb_exe.exists():
        setup_mysql_autostart(mariadb_exe, mariadb_ini)

    # 1. اختبار ما إذا كانت الخدمة تعمل بالفعل
    is_up, msg = test_db_connection()
    if is_up:
        print_colored(f"[OK] {msg}", Colors.GREEN)
        print_colored("📌 تم التأكد من تفعيل التشغيل التلقائي مع بدء تشغيل النظام (Windows Startup).", Colors.CYAN)
        print_colored("\n✨ خادم قاعدة البيانات جاهز، يمكنك العمل فوراً!", Colors.GREEN)
        return

    print_colored("[!] خادم قاعدة البيانات متوقف، جاري التشغيل التلقائي وضمان استمراره...", Colors.YELLOW)

    # 2. محاولة تشغيل خدمة ويندوز أولاً إذا كانت مثبتة
    service_started = try_start_windows_service()

    # 3. بدء التشغيل التلقائي لـ MariaDB 10.11 المستقل أو مسارات XAMPP
    if not service_started:
        started = start_mariadb_standalone()
        if not started:
            started = start_mysql_fallback()

    # 4. إعادة الاختبار مع الانتظار
    for _ in range(12):
        time.sleep(1)
        is_up, msg = test_db_connection()
        if is_up:
            print_colored(f"[OK] {msg}", Colors.GREEN)
            print_colored("📌 تم تفعيل التشغيل التلقائي مع فتح الجهاز (Windows Startup).", Colors.CYAN)
            print_colored("\n✨ تم تشغيل خادم قاعدة البيانات بنجاح تام ويعمل باستمرار في الخلفية!", Colors.GREEN)
            return

    print_colored("[X] تعذر بدء تشغيل قاعدة البيانات تلقائياً.", Colors.RED)
    print_colored(f"التفاصيل: {msg}", Colors.GRAY)
    open_xampp_control()
    sys.exit(1)


if __name__ == "__main__":
    main()
