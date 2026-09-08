#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XAMPP & MySQL Startup Script
سكربت تشغيل XAMPP و MySQL
"""

import os
import sys
import time
import subprocess
import platform
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_colored(text, color=Colors.RESET):
    """Print colored text to terminal"""
    print(f"{color}{text}{Colors.RESET}")


def print_header(text):
    """Print section header"""
    print_colored(f"\n{'='*50}", Colors.CYAN)
    print_colored(f"  {text}", Colors.CYAN)
    print_colored(f"{'='*50}\n", Colors.CYAN)


def find_xampp_path():
    """Find XAMPP installation path"""
    possible_paths = [
        r"C:\xampp",
        r"C:\Program Files\xampp",
        r"C:\Program Files (x86)\xampp",
        r"D:\xampp",
    ]
    
    for path in possible_paths:
        if Path(path).exists():
            return path
    
    return None


def check_service_status(service_name):
    """Check if Windows service is running"""
    try:
        result = subprocess.run(
            ['sc', 'query', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        return 'RUNNING' in result.stdout
    except:
        return False


def start_service(service_name, display_name):
    """Start Windows service"""
    print_colored(f"🔄 جاري تشغيل {display_name}...", Colors.YELLOW)
    
    if check_service_status(service_name):
        print_colored(f"✓ {display_name} يعمل بالفعل", Colors.GREEN)
        return True
    
    try:
        result = subprocess.run(
            ['net', 'start', service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print_colored(f"✓ تم تشغيل {display_name} بنجاح", Colors.GREEN)
            return True
        else:
            print_colored(f"⚠️  {display_name} ليس مثبت كخدمة", Colors.YELLOW)
            return False
    except Exception as e:
        print_colored(f"❌ خطأ في تشغيل {display_name}: {str(e)}", Colors.RED)
        return False


def start_mysql_direct(xampp_path):
    """Start MySQL / MariaDB directly"""
    mariadb_standalone = Path(r"C:\Users\UTD\mariadb-10.11\bin\mysqld.exe")
    mariadb_ini = Path(r"C:\Users\UTD\mariadb-10.11\data\my.ini")
    
    if mariadb_standalone.exists():
        mysql_exe = mariadb_standalone
        args = [str(mysql_exe), f"--defaults-file={mariadb_ini}"]
    else:
        mysql_exe = Path(xampp_path) / "mysql" / "bin" / "mysqld.exe"
        args = [str(mysql_exe), "--console"]
    
    if not mysql_exe.exists():
        print_colored("❌ لم يتم العثور على MySQL / MariaDB", Colors.RED)
        return False
    
    try:
        print_colored("🔧 محاولة تشغيل MySQL/MariaDB مباشرة...", Colors.YELLOW)
        subprocess.Popen(
            args,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(3)
        print_colored("✓ تم تشغيل MySQL/MariaDB مباشرة", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"❌ فشل تشغيل MySQL: {str(e)}", Colors.RED)
        return False


def start_apache_direct(xampp_path):
    """Start Apache directly from XAMPP"""
    apache_exe = Path(xampp_path) / "apache" / "bin" / "httpd.exe"
    
    if not apache_exe.exists():
        print_colored("❌ لم يتم العثور على Apache", Colors.RED)
        return False
    
    try:
        print_colored("🔧 محاولة تشغيل Apache مباشرة...", Colors.YELLOW)
        subprocess.Popen(
            [str(apache_exe)],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(2)
        print_colored("✓ تم تشغيل Apache مباشرة", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"❌ فشل تشغيل Apache: {str(e)}", Colors.RED)
        return False


def open_xampp_control(xampp_path):
    """Open XAMPP Control Panel"""
    control_exe = Path(xampp_path) / "xampp-control.exe"
    
    if not control_exe.exists():
        print_colored("❌ لم يتم العثور على XAMPP Control Panel", Colors.RED)
        return False
    
    try:
        print_colored("🚀 جاري فتح XAMPP Control Panel...", Colors.YELLOW)
        subprocess.Popen([str(control_exe)])
        print_colored("✓ تم فتح XAMPP Control Panel", Colors.GREEN)
        return True
    except Exception as e:
        print_colored(f"❌ خطأ في فتح Control Panel: {str(e)}", Colors.RED)
        return False


def test_mysql_connection(xampp_path):
    """Test MySQL connection"""
    mysql_client = Path(xampp_path) / "mysql" / "bin" / "mysql.exe"
    
    if not mysql_client.exists():
        print_colored("⚠️  تعذر العثور على MySQL client", Colors.YELLOW)
        return False
    
    try:
        print_colored("🔍 اختبار الاتصال بـ MySQL...", Colors.YELLOW)
        result = subprocess.run(
            [str(mysql_client), "-u", "root", "-e", "SELECT 1;"],
            capture_output=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print_colored("✓ MySQL يعمل بشكل صحيح!", Colors.GREEN)
            print_colored("✓ يمكنك الآن تشغيل: python manage.py migrate", Colors.GREEN)
            return True
        else:
            print_colored("⚠️  MySQL يعمل لكن قد تحتاج لضبط كلمة المرور", Colors.YELLOW)
            return False
    except Exception as e:
        print_colored("⚠️  تعذر الاتصال بـ MySQL", Colors.YELLOW)
        print_colored("   تحقق من XAMPP Control Panel", Colors.YELLOW)
        return False


def run_django_migrate():
    """Run Django migrations"""
    try:
        print_colored("\n🐍 جاري تشغيل Django migrations...", Colors.CYAN)
        result = subprocess.run(
            [sys.executable, "manage.py", "migrate"],
            capture_output=False
        )
        return result.returncode == 0
    except Exception as e:
        print_colored(f"❌ خطأ في تشغيل migrations: {str(e)}", Colors.RED)
        return False


def main():
    """Main function"""
    # Check if running on Windows
    if platform.system() != 'Windows':
        print_colored("❌ هذا السكربت يعمل على Windows فقط", Colors.RED)
        sys.exit(1)
    
    print_header("تشغيل MySQL")
    
    # Find XAMPP
    xampp_path = find_xampp_path()
    
    if not xampp_path:
        print_colored("❌ لم يتم العثور على XAMPP", Colors.RED)
        sys.exit(1)
    
    print_colored(f"📁 مسار XAMPP: {xampp_path}", Colors.GRAY)
    
    # Start MySQL
    mysql_started = start_service("MySQL", "MySQL")
    
    if not mysql_started:
        mysql_started = start_mysql_direct(xampp_path)
    
    # Test MySQL connection
    time.sleep(2)
    test_mysql_connection(xampp_path)
    
    print_colored("\n✓ تم بنجاح!", Colors.GREEN)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  تم إيقاف السكربت", Colors.YELLOW)
        sys.exit(0)
    except Exception as e:
        print_colored(f"\n❌ خطأ غير متوقع: {str(e)}", Colors.RED)
        sys.exit(1)
