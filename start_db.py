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

        return True, f"قاعدة البيانات متصلة وتعمل بنجاح! (الإصدار: {version})"
    except Exception as e:
        return False, str(e)


def start_mariadb_standalone():
    """تشغيل خادم MariaDB 10.11 المستقل في الخلفية"""
    mariadb_exe = Path(r"C:\Users\UTD\mariadb-10.11\bin\mysqld.exe")
    mariadb_ini = Path(r"C:\Users\UTD\mariadb-10.11\data\my.ini")

    if not mariadb_exe.exists():
        return False

    print_colored("[*] جاري تشغيل خادم MariaDB 10.11...", Colors.YELLOW)
    try:
        subprocess.Popen(
            [str(mariadb_exe), f"--defaults-file={mariadb_ini}", "--console"],
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
        )
        time.sleep(3)
        return True
    except Exception as e:
        print_colored(f"[X] فشل تشغيل MariaDB: {e}", Colors.RED)
        return False


def start_mysql_fallback():
    """محاولة بديلة لتشغيل MySQL من XAMPP لو لم يتوفر MariaDB المستقل"""
    xampp_paths = [
        Path(r"C:\xampp\mysql\bin\mysqld.exe"),
        Path(r"D:\xampp\mysql\bin\mysqld.exe"),
    ]
    for exe in xampp_paths:
        if exe.exists():
            print_colored("[*] جاري تشغيل MySQL من مسار XAMPP كبديل...", Colors.YELLOW)
            try:
                subprocess.Popen([str(exe), "--console"], creationflags=subprocess.CREATE_NO_WINDOW)
                time.sleep(3)
                return True
            except Exception:
                pass
    return False


def main():
    print_header("فحص وتشغيل خادم قاعدة البيانات (Database Server)")

    # 1. اختبار ما إذا كانت الخدمة تعمل بالفعل
    is_up, msg = test_db_connection()
    if is_up:
        print_colored(f"[OK] {msg}", Colors.GREEN)
        print_colored("\n✨ خادم قاعدة البيانات جاهز، يمكنك العمل فوراً!", Colors.GREEN)
        return

    print_colored("[!] خادم قاعدة البيانات متوقف، جاري التشغيل التلقائي...", Colors.YELLOW)

    # 2. بدء التشغيل التلقائي لـ MariaDB 10.11
    started = start_mariadb_standalone()
    if not started:
        started = start_mysql_fallback()

    # 3. إعادة الاختبار
    time.sleep(2)
    is_up, msg = test_db_connection()
    if is_up:
        print_colored(f"[OK] {msg}", Colors.GREEN)
        print_colored("\n✨ تم تشغيل خادم قاعدة البيانات بنجاح تام!", Colors.GREEN)
    else:
        print_colored("[X] تعذر بدء تشغيل قاعدة البيانات تلقائياً.", Colors.RED)
        print_colored(f"التفاصيل: {msg}", Colors.GRAY)
        sys.exit(1)


if __name__ == "__main__":
    main()
