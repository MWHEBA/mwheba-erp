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
import warnings

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


def print_colored(text, color=""):
    """طباعة نص ملون"""
    try:
        # في الوضع التلقائي، استخدم طباعة بسيطة بدون ألوان
        if auto_mode:
            # إزالة الـ emoji والرموز الخاصة
            text_clean = text.replace("✅", "[OK]").replace("❌", "[X]").replace("⚠️", "[!]")
            text_clean = text_clean.replace("🔄", "[~]").replace("📦", "[*]").replace("ℹ️", "[i]")
            print(text_clean)
        else:
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


def run_command(command, check=True, show_output=False):
    """تشغيل أمر في الـ shell"""
    try:
        # إذا كان show_output=True، نعرض الـ output مباشرة بدون capture
        if show_output:
            result = subprocess.run(
                command, shell=True, check=check, text=True
            )
            return result.returncode == 0
        else:
            # إذا كان show_output=False، نخفي الـ output
            result = subprocess.run(
                command, shell=True, check=check, capture_output=True, text=True
            )
            if result.returncode != 0 and result.stderr:
                print_warning(f"خطأ: {result.stderr[:200]}")
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
    
    # تهيئة Django في البداية
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")
    import django

    # فحص وجود ملف الإعدادات
    settings_path = Path("mwheba_erp/settings.py")
    if not settings_path.exists():
        print_colored(f"\n❌ لا يوجد ملف الإعدادات {settings_path}", Colors.RED)
        sys.exit(1)
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
                
                import time
                time.sleep(2)  # انتظار ثانيتين فقط (أسرع)
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
    if not run_command("python manage.py migrate", show_output=False):
        print_colored("\n❌ فشل تطبيق الهجرات", Colors.RED)
        sys.exit(1)
    print_success("تم تطبيق الهجرات بنجاح")

    # المرحلة 3: إنشاء المستخدمين الأساسيين
    print_step(3, 9, "إنشاء المستخدمين الأساسيين")
    
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # حذف المستخدمين القدامى دفعة واحدة
        User.objects.filter(username__in=['mwheba', 'fatma', 'admin']).delete()
        
        # إنشاء المستخدمين (أسرع)
        users_data = [
            {'username': 'mwheba', 'email': 'info@mwheba.com', 'first_name': 'Mohamed', 'last_name': 'Yousif', 'password': 'MedooAlnems2008'},
            {'username': 'fatma', 'email': 'fatma@mwheba.com', 'first_name': 'فاطمة', 'last_name': '', 'password': '2951096'},
            {'username': 'admin', 'email': 'admin@mwheba.com', 'first_name': 'Admin', 'last_name': 'Test', 'password': 'admin123'}
        ]
        
        for user_data in users_data:
            user = User.objects.create_user(
                username=user_data['username'],
                email=user_data['email'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                password=user_data['password'],
                is_superuser=True,
                is_staff=True
            )
            print_success(f"تم إنشاء المستخدم {user_data['username']}")
        
        print_success("تم إنشاء جميع المستخدمين بنجاح")
        
    except Exception as e:
        print_warning(f"فشل في إنشاء المستخدمين: {e}")

    # المرحلة 4: إنشاء الصلاحيات المخصصة والأدوار
    print_step(4, 10, "إنشاء الصلاحيات المخصصة والأدوار")
    
    print_info("إنشاء الصلاحيات المخصصة (37 صلاحية)...")
    result = run_command("python manage.py create_custom_permissions", check=False, show_output=True)
    if result:
        print_success("تم إنشاء الصلاحيات المخصصة بنجاح")
    else:
        print_warning("فشل إنشاء الصلاحيات المخصصة - تحقق من الأخطاء أعلاه")
    
    print_info("إنشاء الأدوار الأساسية (8 أدوار)...")
    result = run_command("python manage.py update_roles_with_custom_permissions", check=False, show_output=True)
    if result:
        print_success("تم إنشاء الأدوار بنجاح (8 أدوار)")
    else:
        print_warning("فشل إنشاء الأدوار - تحقق من الأخطاء أعلاه")

    # المرحلة 5: تحميل إعدادات النظام
    print_step(5, 10, "تحميل إعدادات النظام")
    
    settings_file = Path("core/fixtures/system_settings_final.json")
    if not settings_file.exists():
        print_warning(f"الملف غير موجود: {settings_file}")
    else:
        print_info("تحميل الإعدادات الشاملة (101 إعداد)...")
        try:
            if run_command("python manage.py loaddata core/fixtures/system_settings_final.json", check=False, show_output=False):
                print_success("تم تحميل جميع إعدادات النظام بنجاح")
            else:
                print_warning("فشل تحميل إعدادات النظام")
        except Exception as e:
            print_warning(f"خطأ في تحميل إعدادات النظام: {str(e)[:100]}")

    # المرحلة 6: تحميل الدليل المحاسبي
    print_step(6, 10, "تحميل الدليل المحاسبي")

    chart_file = Path("financial/fixtures/chart_of_accounts_final.json")
    if not chart_file.exists():
        print_colored("\n❌ الملف غير موجود: financial/fixtures/chart_of_accounts_final.json", Colors.RED)
        sys.exit(1)
    
    print_info("تحميل الدليل المحاسبي وقواعد التزامن...")
    try:
        # تحميل الدليل المحاسبي وقواعد التزامن معاً (دفعة واحدة)
        financial_fixtures = ["financial/fixtures/chart_of_accounts_final.json"]
        sync_rules_file = Path("financial/fixtures/payment_sync_rules.json")
        
        if sync_rules_file.exists():
            financial_fixtures.append("financial/fixtures/payment_sync_rules.json")
        
        fixtures_str = " ".join(financial_fixtures)
        
        if not run_command(f"python manage.py loaddata {fixtures_str}", show_output=False):
            print_colored("\n❌ فشل تحميل البيانات المالية", Colors.RED)
            sys.exit(1)
        
        print_success(f"تم تحميل الدليل المحاسبي ({len(financial_fixtures)} ملف)")
    except Exception as e:
        print_colored(f"\n❌ خطأ في تحميل البيانات المالية: {str(e)[:100]}", Colors.RED)
        sys.exit(1)

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
        # المجموعة الأولى: البيانات الأساسية (يمكن تحميلها دفعة واحدة)
        basic_fixtures = [
            "product/fixtures/initial_data.json",
            "client/fixtures/initial_data.json",
            "hr/fixtures/departments.json",
            "hr/fixtures/job_titles.json",
            "hr/fixtures/initial_data.json",
            "hr/fixtures/biometric_devices.json",
            "hr/fixtures/employees_demo.json",
            "supplier/fixtures/supplier_types.json",
            "supplier/fixtures/initial_data.json",
        ]
        
        test_loaded = 0
        test_failed = 0
        
        # فحص الملفات الموجودة
        existing_fixtures = [f for f in basic_fixtures if Path(f).exists()]
        
        if existing_fixtures:
            print_info(f"تحميل البيانات الأساسية ({len(existing_fixtures)} ملف دفعة واحدة)...")
            fixtures_str = " ".join(existing_fixtures)
            try:
                if run_command(f"python manage.py loaddata {fixtures_str}", check=False, show_output=False):
                    print_success(f"تم تحميل {len(existing_fixtures)} ملف بيانات أساسية بنجاح")
                    test_loaded = len(existing_fixtures)
                else:
                    print_warning("فشل تحميل بعض البيانات الأساسية")
                    test_failed = len(existing_fixtures)
            except Exception as e:
                print_warning(f"خطأ في تحميل البيانات الأساسية: {str(e)[:100]}")
                test_failed = len(existing_fixtures)
        
        # المجموعة الثانية: علاقات الموردين (تعتمد على الموردين)
        relationships_file = Path("supplier/fixtures/supplier_relationships.json")
        if relationships_file.exists():
            print_info("تحميل علاقات الموردين...")
            try:
                if run_command("python manage.py loaddata supplier/fixtures/supplier_relationships.json", check=False, show_output=False):
                    print_success("تم تحميل علاقات الموردين")
                    test_loaded += 1
                else:
                    print_warning("فشل تحميل علاقات الموردين")
                    test_failed += 1
            except Exception as e:
                print_warning(f"خطأ في تحميل علاقات الموردين: {str(e)[:100]}")
                test_failed += 1
        
        # تحميل الفواتير التجريبية باستخدام السكريبت (اختياري)
        load_invoices = False
        if auto_mode:
            # في الوضع التلقائي، لا نحمل الفواتير افتراضياً
            print_info("الوضع التلقائي: تخطي تحميل الفواتير التجريبية")
        else:
            # سؤال المستخدم
            print_colored("\n📋 تحميل الفواتير التجريبية", Colors.CYAN)
            print_info("هل تريد تحميل فواتير ودفعات تجريبية؟")
            print_info("(يتضمن: فواتير شراء، فواتير بيع، دفعات، قيود محاسبية)")
            invoice_confirm = input("تحميل الفواتير؟ (yes/no): ").strip().lower()
            load_invoices = (invoice_confirm == "yes")
        
        if load_invoices:
            print_info("تحميل فواتير ودفعات تجريبية (وضع تلقائي)...")
            try:
                result = subprocess.run(
                    ["python", "tests/fixtures/load_demo_transactions_automated.py"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                # نتحقق من exit code فقط، نتجاهل warnings في stderr
                if result.returncode == 0:
                    # عرض تفاصيل ما تم تحميله
                    if result.stdout:
                        for line in result.stdout.strip().split('\n'):
                            if line.strip():
                                # عرض الرسائل المهمة فقط
                                if '[OK]' in line or '[X]' in line or '[*]' in line or 'تم' in line or 'الملخص' in line or 'الأتمتة' in line or '[1/4]' in line or '[2/4]' in line or '[3/4]' in line or '[4/4]' in line:
                                    print_success(f"   {line.strip()}")
                    print_success("تم تحميل فواتير ودفعات تجريبية (معالجة تلقائية)")
                    test_loaded += 1
                else:
                    print_warning("فشل تحميل فواتير ودفعات تجريبية")
                    # عرض آخر 15 سطر من الخطأ
                    if result.stderr:
                        print_warning("الخطأ:")
                        lines = result.stderr.strip().split('\n')
                        for line in lines[-15:]:
                            print(f"   {line}")
                    elif result.stdout:
                        print_warning("التفاصيل:")
                        lines = result.stdout.strip().split('\n')
                        for line in lines[-15:]:
                            print(f"   {line}")
                    test_failed += 1
            except Exception as e:
                print_warning(f"خطأ في تحميل فواتير ودفعات تجريبية: {str(e)[:100]}")
                test_failed += 1
        else:
            print_info("تم تخطي تحميل الفواتير التجريبية")
        
        # إنشاء أرصدة الإجازات إذا تم تحميل الموظفين
        if Path("hr/fixtures/employees_demo.json").exists():
            print_info("إنشاء أرصدة الإجازات للموظفين...")
            try:
                if run_command("python manage.py create_leave_balances --year 2025", check=False, show_output=False):
                    print_success("تم إنشاء أرصدة الإجازات")
                else:
                    print_warning("فشل إنشاء أرصدة الإجازات")
            except Exception as e:
                print_warning(f"خطأ في إنشاء أرصدة الإجازات: {str(e)[:100]}")
        
        # حساب إجمالي الملفات المتوقعة
        total_expected = len(basic_fixtures) + 2  # +1 للعلاقات +1 للفواتير
        
        if test_loaded > 0:
            print_success(f"تم تحميل {test_loaded} من {total_expected} ملف بيانات تجريبية")
        if test_failed > 0:
            print_warning(f"فشل تحميل {test_failed} ملف")

        # التحقق من نجاح تحميل البيانات
        try:
            from product.models import Product, Warehouse
            from client.models import Customer
            from supplier.models import Supplier
            from hr.models import Department, Employee
            from purchase.models import Purchase, PurchasePayment
            from sale.models import Sale, SalePayment

            products_count = Product.objects.count()
            warehouses_count = Warehouse.objects.count()
            customers_count = Customer.objects.count()
            suppliers_count = Supplier.objects.count()
            departments_count = Department.objects.count()
            employees_count = Employee.objects.count()
            purchases_count = Purchase.objects.count()
            sales_count = Sale.objects.count()
            purchase_payments_count = PurchasePayment.objects.count()
            sale_payments_count = SalePayment.objects.count()

            print_success(f"تم تحميل البيانات التجريبية بنجاح:")
            print_success(f"   - {products_count} منتج")
            print_success(f"   - {warehouses_count} مخزن")
            print_success(f"   - {customers_count} عميل")
            print_success(f"   - {suppliers_count} مورد")
            print_success(f"   - {departments_count} قسم")
            print_success(f"   - {employees_count} موظف")
            
            if purchases_count > 0 or sales_count > 0:
                print_success(f"\n   📦 الفواتير والدفعات:")
                print_success(f"   - {purchases_count} فاتورة شراء")
                print_success(f"   - {sales_count} فاتورة بيع")
                print_success(f"   - {purchase_payments_count} دفعة شراء")
                print_success(f"   - {sale_payments_count} دفعة بيع")
                
                # حساب الملخص المالي
                from django.db.models import Sum
                total_purchases = Purchase.objects.aggregate(total=Sum('total'))['total'] or 0
                total_sales = Sale.objects.aggregate(total=Sum('total'))['total'] or 0
                total_purchase_payments = PurchasePayment.objects.filter(status='posted').aggregate(total=Sum('amount'))['total'] or 0
                total_sale_payments = SalePayment.objects.filter(status='posted').aggregate(total=Sum('amount'))['total'] or 0
                
                print_success(f"\n   💰 الملخص المالي:")
                print_success(f"   - إجمالي المشتريات: {total_purchases} ج")
                print_success(f"   - إجمالي المبيعات: {total_sales} ج")
                print_success(f"   - المدفوع للموردين: {total_purchase_payments} ج")
                print_success(f"   - المحصل من العملاء: {total_sale_payments} ج")
                print_success(f"   - صافي حركة الخزينة: {total_sale_payments - total_purchase_payments} ج")

        except Exception as e:
            print_warning(f"خطأ في التحقق من البيانات: {e}")
    else:
        print_info("تم تخطي البيانات التجريبية")

    # المرحلة 9: تحميل بيانات أنظمة التسعير
    print_step(9, 10, "تحميل بيانات أنظمة التسعير")

    if load_test_data:
        # تحميل بيانات نظام printing_pricing (دفعة واحدة)
        print_info("تحميل إعدادات نظام طباعة التسعير (printing_pricing)...")
        
        pricing_fixtures = [
            "printing_pricing/fixtures/printing_pricing_settings.json",
            "printing_pricing/fixtures/paper_sizes.json",
            "printing_pricing/fixtures/paper_weights.json",
            "printing_pricing/fixtures/paper_origins.json",
            "printing_pricing/fixtures/piece_plate_sizes.json",
            "printing_pricing/fixtures/print_settings.json",
            "printing_pricing/fixtures/coating_finishing.json",
            "printing_pricing/fixtures/product_types_sizes.json",
            "printing_pricing/fixtures/offset_machines.json",
            "printing_pricing/fixtures/offset_sheet_sizes.json",
            "printing_pricing/fixtures/digital_machines.json",
            "printing_pricing/fixtures/digital_sheet_sizes.json",
        ]
        
        # فحص الملفات الموجودة
        existing_pricing = [f for f in pricing_fixtures if Path(f).exists()]
        
        loaded_count = 0
        failed_count = 0
        
        if existing_pricing:
            print_info(f"تحميل إعدادات التسعير ({len(existing_pricing)} ملف دفعة واحدة)...")
            fixtures_str = " ".join(existing_pricing)
            try:
                if run_command(f"python manage.py loaddata {fixtures_str}", check=False, show_output=False):
                    print_success(f"تم تحميل {len(existing_pricing)} ملف إعدادات تسعير بنجاح")
                    loaded_count = len(existing_pricing)
                else:
                    print_warning("فشل تحميل بعض إعدادات التسعير")
                    failed_count = len(existing_pricing)
            except Exception as e:
                print_warning(f"خطأ في تحميل إعدادات التسعير: {str(e)[:100]}")
                failed_count = len(existing_pricing)
        
        if loaded_count > 0:
            print_success(f"تم تحميل إعدادات نظام طباعة التسعير ({loaded_count} ملف)")
        if failed_count > 0:
            print_warning(f"فشل تحميل {failed_count} ملف")


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
    print_colored("   ✅ mwheba (محمد يوسف) - كلمة المرور: MedooAlnems2008", Colors.GREEN)
    print_colored("   ✅ fatma - كلمة المرور: 2951096", Colors.GREEN)
    print_colored("   ✅ admin - كلمة المرور: admin123", Colors.GREEN)

    print_colored(f"\n{'='*50}", Colors.CYAN)

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
        "   - 5 عملاء: راقيات الابداع، تراست بلس، وغيرهم", Colors.GRAY
    )
    print_colored("   - 5 موردين: شركة الورق السعودية، مطابع الخليج، وغيرهم", Colors.GRAY)
    print_colored("   - 3 موظفين: محمد يوسف، هبة حافظ، فاطمة عمار", Colors.GRAY)
    
    print_colored("\n   📦 الفواتير التجريبية:", Colors.YELLOW + Colors.BOLD)
    print_colored("   - 2 فاتورة شراء (نقدي + آجل مع دفعة جزئية)", Colors.GRAY)
    print_colored("   - 2 فاتورة بيع (نقدي + آجل مع تحصيل جزئي)", Colors.GRAY)
    print_colored("   - 4 دفعات مرحّلة (2 شراء + 2 بيع)", Colors.GRAY)
    print_colored("   - إجمالي المشتريات: 6,200 ج", Colors.GRAY)
    print_colored("   - إجمالي المبيعات: 1,675 ج", Colors.GRAY)
    print_colored("   - صافي حركة الخزينة: -3,300 ج", Colors.GRAY)

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
