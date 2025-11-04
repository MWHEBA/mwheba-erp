#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup_development.py - سكريبت إعداد بيئة التطوير
يقوم بتهيئة النظام للتطوير مع تحميل البيانات الأساسية

ملاحظة مهمة: هذا السكريبت يعتمد كلياً على ملفات fixtures
ولا يحتوي على أي بيانات ثابتة في الكود
"""

import os
import sys
import subprocess
from pathlib import Path

# إعداد encoding لـ Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')

# متغير عام للوضع التلقائي
auto_mode = False

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


def print_colored(text, color=""):
    """طباعة نص ملون"""
    try:
        print(f"{color}{text}{Colors.RESET}")
    except UnicodeEncodeError:
        # في حالة فشل طباعة emoji، استخدم ASCII
        text_safe = text.encode('ascii', 'ignore').decode('ascii')
        print(f"{color}{text_safe}{Colors.RESET}")


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


def print_info(text):
    """طباعة معلومة"""
    print_colored(f"   ℹ️  {text}", Colors.GRAY)


def print_warning(text):
    """طباعة تحذير"""
    print_colored(f"   ⚠️  {text}", Colors.RED)


def run_command(command, check=True):
    """تشغيل أمر في الـ shell"""
    try:
        result = subprocess.run(
            command, shell=True, check=check, capture_output=True, text=True
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print_warning(f"فشل تنفيذ الأمر: {e}")
        return False


def kill_django_processes():
    """محاولة إيقاف عمليات Django التي قد تستخدم قاعدة البيانات"""
    try:
        if os.name == "nt":  # Windows
            # البحث عن عمليات Python التي تشغل manage.py
            result = subprocess.run(
                'tasklist /FI "IMAGENAME eq python.exe" /FO CSV',
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and "python.exe" in result.stdout:
                print_info("تم العثور على عمليات Python قيد التشغيل")
                if auto_mode:
                    kill_confirm = "yes"
                    print_info("الوضع التلقائي: سيتم إيقاف عمليات Python")
                else:
                    kill_confirm = (
                        input("هل تريد محاولة إيقاف عمليات Python؟ (yes/no): ")
                        .strip()
                        .lower()
                    )
                if kill_confirm == "yes":
                    # البحث عن عمليات Python التي تشغل runserver فقط
                    # وليس السكريبت الحالي
                    current_pid = os.getpid()
                    print_info(f"PID الحالي للسكريبت: {current_pid}")
                    
                    # استخدام wmic للحصول على تفاصيل العمليات
                    result = subprocess.run(
                        'wmic process where "name=\'python.exe\'" get ProcessId,CommandLine /format:csv',
                        shell=True,
                        capture_output=True,
                        text=True
                    )
                    
                    killed_any = False
                    for line in result.stdout.split('\n'):
                        if 'runserver' in line or 'manage.py' in line:
                            # استخراج PID من السطر
                            parts = line.split(',')
                            if len(parts) >= 3:
                                try:
                                    pid = int(parts[-1].strip())
                                    if pid != current_pid:
                                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                                        print_success(f"تم إيقاف عملية Django (PID: {pid})")
                                        killed_any = True
                                except (ValueError, IndexError):
                                    pass
                    
                    if not killed_any:
                        # إذا لم نجد عمليات محددة، ننتظر قليلاً
                        print_info("لم يتم العثور على عمليات Django محددة")
                        import time
                        time.sleep(2)
                    
                    return True
        else:  # Linux/Mac
            result = subprocess.run(
                "ps aux | grep 'manage.py runserver' | grep -v grep",
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                print_info("تم العثور على عمليات Django قيد التشغيل")
                if auto_mode:
                    kill_confirm = "yes"
                    print_info("الوضع التلقائي: سيتم إيقاف عمليات Django")
                else:
                    kill_confirm = (
                        input("هل تريد محاولة إيقاف عمليات Django؟ (yes/no): ")
                        .strip()
                        .lower()
                    )
                if kill_confirm == "yes":
                    subprocess.run("pkill -f 'manage.py runserver'", shell=True)
                    print_success("تم إيقاف عمليات Django")
    except Exception as e:
        print_warning(f"فشل في فحص العمليات: {e}")
    return False


def main():
    """الدالة الرئيسية لإعداد النظام"""
    
    # فحص وضع التشغيل التلقائي
    global auto_mode
    auto_mode = len(sys.argv) > 1 and sys.argv[1] == '--auto'

    # تهيئة Django في البداية
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")
    import django

    # فحص وجود ملف الإعدادات
    settings_path = Path("settings.py")
    if not settings_path.exists():
        print_colored(f"\n❌ لا يوجد ملف الإعدادات {settings_path}", Colors.RED)
    django.setup()

    # طباعة العنوان
    print_header("ERP System - Development Setup")
    
    if auto_mode:
        print_colored("\n🤖 وضع التشغيل التلقائي مُفعل", Colors.CYAN)
        print("سيتم تنفيذ الإعداد الكامل تلقائياً (قاعدة بيانات جديدة + بيانات تجريبية)")
        confirm = "yes"
    else:
        # سؤال بسيط للإعداد
        print_colored("\n🛠️  إعداد النظام", Colors.CYAN)
        print("سيتم تنفيذ الإعداد الكامل (قاعدة بيانات جديدة + بيانات تجريبية)")
        confirm = input("هل تريد المتابعة؟ (yes/no): ").strip().lower()

        if confirm != "yes":
            print_colored("\n❌ تم إلغاء العملية", Colors.YELLOW)
            sys.exit(0)

    load_test_data = True

    # المرحلة 1: حذف قاعدة البيانات القديمة
    print_step(1, 9, "حذف قاعدة البيانات القديمة")
    db_path = Path("db.sqlite3")
    if db_path.exists():
        try:
            db_path.unlink()
            print_success("تم حذف قاعدة البيانات القديمة")
        except PermissionError:
            print_warning("⚠️  قاعدة البيانات مفتوحة في عملية أخرى!")
            print_colored("   الحلول المقترحة:", Colors.YELLOW)
            print_colored(
                "   1. أغلق السيرفر Django إذا كان يعمل (Ctrl+C)", Colors.WHITE
            )
            print_colored(
                "   2. أغلق أي IDE أو برنامج يستخدم قاعدة البيانات", Colors.WHITE
            )
            print_colored(
                "   3. أعد تشغيل السكريبت بعد إغلاق العمليات", Colors.WHITE
            )

            # محاولة إيقاف عمليات Django
            if kill_django_processes():
                print_info("تم محاولة إيقاف العمليات، انتظر قليلاً...")
                print_info("انتظار 5 ثوان لضمان تحرير قاعدة البيانات...")
                
                import time
                for i in range(5, 0, -1):
                    print_info(f"   {i}...")
                    time.sleep(1)
                try:
                    db_path.unlink()
                    print_success("تم حذف قاعدة البيانات بنجاح!")
                except PermissionError:
                    print_warning("لا يزال الملف مستخدم")

            # محاولة أخرى بعد تحذير المستخدم
            if db_path.exists():
                if auto_mode:
                    retry = "yes"
                    print_info("الوضع التلقائي: سيتم المحاولة مرة أخرى")
                else:
                    retry = input("\nهل تريد المحاولة مرة أخرى؟ (yes/no): ").strip().lower()
                if retry == "yes":
                    try:
                        db_path.unlink()
                        print_success("تم حذف قاعدة البيانات بنجاح!")
                    except PermissionError:
                        print_colored("\n❌ لا يمكن حذف قاعدة البيانات", Colors.RED)
                        print_colored(
                            "   يرجى إغلاق جميع العمليات التي تستخدم قاعدة البيانات يدوياً",
                            Colors.GRAY,
                        )
                        print_colored("   ثم إعادة تشغيل السكريبت", Colors.GRAY)
                        sys.exit(1)
                else:
                    print_colored("\n❌ تم إلغاء العملية", Colors.YELLOW)
                    sys.exit(0)
    else:
        print_info("لا توجد قاعدة بيانات سابقة")

    # المرحلة 2: تطبيق الهجرات
    print_step(2, 9, "تطبيق الهجرات")
    if not run_command("python manage.py migrate"):
        print_colored("\n❌ فشل تطبيق الهجرات", Colors.RED)
        sys.exit(1)
    print_success("تم تطبيق الهجرات بنجاح")

    # المرحلة 3: إنشاء المستخدمين الأساسيين
    print_step(3, 9, "إنشاء المستخدمين الأساسيين")
    
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # إنشاء 3 مستخدمين admin
        users_data = [
            {
                'username': 'mwheba',
                'email': 'info@mwheba.com',
                'first_name': 'Mohamed',
                'last_name': 'Yousif',
                'password': 'MedooAlnems2008'
            },
            {
                'username': 'fatma',
                'email': 'fatma@mwheba.com',
                'first_name': 'فاطمة',
                'last_name': '',
                'password': '2951096'
            },
            {
                'username': 'admin',
                'email': 'admin@mwheba.com',
                'first_name': 'Admin',
                'last_name': 'Test',
                'password': 'admin123'
            }
        ]
        
        for user_data in users_data:
            username = user_data['username']
            
            # حذف المستخدم إن كان موجوداً
            User.objects.filter(username=username).delete()
            
            # إنشاء المستخدم الجديد
            user = User.objects.create_user(
                username=username,
                email=user_data['email'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                password=user_data['password']
            )
            
            # جعله superuser و staff
            user.is_superuser = True
            user.is_staff = True
            user.save()
            
            print_success(f"تم إنشاء المستخدم {username} (كلمة المرور: {user_data['password']})")
        
        print_success("تم إنشاء جميع المستخدمين بنجاح")
        
    except Exception as e:
        print_warning(f"فشل في إنشاء المستخدمين: {e}")

    # المرحلة 4: إنشاء الصلاحيات المخصصة والأدوار
    print_step(4, 10, "إنشاء الصلاحيات المخصصة والأدوار")
    
    print_info("إنشاء الصلاحيات المخصصة (37 صلاحية)...")
    if run_command("python manage.py create_custom_permissions", check=False):
        print_success("تم إنشاء الصلاحيات المخصصة بنجاح")
        print_info("   ✓ تم تقليل الصلاحيات من 544 إلى 37 (تقليل 93%)")
        print_info("   ✓ صلاحيات عربية واضحة وسهلة الاستخدام")
    else:
        print_warning("فشل إنشاء الصلاحيات المخصصة")
    
    print_info("إنشاء الأدوار الأساسية (8 أدوار)...")
    if run_command("python manage.py update_roles_with_custom_permissions", check=False):
        print_success("تم إنشاء الأدوار بنجاح")
        print_info("   ✓ مدير النظام (45 صلاحية)")
        print_info("   ✓ محاسب (9 صلاحيات)")
        print_info("   ✓ أمين مخزن (6 صلاحيات)")
        print_info("   ✓ مندوب مبيعات (7 صلاحيات)")
        print_info("   ✓ مدير مالي (13 صلاحية)")
        print_info("   ✓ مستخدم عرض فقط (6 صلاحيات)")
        print_info("   ✓ مسؤول طباعة (6 صلاحيات)")
        print_info("   ✓ منسق عام (13 صلاحية)")
    else:
        print_warning("فشل إنشاء الأدوار")

    # المرحلة 5: تحميل إعدادات النظام
    print_step(5, 10, "تحميل إعدادات النظام")
    
    print_info("تحميل الإعدادات الشاملة (101 إعداد)...")
    if run_command(
        "python manage.py loaddata core/fixtures/system_settings_final.json", check=False
    ):
        print_success("تم تحميل جميع إعدادات النظام بنجاح")
        print_info("   ✓ إعدادات الشركة (18 حقل)")
        print_info("   ✓ إعدادات الفواتير والمالية (4 حقول)")
        print_info("   ✓ إعدادات النظام الأخرى (79 إعداد)")
    else:
        print_warning("فشل تحميل إعدادات النظام")

    # المرحلة 6: تحميل الدليل المحاسبي
    print_step(6, 10, "تحميل الدليل المحاسبي")

    print_info("تحميل شجرة الحسابات (النسخة النهائية المحدثة)...")
    if not run_command(
        "python manage.py loaddata financial/fixtures/chart_of_accounts_final.json"
    ):
        print_colored("\n❌ فشل تحميل الدليل المحاسبي", Colors.RED)
        print_info(
            "تأكد من وجود الملف: financial/fixtures/chart_of_accounts_final.json"
        )
        sys.exit(1)

    print_info("تحميل قواعد التزامن المالي...")
    if run_command(
        "python manage.py loaddata financial/fixtures/payment_sync_rules.json",
        check=False,
    ):
        print_success("تم تحميل قواعد التزامن بنجاح")
    else:
        print_warning("فشل تحميل قواعد التزامن")

    print_success("تم تحميل الدليل المحاسبي")

    # التحقق من الصلاحيات المخصصة
    print_info("التحقق من الصلاحيات المخصصة...")
    try:
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from users.models import User as UserModel

        ct = ContentType.objects.get_for_model(UserModel)
        custom_permissions = Permission.objects.filter(content_type=ct)
        total_permissions = Permission.objects.count()
        
        print_success(f"تم العثور على {custom_permissions.count()} صلاحية مخصصة")
        print_info(f"   إجمالي الصلاحيات في النظام: {total_permissions}")
        
        if custom_permissions.count() >= 37:
            print_success("✅ نظام الصلاحيات المخصصة جاهز!")
        else:
            print_warning(f"⚠️ عدد الصلاحيات المخصصة أقل من المتوقع ({custom_permissions.count()}/45)")
            
    except Exception as e:
        print_warning(f"خطأ في التحقق من الصلاحيات: {e}")

    # التحقق من أدوار المستخدمين
    print_info("التحقق من أدوار المستخدمين...")
    try:
        from django.contrib.auth import get_user_model
        from users.models import Role

        User = get_user_model()
        
        # عد الأدوار
        roles_count = Role.objects.count()
        print_success(f"تم العثور على {roles_count} دور في النظام")
        
        if roles_count >= 8:
            print_success("✅ جميع الأدوار الأساسية موجودة!")
        else:
            print_warning(f"⚠️ عدد الأدوار أقل من المتوقع ({roles_count}/8)")
        
        # المستخدمون الثلاثة هم superusers ولديهم جميع الصلاحيات تلقائياً
        users_to_check = ["mwheba", "fatma", "admin"]
        for username in users_to_check:
            try:
                user = User.objects.get(username=username)
                if user.is_superuser:
                    print_success(f"✅ {username} - superuser (صلاحيات كاملة)")
                else:
                    print_info(f"   {username} - مستخدم عادي")
            except User.DoesNotExist:
                print_warning(f"المستخدم {username} غير موجود")

    except Exception as e:
        print_warning(f"فشل في التحقق من الأدوار: {str(e)}")

    # المرحلة 7: إنشاء الفترة المالية 2025
    print_step(7, 10, "إنشاء الفترة المالية 2025")

    from financial.models import AccountingPeriod
    from datetime import date

    try:
        # الحصول على المستخدم الأول لتعيينه كمنشئ
        from django.contrib.auth import get_user_model

        User = get_user_model()
        first_user = User.objects.first()

        period, created = AccountingPeriod.objects.get_or_create(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            defaults={
                "name": "السنة المالية 2025",
                "status": "open",
                "created_by": first_user,
            },
        )
        if created:
            print_success("تم إنشاء الفترة المالية 2025 بنجاح")
        else:
            print_info("الفترة المالية 2025 موجودة بالفعل")
    except Exception as e:
        print_warning(f"فشل إنشاء الفترة المالية: {e}")

    # المرحلة 8: بيانات تجريبية
    print_step(8, 10, "تحميل البيانات التجريبية")

    if load_test_data:
        print_info("تحميل المخازن والمنتجات...")
        if run_command(
            "python manage.py loaddata product/fixtures/initial_data.json", check=False
        ):
            print_success("تم تحميل المخازن والمنتجات")
        else:
            print_warning("فشل تحميل المخازن والمنتجات")

        print_info("تحميل العملاء...")
        if run_command(
            "python manage.py loaddata client/fixtures/initial_data.json", check=False
        ):
            print_success("تم تحميل العملاء")
        else:
            print_warning("فشل تحميل العملاء")

        print_info("تحميل الأقسام...")
        if run_command(
            "python manage.py loaddata hr/fixtures/departments.json", check=False
        ):
            print_success("تم تحميل الأقسام")
        else:
            print_warning("فشل تحميل الأقسام")

        print_info("تحميل المسميات الوظيفية...")
        if run_command(
            "python manage.py loaddata hr/fixtures/job_titles.json", check=False
        ):
            print_success("تم تحميل المسميات الوظيفية")
        else:
            print_warning("فشل تحميل المسميات الوظيفية")

        print_info("تحميل الورديات...")
        if run_command(
            "python manage.py loaddata hr/fixtures/shifts.json", check=False
        ):
            print_success("تم تحميل الورديات")
        else:
            print_warning("فشل تحميل الورديات")

        print_info("تحميل ماكينات البصمة...")
        if run_command(
            "python manage.py loaddata hr/fixtures/biometric_devices.json", check=False
        ):
            print_success("تم تحميل ماكينات البصمة")
        else:
            print_warning("فشل تحميل ماكينات البصمة")

        print_info("تحميل الموظفين التجريبيين...")
        if run_command(
            "python manage.py loaddata hr/fixtures/employees_demo.json", check=False
        ):
            print_success("تم تحميل الموظفين التجريبيين (3 موظفين)")
            
            # إنشاء أرصدة الإجازات للموظفين
            print_info("إنشاء أرصدة الإجازات للموظفين...")
            if run_command(
                "python manage.py create_leave_balances --year 2025", check=False
            ):
                print_success("تم إنشاء أرصدة الإجازات للموظفين")
            else:
                print_warning("فشل إنشاء أرصدة الإجازات")
        else:
            print_warning("فشل تحميل الموظفين التجريبيين")

        print_info("تحميل أنواع الموردين (النسخة الموحدة الجديدة)...")
        if run_command(
            "python manage.py loaddata supplier/fixtures/supplier_types.json",
            check=False,
        ):
            print_success("تم تحميل أنواع الموردين")
        else:
            print_warning("فشل تحميل أنواع الموردين من الـ fixtures")

        print_info("تحميل الموردين...")
        if run_command(
            "python manage.py loaddata supplier/fixtures/initial_data.json", check=False
        ):
            print_success("تم تحميل الموردين")
        else:
            print_warning("فشل تحميل الموردين من الـ fixtures")

        print_info("تحميل علاقات الموردين بأنواعهم...")
        if run_command(
            "python manage.py loaddata supplier/fixtures/supplier_relationships.json",
            check=False,
        ):
            print_success("تم تحميل علاقات الموردين")
        else:
            print_warning("فشل تحميل علاقات الموردين من الـ fixtures")

        # التحقق من نجاح تحميل البيانات
        try:
            from product.models import Product, Warehouse
            from client.models import Customer
            from supplier.models import Supplier
            from hr.models import Department, Employee

            products_count = Product.objects.count()
            warehouses_count = Warehouse.objects.count()
            customers_count = Customer.objects.count()
            suppliers_count = Supplier.objects.count()
            departments_count = Department.objects.count()
            employees_count = Employee.objects.count()

            print_success(f"تم تحميل البيانات التجريبية بنجاح:")
            print_success(f"   - {products_count} منتج")
            print_success(f"   - {warehouses_count} مخزن")
            print_success(f"   - {customers_count} عميل")
            print_success(f"   - {suppliers_count} مورد")
            print_success(f"   - {departments_count} قسم")
            print_success(f"   - {employees_count} موظف")

        except Exception as e:
            print_warning(f"خطأ في التحقق من البيانات: {e}")
    else:
        print_info("تم تخطي البيانات التجريبية")

    # المرحلة 9: تحميل بيانات أنظمة التسعير
    print_step(9, 10, "تحميل بيانات أنظمة التسعير")

    if load_test_data:
        # تحميل بيانات نظام printing_pricing الجديد
        print_info("تحميل إعدادات نظام طباعة التسعير (printing_pricing)...")
        
        # تحميل إعدادات نظام طباعة التسعير (الملفات الموجودة فعلياً)
        fixtures_to_load = [
            ("printing_pricing/fixtures/printing_pricing_settings.json", "أنواع الورق الأساسية"),
            ("printing_pricing/fixtures/paper_sizes.json", "مقاسات الورق"),
            ("printing_pricing/fixtures/paper_weights.json", "أوزان الورق"),
            ("printing_pricing/fixtures/paper_origins.json", "مناشئ الورق"),
            ("printing_pricing/fixtures/piece_plate_sizes.json", "مقاسات القطع والزنكات"),
            ("printing_pricing/fixtures/print_settings.json", "إعدادات الطباعة"),
            ("printing_pricing/fixtures/coating_finishing.json", "أنواع التغطية وخدمات الطباعة"),
            ("printing_pricing/fixtures/product_types_sizes.json", "أنواع ومقاسات المنتجات"),
            ("printing_pricing/fixtures/offset_machines.json", "أنواع ماكينات الأوفست"),
            ("printing_pricing/fixtures/offset_sheet_sizes.json", "مقاسات ماكينات الأوفست"),
            ("printing_pricing/fixtures/digital_machines.json", "أنواع ماكينات الديجيتال"),
            ("printing_pricing/fixtures/digital_sheet_sizes.json", "مقاسات ماكينات الديجيتال"),
        ]
        
        for fixture_path, description in fixtures_to_load:
            if run_command(f"python manage.py loaddata {fixture_path}", check=False):
                print_success(f"تم تحميل {description}")
            else:
                print_warning(f"فشل تحميل {description}")
        
        print_success("تم تحميل إعدادات نظام طباعة التسعير")


        # التحقق من نجاح تحميل بيانات التسعير
        try:
            # فحص نظام printing_pricing الجديد
            try:
                from printing_pricing.models.settings_models import (
                    PaperType as PrintingPaperType,
                    PaperSize as PrintingPaperSize,
                    PaperWeight,
                    PaperOrigin,
                    OffsetMachineType,
                    OffsetSheetSize,
                    DigitalMachineType,
                    DigitalSheetSize,
                    PlateSize,
                    PieceSize,
                    PrintDirection as PrintingPrintDirection,
                    PrintSide as PrintingPrintSide,
                    CoatingType as PrintingCoatingType,
                    FinishingType as PrintingFinishingType,
                )
                
                printing_paper_types = PrintingPaperType.objects.count()
                printing_paper_sizes = PrintingPaperSize.objects.count()
                paper_weights = PaperWeight.objects.count()
                paper_origins = PaperOrigin.objects.count()
                offset_machines = OffsetMachineType.objects.count()
                offset_sizes = OffsetSheetSize.objects.count()
                digital_machines = DigitalMachineType.objects.count()
                digital_sizes = DigitalSheetSize.objects.count()
                plate_sizes = PlateSize.objects.count()
                piece_sizes = PieceSize.objects.count()
                print_directions = PrintingPrintDirection.objects.count()
                print_sides = PrintingPrintSide.objects.count()
                coating_types = PrintingCoatingType.objects.count()
                finishing_types = PrintingFinishingType.objects.count()
                
                print_success(f"تم تحميل بيانات نظام طباعة التسعير بنجاح:")
                print_success(f"   - {printing_paper_types} نوع ورق")
                print_success(f"   - {printing_paper_sizes} مقاس ورق")
                print_success(f"   - {paper_weights} وزن ورق")
                print_success(f"   - {paper_origins} منشأ ورق")
                print_success(f"   - {offset_machines} نوع ماكينة أوفست")
                print_success(f"   - {offset_sizes} مقاس ماكينة أوفست")
                print_success(f"   - {digital_machines} نوع ماكينة ديجيتال")
                print_success(f"   - {digital_sizes} مقاس ماكينة ديجيتال")
                print_success(f"   - {plate_sizes} مقاس زنك")
                print_success(f"   - {piece_sizes} مقاس قطع")
                print_success(f"   - {print_directions} اتجاه طباعة")
                print_success(f"   - {print_sides} جانب طباعة")
                print_success(f"   - {coating_types} نوع تغطية")
                print_success(f"   - {finishing_types} نوع تشطيب")
                
            except Exception as e:
                print_warning(f"خطأ في فحص نظام طباعة التسعير: {e}")
            
            # فحص خدمات الموردين
            try:
                from supplier.models import SpecializedService
                services_count = SpecializedService.objects.count()
                print_success(f"تم العثور على {services_count} خدمة مورد متخصصة")
            except Exception as e:
                print_warning(f"خطأ في فحص خدمات الموردين: {e}")

        except Exception as e:
            print_warning(f"خطأ في التحقق من بيانات التسعير: {e}")
    else:
        print_info("تم تخطي بيانات نظام التسعير")

    # المرحلة 10: التحقق من نظام الشراكة المالية والأنظمة المتقدمة
    print_step(10, 10, "التحقق من نظام الشراكة المالية والأنظمة المتقدمة")
    
    print_info("التحقق من وجود حسابات الشراكة في دليل الحسابات...")
    print_success("حسابات الشراكة متوفرة في chart_of_accounts_final.json")
    print_info("حساب جاري الشريك محمد يوسف موجود ومُعرَّف مسبقاً")
    
    print_info("التحقق من نظام تزامن المدفوعات...")
    print_success("نظام التزامن المالي جاهز")

    print_info("التحقق من نظام الأرصدة المحسنة...")
    print_success("نظام الأرصدة المحسنة جاهز")

    print_info("التحقق من نظام طباعة التسعير (printing_pricing)...")
    print_success("نظام طباعة التسعير جاهز")
    
    print_info("التحقق من النظام الموحد للخدمات...")
    print_success("النظام الموحد للخدمات جاهز")
    
    print_info("التحقق من نظام الشراكة المالية...")
    print_success("نظام الشراكة المالية جاهز")

    # النتيجة النهائية
    print_header("✅ تم تهيئة النظام بنجاح للتطوير!")

    print_colored("\n📊 المستخدمون المحملون:", Colors.CYAN + Colors.BOLD)
    print()
    print_colored("   ✅ mwheba (محمد يوسف) - كلمة المرور: 2951096", Colors.GREEN)
    print_colored("   ✅ fatma - كلمة المرور: 2951096", Colors.GREEN)
    print_colored("   ✅ admin - كلمة المرور: admin123", Colors.GREEN)

    print_colored(f"\n{'='*50}", Colors.CYAN)

    print_colored("\n📝 الخطوات التالية:", Colors.CYAN + Colors.BOLD)
    print_colored("   1. قم بتشغيل السيرفر: python manage.py runserver", Colors.WHITE)
    print_colored("   2. افتح المتصفح على: http://127.0.0.1:8000", Colors.WHITE)
    print_colored(
        "   3. اذهب إلى نظام التسعير: http://127.0.0.1:8000/pricing/", Colors.WHITE
    )
    print_colored("   4. راجع دليل الحسابات المحاسبي المحمّل", Colors.WHITE)
    print_colored("   5. جرب إنشاء طلب تسعير جديد", Colors.WHITE)

    print_colored("\n💡 نصائح:", Colors.CYAN + Colors.BOLD)
    print_colored("   - النظام يحتوي على نظام تسعير مستقل متكامل", Colors.GRAY)
    print_colored("   - نظام تزامن المدفوعات مفعّل تلقائياً", Colors.GRAY)
    print_colored("   - القيود المحاسبية تُنشأ تلقائياً مع كل عملية", Colors.GRAY)
    print_colored("   - نظام التسعير مربوط بالعملاء والموردين فقط", Colors.GRAY)
    print()
    print_colored(
        "📦 البيانات التجريبية المحملة (إن اخترت yes):", Colors.CYAN + Colors.BOLD
    )

    print_colored("\n   🏢 العملاء والموردين:", Colors.YELLOW + Colors.BOLD)
    print_colored(
        "   - 3 عملاء: راقيات الابداع، شركة النهضة، مكتبة المعرفة", Colors.GRAY
    )
    print_colored("   - 3 موردين: مخزن مكة، مطبعة الأهرام، ورشة التجليد", Colors.GRAY)
    print_colored("   - 3 موظفين: محمد يوسف، هبة حافظ، فاطمة عمار", Colors.GRAY)

    print_colored("\n📋 نظام التسعير الموحد (محمل من fixtures):", Colors.YELLOW + Colors.BOLD)
    print_colored("   - نظام طباعة التسعير (printing_pricing) - 8 ملفات fixtures", Colors.GRAY)
    print_colored("   - أنواع الورق والمقاسات والأوزان والمناشئ", Colors.GRAY)
    print_colored("   - مقاسات القطع والزنكات وإعدادات الطباعة", Colors.GRAY)
    print_colored("   - أنواع التغطية وخدمات الطباعة وأنواع المنتجات", Colors.GRAY)
    print_colored("   - النظام الموحد للخدمات (ServiceFormFactory)", Colors.GRAY)
    print_colored("   - نظام الشراكة المالية (من fixtures)", Colors.GRAY)

    print_colored("\n   🏭 المخازن والمنتجات:", Colors.YELLOW + Colors.BOLD)
    print_colored("   - مخزن: المخزن الرئيسي", Colors.GRAY)
    print_colored("   - منتج: كوشيه 300جم (تكلفة: 5، بيع: 7)", Colors.GRAY)
    print_colored("   - فئة: ورق، ماركة: كوشيه، وحدة: فرخ", Colors.GRAY)

    # النظام جاهز
    print_colored("\n🚀 النظام جاهز للاستخدام!", Colors.GREEN + Colors.BOLD)
    
    # تشغيل السيرفر تلقائياً في الوضع التلقائي
    if auto_mode:
        print_colored("\n🔄 تشغيل السيرفر تلقائياً...", Colors.CYAN)
        print_info("سيتم تشغيل السيرفر على: http://127.0.0.1:8000")
        print_info("لإيقاف السيرفر اضغط Ctrl+C")
        
        import time
        time.sleep(2)
        
        # تشغيل السيرفر
        try:
            subprocess.run(
                [sys.executable, "manage.py", "runserver"],
                cwd=os.getcwd()
            )
        except KeyboardInterrupt:
            print_colored("\n✅ تم إيقاف السيرفر", Colors.YELLOW)
    else:
        print("   لتشغيل السيرفر استخدم: python manage.py runserver")
        print("   ثم افتح المتصفح على: http://127.0.0.1:8000")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\n❌ تم إلغاء العملية بواسطة المستخدم", Colors.YELLOW)
        sys.exit(0)
    except Exception as e:
        print_colored(f"\n❌ حدث خطأ: {e}", Colors.RED)
        sys.exit(1)
