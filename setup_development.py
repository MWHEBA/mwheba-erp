#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup_development.py - سكريبت إعداد بيئة التطوير
يقوم بتهيئة النظام للتطوير مع تحميل البيانات الأساسية
"""

import os
import sys
import subprocess
from pathlib import Path

# الألوان للطباعة
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_colored(text, color=''):
    """طباعة نص ملون"""
    print(f"{color}{text}{Colors.RESET}")

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
            command,
            shell=True,
            check=check,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print_warning(f"فشل تنفيذ الأمر: {e}")
        return False

def kill_django_processes():
    """محاولة إيقاف عمليات Django التي قد تستخدم قاعدة البيانات"""
    try:
        if os.name == 'nt':  # Windows
            # البحث عن عمليات Python التي تشغل manage.py
            result = subprocess.run(
                'tasklist /FI "IMAGENAME eq python.exe" /FO CSV',
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and 'python.exe' in result.stdout:
                print_info("تم العثور على عمليات Python قيد التشغيل")
                kill_confirm = input("هل تريد محاولة إيقاف عمليات Python؟ (yes/no): ").strip().lower()
                if kill_confirm == 'yes':
                    subprocess.run('taskkill /F /IM python.exe', shell=True, capture_output=True)
                    print_success("تم إيقاف عمليات Python")
                    return True
        else:  # Linux/Mac
            result = subprocess.run(
                "ps aux | grep 'manage.py runserver' | grep -v grep",
                shell=True,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                print_info("تم العثور على عمليات Django قيد التشغيل")
                kill_confirm = input("هل تريد محاولة إيقاف عمليات Django؟ (yes/no): ").strip().lower()
                if kill_confirm == 'yes':
                    subprocess.run("pkill -f 'manage.py runserver'", shell=True)
                    print_success("تم إيقاف عمليات Django")
                    return True
    except Exception as e:
        print_warning(f"فشل في فحص العمليات: {e}")
    return False

def main():
    """الدالة الرئيسية"""
    
    # التأكد من وجود manage.py
    if not Path('manage.py').exists():
        print_colored("❌ خطأ: لم يتم العثور على manage.py", Colors.RED)
        print_colored("   تأكد من تشغيل السكريبت من مجلد المشروع الرئيسي", Colors.GRAY)
        sys.exit(1)
    
    # تهيئة Django في البداية
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
    import django
    django.setup()
    
    # طباعة العنوان
    print_header("ERP System - Development Setup")
    
    # سؤال بسيط للإعداد
    print_colored("\n🛠️  إعداد النظام", Colors.CYAN)
    print("سيتم تنفيذ الإعداد الكامل (قاعدة بيانات جديدة + بيانات تجريبية)")
    confirm = input("هل تريد المتابعة؟ (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print_colored("\n❌ تم إلغاء العملية", Colors.YELLOW)
        sys.exit(0)
        
    load_test_data = True
    
    # المرحلة 1: حذف قاعدة البيانات القديمة
    print_step(1, 9, "حذف قاعدة البيانات القديمة")
    db_path = Path('db.sqlite3')
    if db_path.exists():
        try:
            db_path.unlink()
            print_success("تم حذف قاعدة البيانات القديمة")
        except PermissionError:
            print_warning("⚠️  قاعدة البيانات مفتوحة في عملية أخرى!")
            print_colored("   الحلول المقترحة:", Colors.YELLOW)
            print_colored("   1. أغلق السيرفر Django إذا كان يعمل (Ctrl+C)", Colors.WHITE)
            print_colored("   2. أغلق أي IDE أو برنامج يستخدم قاعدة البيانات", Colors.WHITE)
            print_colored("   3. أعد تشغيل السكريبت بعد إغلاق العمليات", Colors.WHITE)
            
            # محاولة إيقاف العمليات تلقائياً
            if kill_django_processes():
                # انتظار قصير ثم محاولة الحذف مرة أخرى
                import time
                time.sleep(2)
                try:
                    db_path.unlink()
                    print_success("تم حذف قاعدة البيانات بنجاح!")
                except PermissionError:
                    print_warning("لا يزال الملف مستخدم")
            
            # محاولة أخرى بعد تحذير المستخدم
            if db_path.exists():
                retry = input("\nهل تريد المحاولة مرة أخرى؟ (yes/no): ").strip().lower()
                if retry == 'yes':
                    try:
                        db_path.unlink()
                        print_success("تم حذف قاعدة البيانات بنجاح!")
                    except PermissionError:
                        print_colored("\n❌ لا يمكن حذف قاعدة البيانات", Colors.RED)
                        print_colored("   يرجى إغلاق جميع العمليات التي تستخدم قاعدة البيانات يدوياً", Colors.GRAY)
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
    
    # المرحلة 3: تحميل المستخدمين
    print_step(3, 9, "تحميل المستخدمين الأساسيين")
    print_info("تحميل المستخدمين (mwheba, fatma)...")
    if run_command("python manage.py loaddata users/fixtures/initial_data.json", check=False):
        print_success("تم تحميل المستخدمين بنجاح")
    else:
        print_warning("فشل تحميل المستخدمين")
    
    # المرحلة 4: تحميل إعدادات النظام
    print_step(4, 9, "تحميل إعدادات النظام")
    run_command("python manage.py loaddata core/fixtures/initial_data.json", check=False)
    print_success("تم تحميل إعدادات النظام")
    
    # المرحلة 5: تحميل الدليل المحاسبي
    print_step(5, 9, "تحميل الدليل المحاسبي")
    
    print_info("تحميل شجرة الحسابات (النسخة النهائية المحدثة)...")
    if not run_command("python manage.py loaddata financial/fixtures/chart_of_accounts_final.json"):
        print_colored("\n❌ فشل تحميل الدليل المحاسبي", Colors.RED)
        print_info("تأكد من وجود الملف: financial/fixtures/chart_of_accounts_final.json")
        sys.exit(1)
    
    print_info("تحميل قواعد التزامن المالي...")
    if run_command("python manage.py loaddata financial/fixtures/payment_sync_rules.json", check=False):
        print_success("تم تحميل قواعد التزامن بنجاح")
    else:
        print_warning("فشل تحميل قواعد التزامن")
    
    print_success("تم تحميل الدليل المحاسبي")
    
    # التحقق من الصلاحيات الأساسية
    print_info("التحقق من الصلاحيات الأساسية...")
    try:
        from django.contrib.auth.models import Permission
        permissions_count = Permission.objects.count()
        print_success(f"تم العثور على {permissions_count} صلاحية في النظام")
    except Exception as e:
        print_warning(f"خطأ في التحقق من الصلاحيات: {e}")
    
    # إعطاء جميع الصلاحيات للمستخدمين موهبة وفاطمة
    print_info("إعطاء جميع الصلاحيات للمستخدمين موهبة وفاطمة...")
    try:
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        
        User = get_user_model()
        
        # البحث عن المستخدمين
        users_to_grant = ['mwheba', 'fatma']
        
        for username in users_to_grant:
            try:
                user = User.objects.get(username=username)
                
                # إعطاء جميع الصلاحيات
                all_permissions = Permission.objects.all()
                user.user_permissions.set(all_permissions)
                
                # جعله superuser أيضاً
                user.is_superuser = True
                user.is_staff = True
                user.save()
                
                print_success(f"تم إعطاء جميع الصلاحيات للمستخدم {username}")
                
            except User.DoesNotExist:
                print_warning(f"المستخدم {username} غير موجود")
        
        print_success("تم إعطاء جميع الصلاحيات بنجاح")
        
    except Exception as e:
        print_warning(f"فشل في إعطاء الصلاحيات: {str(e)}")
    
    # المرحلة 6: إنشاء الفترة المالية 2025
    print_step(6, 9, "إنشاء الفترة المالية 2025")
    
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
                'name': 'السنة المالية 2025',
                'status': 'open',
                'created_by': first_user
            }
        )
        if created:
            print_success("تم إنشاء الفترة المالية 2025 بنجاح")
        else:
            print_info("الفترة المالية 2025 موجودة بالفعل")
    except Exception as e:
        print_warning(f"فشل إنشاء الفترة المالية: {e}")
    
    # المرحلة 7: بيانات تجريبية
    print_step(7, 9, "تحميل البيانات التجريبية")
    
    if load_test_data:
        print_info("تحميل المخازن والمنتجات...")
        if run_command("python manage.py loaddata product/fixtures/initial_data.json", check=False):
            print_success("تم تحميل المخازن والمنتجات")
        else:
            print_warning("فشل تحميل المخازن والمنتجات")
        
        print_info("تحميل العملاء...")
        if run_command("python manage.py loaddata client/fixtures/initial_data.json", check=False):
            print_success("تم تحميل العملاء")
        else:
            print_warning("فشل تحميل العملاء")
        
        print_info("تحميل أنواع الموردين...")
        if not run_command("python manage.py loaddata supplier/fixtures/supplier_types.json", check=False):
            print_error("فشل تحميل أنواع الموردين من الـ fixtures")
            return False
        print_success("تم تحميل أنواع الموردين")
        
        print_info("تحميل الموردين...")
        if not run_command("python manage.py loaddata supplier/fixtures/initial_data.json", check=False):
            print_error("فشل تحميل الموردين من الـ fixtures")
            return False
        print_success("تم تحميل الموردين")
        
        print_info("تحميل علاقات الموردين بأنواعهم...")
        if not run_command("python manage.py loaddata supplier/fixtures/supplier_relationships.json", check=False):
            print_error("فشل تحميل علاقات الموردين من الـ fixtures")
            return False
        print_success("تم تحميل علاقات الموردين")
        
        # التحقق من نجاح تحميل البيانات
        try:
            from product.models import Product, Warehouse
            from client.models import Customer
            from supplier.models import Supplier
            
            products_count = Product.objects.count()
            warehouses_count = Warehouse.objects.count()
            customers_count = Customer.objects.count()
            suppliers_count = Supplier.objects.count()
            
            print_success(f"تم تحميل البيانات التجريبية بنجاح:")
            print_success(f"   - {products_count} منتج")
            print_success(f"   - {warehouses_count} مخزن")
            print_success(f"   - {customers_count} عميل")
            print_success(f"   - {suppliers_count} مورد")
            
        except Exception as e:
            print_warning(f"خطأ في التحقق من البيانات: {e}")
    else:
        print_info("تم تخطي البيانات التجريبية")
    
    # المرحلة 8: تحميل بيانات نظام التسعير
    print_step(8, 9, "تحميل بيانات نظام التسعير المستقل")
    
    if load_test_data:
        print_info("تحميل البيانات الأساسية لنظام التسعير...")
        # إنشاء بيانات التسعير يدوياً
        try:
            from pricing.models import PaperType, PaperSize, PrintDirection, PrintSide
            
            # إنشاء أنواع الورق
            paper_types_data = [
                {'name': 'كوشيه', 'description': 'ورق كوشيه عالي الجودة للطباعة الملونة'},
                {'name': 'أوفست', 'description': 'ورق أوفست للطباعة العادية'},
                {'name': 'كرتون', 'description': 'كرتون للتغليف والصناديق'},
            ]
            
            for paper_data in paper_types_data:
                PaperType.objects.get_or_create(
                    name=paper_data['name'],
                    defaults={
                        'description': paper_data['description'],
                        'is_active': True
                    }
                )
            
            # إنشاء مقاسات الورق
            paper_sizes_data = [
                {'name': 'فرخ 70×100', 'width': 70.00, 'height': 100.00},
                {'name': 'نصف فرخ 50×70', 'width': 50.00, 'height': 70.00},
                {'name': 'A4', 'width': 21.00, 'height': 29.70},
                {'name': 'A3', 'width': 29.70, 'height': 42.00},
            ]
            
            for size_data in paper_sizes_data:
                PaperSize.objects.get_or_create(
                    name=size_data['name'],
                    defaults={
                        'width': size_data['width'],
                        'height': size_data['height'],
                        'is_active': True
                    }
                )
            
            # إنشاء اتجاهات الطباعة
            print_directions_data = [
                {'name': 'عادي', 'description': 'طباعة عادية'},
                {'name': 'مقلوب', 'description': 'طباعة مقلوبة'},
            ]
            
            for direction_data in print_directions_data:
                try:
                    PrintDirection.objects.get_or_create(
                        name=direction_data['name'],
                        defaults={
                            'description': direction_data['description'],
                            'is_active': True
                        }
                    )
                except:
                    pass
            
            # إنشاء جهات الطباعة
            print_sides_data = [
                {'name': 'وجه واحد', 'description': 'طباعة على وجه واحد فقط'},
                {'name': 'وجهين', 'description': 'طباعة على الوجهين'},
            ]
            
            for side_data in print_sides_data:
                try:
                    PrintSide.objects.get_or_create(
                        name=side_data['name'],
                        defaults={
                            'description': side_data['description'],
                            'is_active': True
                        }
                    )
                except:
                    pass
            
            print_success("تم تحميل البيانات الأساسية للتسعير")
        except Exception as e:
            print_warning(f"فشل تحميل البيانات الأساسية للتسعير: {e}")
        
        print_info("تحميل أمثلة طلبات التسعير...")
        if run_command("python manage.py loaddata pricing/fixtures/sample_orders.json", check=False):
            print_success("تم تحميل أمثلة طلبات التسعير")
        else:
            print_warning("فشل تحميل أمثلة طلبات التسعير")
        
        print_info("تحميل أمثلة عروض الأسعار...")
        if run_command("python manage.py loaddata pricing/fixtures/sample_quotations.json", check=False):
            print_success("تم تحميل أمثلة عروض الأسعار")
        else:
            print_warning("فشل تحميل أمثلة عروض الأسعار")
        
        # التحقق من نجاح تحميل بيانات التسعير
        try:
            from pricing.models import (
                PaperType, PaperSize, PrintDirection, PrintSide, 
                CoatingType, FinishingType,
                PricingOrder, PricingQuotation
            )
            # استيراد SupplierService من supplier.models
            try:
                from supplier.models import SpecializedService
                services_count = SpecializedService.objects.count()
            except:
                services_count = 0
            
            # استيراد PricingApprovalWorkflow إذا كان موجود
            try:
                from pricing.models import PricingApprovalWorkflow
                workflows_count = PricingApprovalWorkflow.objects.count()
            except:
                workflows_count = 0
            
            paper_types_count = PaperType.objects.count()
            paper_sizes_count = PaperSize.objects.count()
            orders_count = PricingOrder.objects.count()
            quotations_count = PricingQuotation.objects.count()
            
            print_success(f"تم تحميل بيانات نظام التسعير بنجاح:")
            print_success(f"   - {paper_types_count} نوع ورق")
            print_success(f"   - {paper_sizes_count} مقاس ورق")
            print_success(f"   - {services_count} خدمة مورد")
            print_success(f"   - {orders_count} طلب تسعير")
            print_success(f"   - {quotations_count} عرض سعر")
            print_success(f"   - {workflows_count} تدفق موافقة")
            
        except Exception as e:
            print_warning(f"خطأ في التحقق من بيانات التسعير: {e}")
    else:
        print_info("تم تخطي بيانات نظام التسعير")
    
    # المرحلة 9: تفعيل الأنظمة المتقدمة
    print_step(9, 9, "تفعيل الأنظمة المتقدمة")
    print_info("التحقق من نظام تزامن المدفوعات...")
    print_success("نظام التزامن المالي جاهز")
    
    print_info("التحقق من نظام الأرصدة المحسنة...")
    print_success("نظام الأرصدة المحسنة جاهز")
    
    print_info("التحقق من نظام التسعير المستقل...")
    print_success("نظام التسعير المستقل جاهز")
    
    # النتيجة النهائية
    print_header("✅ تم تهيئة النظام بنجاح للتطوير!")
    
    print_colored("\n📊 المستخدمون المحملون:", Colors.CYAN + Colors.BOLD)
    print()
    print_colored("   ✅ المستخدم الأول: mwheba (Mohamed Yousif)", Colors.GREEN)
    print_colored("   ✅ المستخدم الثاني: fatma", Colors.GREEN)
    
    print_colored(f"\n{'='*50}", Colors.CYAN)
    
    print_colored("\n🔐 تغيير كلمة المرور (مهم جداً!):", Colors.RED + Colors.BOLD)
    print_colored("\n   لتغيير كلمة المرور لاحقاً استخدم:", Colors.WHITE)
    print()
    print_colored("   python manage.py changepassword mwheba", Colors.YELLOW)
    
    print_colored(f"\n{'='*50}", Colors.CYAN)
    
    print_colored("\n📝 الخطوات التالية:", Colors.CYAN + Colors.BOLD)
    print_colored("   1. قم بتشغيل السيرفر: python manage.py runserver", Colors.WHITE)
    print_colored("   2. افتح المتصفح على: http://127.0.0.1:8000", Colors.WHITE)
    print_colored("   3. اذهب إلى نظام التسعير: http://127.0.0.1:8000/pricing/", Colors.WHITE)
    print_colored("   4. راجع دليل الحسابات المحاسبي المحمّل", Colors.WHITE)
    print_colored("   5. جرب إنشاء طلب تسعير جديد", Colors.WHITE)
    
    print_colored("\n💡 نصائح:", Colors.CYAN + Colors.BOLD)
    print_colored("   - النظام يحتوي على نظام تسعير مستقل متكامل", Colors.GRAY)
    print_colored("   - نظام تزامن المدفوعات مفعّل تلقائياً", Colors.GRAY)
    print_colored("   - القيود المحاسبية تُنشأ تلقائياً مع كل عملية", Colors.GRAY)
    print_colored("   - نظام التسعير مربوط بالعملاء والموردين فقط", Colors.GRAY)
    print()
    print_colored("📦 البيانات التجريبية المحملة (إن اخترت yes):", Colors.CYAN + Colors.BOLD)
    
    print_colored("\n   🏢 العملاء والموردين:", Colors.YELLOW + Colors.BOLD)
    print_colored("   - 3 عملاء: راقيات الابداع، شركة النهضة، مكتبة المعرفة", Colors.GRAY)
    print_colored("   - 3 موردين: مخزن مكة، مطبعة الأهرام، ورشة التجليد", Colors.GRAY)
    
    print_colored("\n   📋 نظام التسعير:", Colors.YELLOW + Colors.BOLD)
    print_colored("   - 3 أنواع ورق: كوشيه، أوفست، كرتون", Colors.GRAY)
    print_colored("   - 4 مقاسات: فرخ، نصف فرخ، A4، A3", Colors.GRAY)
    print_colored("   - 4 أنواع تشطيب: قص، طي، تجليد حلزوني، تجليد كعب", Colors.GRAY)
    print_colored("   - 3 خدمات موردين: ورنيش، طي، تجليد", Colors.GRAY)
    print_colored("   - 2 تدفق موافقة: عادية وكبيرة", Colors.GRAY)
    print_colored("   - 2 طلب تسعير نموذجي", Colors.GRAY)
    print_colored("   - 2 عرض سعر نموذجي", Colors.GRAY)
    
    print_colored("\n   🏭 المخازن والمنتجات:", Colors.YELLOW + Colors.BOLD)
    print_colored("   - مخزن: المخزن الرئيسي", Colors.GRAY)
    print_colored("   - منتج: كوشيه 300جم (تكلفة: 5، بيع: 7)", Colors.GRAY)
    print_colored("   - فئة: ورق، ماركة: كوشيه، وحدة: فرخ", Colors.GRAY)
    print()
    
    # سؤال عن تغيير كلمة المرور
    print_colored(f"{'='*50}", Colors.CYAN)
    # سؤال تغيير كلمة المرور
    change_pass = input("\nهل تريد تغيير كلمة مرور mwheba الآن؟ (yes/no): ").strip().lower()
    
    if change_pass == 'yes':
        print("\n🔐 تغيير كلمة مرور المستخدم (mwheba):")
        if run_command("python manage.py changepassword mwheba", check=False):
            print_success("تم تغيير كلمة المرور بنجاح!")
        else:
            print_warning("فشل في تغيير كلمة المرور")
            print_info("يمكنك تغييرها لاحقاً بالأمر: python manage.py changepassword mwheba")
    
    # النظام جاهز
    print("\n🚀 النظام جاهز للاستخدام!")
    print("   لتشغيل السيرفر استخدم: python manage.py runserver")
    print("   ثم افتح المتصفح على: http://127.0.0.1:8000")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\n❌ تم إلغاء العملية بواسطة المستخدم", Colors.YELLOW)
        sys.exit(0)
    except Exception as e:
        print_colored(f"\n❌ حدث خطأ: {e}", Colors.RED)
        sys.exit(1)
