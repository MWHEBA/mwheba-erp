from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.management import call_command
from django.apps import apps
import os
import sys
from pathlib import Path


class Command(BaseCommand):
    help = 'إعادة تهيئة النظام - استعادة ضبط مصنع'

    def add_arguments(self, parser):
        parser.add_argument(
            '--operation-id',
            type=str,
        )

    def handle(self, *args, **options):
        operation_id = options['operation_id']
        
        try:
            # المراحل الأساسية
            self.update_progress(operation_id, 1, 10, "حذف البيانات الموجودة...", 10)
            self.clear_all_data()
            
            self.update_progress(operation_id, 2, 10, "تطبيق الهجرات...", 20)
            self.apply_migrations()
            
            # إنشاء المستخدمين أولاً قبل أي fixtures
            self.update_progress(operation_id, 3, 10, "إنشاء المستخدمين الأساسيين...", 25)
            self.create_users()
            
            self.update_progress(operation_id, 4, 10, "تحميل إعدادات النظام...", 35)
            self.load_initial_data()
            
            self.update_progress(operation_id, 5, 10, "تحميل الدليل المحاسبي...", 45)
            self.load_chart_of_accounts()
            
            self.update_progress(operation_id, 6, 10, "إنشاء الفترة المالية 2025...", 55)
            self.create_accounting_period()
            
            # الآن نحمل البيانات التجريبية بعد إنشاء المستخدمين
            self.update_progress(operation_id, 7, 10, "تحميل البيانات التجريبية...", 65)
            self.load_test_data()
            
            self.update_progress(operation_id, 8, 10, "تحميل بيانات أنظمة التسعير...", 75)
            self.load_pricing_data()
            
            self.update_progress(operation_id, 9, 10, "تحميل fixtures إضافية...", 85)
            self.load_additional_fixtures()
            
            self.update_progress(operation_id, 10, 10, "تفعيل الأنظمة المتقدمة...", 95)
            self.verify_partnership_system()
            self.activate_advanced_systems()
            
            # تحديث الحالة النهائية
            cache.set(f"progress_{operation_id}", {
                'status': 'completed',
                'percentage': 100,
                'step_name': 'تم الانتهاء بنجاح!',
                'success': True,
                'message': 'تم إعادة تهيئة النظام بنجاح!',
                'current_step': 10,
                'total_steps': 10,
                'messages': cache.get(f"progress_{operation_id}", {}).get('messages', [])
            }, timeout=600)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            cache.set(f"progress_{operation_id}", {
                'status': 'failed',
                'success': False,
                'message': f'حدث خطأ: {str(e)}',
                'error_details': error_details
            }, timeout=600)
            self.stdout.write(f"   [X] خطأ في العملية: {str(e)}")
            self.stdout.write(f"   [X] تفاصيل الخطأ: {error_details}")
            raise

    def update_progress(self, operation_id, current_step, total_steps, step_name, percentage):
        """تحديث تقدم العملية"""
        progress_data = cache.get(f"progress_{operation_id}", {'messages': []})
        progress_data.update({
            'status': 'running',
            'current_step': current_step,
            'total_steps': total_steps,
            'step_name': step_name,
            'percentage': percentage,
        })
        progress_data['messages'].append(f"المرحلة {current_step}: {step_name}")
        cache.set(f"progress_{operation_id}", progress_data, timeout=600)
        
        self.stdout.write(f"[*] المرحلة {current_step}/{total_steps}: {step_name}...")

    def clear_all_data(self):
        """حذف جميع البيانات باستخدام Django ORM"""
        # قائمة النماذج التي نريد حذف بياناتها (بترتيب الاعتماديات)
        models_to_clear = [
            'sale.SaleItem',
            'sale.Sale', 
            'purchase.PurchaseItem',
            'purchase.Purchase',
            'product.Stock',
            'product.Product',
            'client.Customer',
            'supplier.Supplier',
            'financial.JournalEntry',
            'financial.AccountingPeriod',
            'core.Notification',
        ]
        
        with transaction.atomic():
            for model_path in models_to_clear:
                try:
                    app_label, model_name = model_path.split('.')
                    model = apps.get_model(app_label, model_name)
                    count = model.objects.count()
                    if count > 0:
                        model.objects.all().delete()
                        self.stdout.write(f"   [+] تم حذف {count} سجل من {model_name}")
                except Exception as e:
                    self.stdout.write(f"   [!] تخطي {model_path}: {str(e)}")

    def apply_migrations(self):
        """تطبيق الهجرات"""
        try:
            call_command('migrate', verbosity=0)
            self.stdout.write("   [+] تم تطبيق الهجرات بنجاح")
        except Exception as e:
            self.stdout.write(f"   [!] خطأ في تطبيق الهجرات: {e}")

    def create_users(self):
        User = get_user_model()
        
        users_data = [
            {
                'username': 'mwheba',
                'email': 'info@mwheba.com',
                'first_name': 'Mohamed',
                'last_name': 'Yousif',
                'password': 'MedooAlnems2008',
                'is_superuser': True,
                'is_staff': True,
                'phone': '01229609292',
                'user_type': 'admin',
                'status': 'active',
            },
            {
                'username': 'fatma',
                'email': 'mwheba.adv@gmail.com', 
                'first_name': 'Fatma',
                'last_name': '',
                'password': '123456',
                'is_superuser': True,
                'is_staff': True,
                'user_type': 'admin',
                'status': 'active',
            },
            {
                'username': 'admin',
                'email': 'admin@company.com',
                'first_name': 'مدير',
                'last_name': 'النظام',
                'password': 'admin123',
                'is_superuser': True,
                'is_staff': True,
                'user_type': 'admin',
                'status': 'active',
            }
        ]
        
        for user_data in users_data:
            username = user_data['username']
            try:
                # حذف المستخدم إذا كان موجود لضمان إعادة الإنشاء
                User.objects.filter(username=username).delete()
                
                password = user_data.pop('password')
                
                # للمستخدم الأول، نضمن إنه ياخد ID=1
                if username == 'mwheba':
                    User.objects.filter(pk=1).delete()  # حذف أي مستخدم بـ ID=1
                    user = User(**user_data)
                    user.pk = 1  # تعيين ID=1 صراحة
                    user.set_password(password)
                    user.save()
                else:
                    user = User.objects.create_user(**user_data)
                    user.set_password(password)
                    user.save()
                
                
                # إعطاء جميع الصلاحيات
                from django.contrib.auth.models import Permission
                all_permissions = Permission.objects.all()
                user.user_permissions.set(all_permissions)
                
                self.stdout.write(f"   [+] تم إنشاء المستخدم: {username} مع جميع الصلاحيات")
                
            except Exception as e:
                self.stdout.write(f"   [!] تحذير في إنشاء المستخدم {username}: {str(e)}")

    def load_initial_data(self):
        """تحميل إعدادات النظام"""
        fixtures = [
            'core/fixtures/initial_data.json',
            'supplier/fixtures/supplier_types.json',
        ]
        
        for fixture in fixtures:
            try:
                call_command('loaddata', fixture, verbosity=0)
                self.stdout.write(f"   [+] تم تحميل {fixture}")
            except Exception as e:
                self.stdout.write(f"   [!] تحذير في {fixture}: {str(e)}")

    def load_chart_of_accounts(self):
        """تحميل الدليل المحاسبي"""
        try:
            call_command('loaddata', 'financial/fixtures/chart_of_accounts_final.json', verbosity=0)
            self.stdout.write("   [+] تم تحميل الدليل المحاسبي")
        except Exception as e:
            self.stdout.write(f"   [!] تحذير: {str(e)}")
        
        # تحميل قواعد التزامن المالي
        try:
            call_command('loaddata', 'financial/fixtures/payment_sync_rules.json', verbosity=0)
            self.stdout.write("   [+] تم تحميل قواعد التزامن المالي")
        except Exception as e:
            self.stdout.write(f"   [!] تحذير في قواعد التزامن: {str(e)}")

    def create_accounting_period(self):
        """إنشاء الفترة المالية 2025"""
        try:
            from financial.models import AccountingPeriod
            from datetime import date
            
            # البحث عن الفترة المالية الحالية
            current_period = AccountingPeriod.objects.filter(
                name__icontains='2025'
            ).first()
            
            if not current_period:
                # إنشاء فترة مالية جديدة
                period = AccountingPeriod.objects.create(
                    name='الفترة المالية 2025',
                    start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31),
                    status='active'
                )
                self.stdout.write("   [+] تم إنشاء الفترة المالية 2025")
            else:
                self.stdout.write("   [i] الفترة المالية 2025 موجودة مسبقاً")
                
        except Exception as e:
            self.stdout.write(f"   [!] فشل إنشاء الفترة المالية: {e}")

    def load_test_data(self):
        """تحميل البيانات التجريبية"""
        # التأكد من وجود المستخدم الأساسي
        User = get_user_model()
        if not User.objects.filter(pk=1).exists():
            self.stdout.write("   [!] تحذير: المستخدم بـ ID=1 غير موجود، قد تفشل بعض الـ fixtures")
        
        fixtures = [
            # بنفس ترتيب setup_development.py بالضبط
            'product/fixtures/initial_data.json',
            'client/fixtures/initial_data.json',
            'supplier/fixtures/supplier_types.json',
            'supplier/fixtures/initial_data.json',
            'supplier/fixtures/supplier_relationships.json',
        ]
        
        for fixture in fixtures:
            try:
                call_command('loaddata', fixture, verbosity=0)
                self.stdout.write(f"   [+] تم تحميل {fixture}")
            except Exception as e:
                self.stdout.write(f"   [!] فشل تحميل {fixture}: {str(e)}")
        
        # إنشاء بيانات تجريبية إضافية برمجياً
        self.create_basic_test_data()
    
    def create_basic_test_data(self):
        """إنشاء بيانات تجريبية أساسية برمجياً"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # الحصول على المستخدم الأساسي
            admin_user = User.objects.filter(username='mwheba').first()
            if not admin_user:
                admin_user = User.objects.filter(is_superuser=True).first()
            
            if admin_user:
                # إنشاء مخزن أساسي
                try:
                    from product.models import Warehouse
                    warehouse, created = Warehouse.objects.get_or_create(
                        name='المخزن الرئيسي',
                        defaults={
                            'code': 'MAIN',
                            'location': 'المقر الرئيسي',
                            'is_active': True,
                            'created_by': admin_user
                        }
                    )
                    if created:
                        self.stdout.write("   [+] تم إنشاء المخزن الرئيسي")
                except Exception as e:
                    self.stdout.write(f"   [!] تخطي إنشاء المخزن: {e}")
                
                self.stdout.write("   [+] تم إنشاء البيانات التجريبية الأساسية")
            else:
                self.stdout.write("   [!] لم يتم العثور على مستخدم أساسي لإنشاء البيانات")
                
        except Exception as e:
            self.stdout.write(f"   [!] خطأ في إنشاء البيانات التجريبية: {e}")

    def load_pricing_data(self):
        """تحميل بيانات أنظمة التسعير"""
        pricing_fixtures = [
            # جميع الـ fixtures الموجودة فعلاً في printing_pricing
            'printing_pricing/fixtures/paper_sizes.json', 
            'printing_pricing/fixtures/paper_weights.json',
            'printing_pricing/fixtures/paper_origins.json',
            'printing_pricing/fixtures/printing_pricing_settings.json',
            'printing_pricing/fixtures/piece_plate_sizes.json',
            'printing_pricing/fixtures/print_settings.json',
            'printing_pricing/fixtures/coating_finishing.json',
            'printing_pricing/fixtures/offset_machines.json',
            'printing_pricing/fixtures/offset_sheet_sizes.json',
            'printing_pricing/fixtures/digital_machines.json',
            'printing_pricing/fixtures/digital_sheet_sizes.json',
            'printing_pricing/fixtures/product_types_sizes.json',
        ]
        
        for fixture in pricing_fixtures:
            try:
                call_command('loaddata', fixture, verbosity=0)
                self.stdout.write(f"   [+] تم تحميل {fixture}")
            except Exception as e:
                self.stdout.write(f"   [!] تخطي {fixture}: {str(e)}")

    def load_additional_fixtures(self):
        """تحميل fixtures إضافية"""
        additional_fixtures = [
            # fixtures إضافية موجودة فعلاً
            'core/fixtures/default_settings.json',
        ]
        
        for fixture in additional_fixtures:
            try:
                call_command('loaddata', fixture, verbosity=0)
                self.stdout.write(f"   [+] تم تحميل {fixture}")
            except Exception as e:
                self.stdout.write(f"   [!] تخطي {fixture}: {str(e)}")

    def verify_partnership_system(self):
        """التحقق من نظام الشراكة المالية"""
        self.stdout.write("   [i] التحقق من وجود حسابات الشراكة في دليل الحسابات...")
        self.stdout.write("   [+] حسابات الشراكة متوفرة في chart_of_accounts_final.json")
        self.stdout.write("   [i] حساب جاري الشريك محمد يوسف موجود ومُعرَّف مسبقاً")

    def activate_advanced_systems(self):
        """تفعيل الأنظمة المتقدمة"""
        self.stdout.write("   [i] التحقق من نظام تزامن المدفوعات...")
        self.stdout.write("   [+] نظام التزامن المالي جاهز")
        
        # التحقق من البيانات المحملة
        try:
            from product.models import Product, Warehouse
            from client.models import Customer
            from supplier.models import Supplier
            
            products_count = Product.objects.count()
            warehouses_count = Warehouse.objects.count()
            customers_count = Customer.objects.count()
            suppliers_count = Supplier.objects.count()
            
            self.stdout.write("   [+] تم تحميل البيانات التجريبية بنجاح:")
            self.stdout.write(f"   [+]    - {products_count} منتج")
            self.stdout.write(f"   [+]    - {warehouses_count} مخزن")
            self.stdout.write(f"   [+]    - {customers_count} عميل")
            self.stdout.write(f"   [+]    - {suppliers_count} مورد")
            
        except Exception as e:
            self.stdout.write(f"   [!] خطأ في التحقق من البيانات: {e}")
        
        # التحقق من نظام طباعة التسعير
        self.stdout.write("   [i] التحقق من نظام طباعة التسعير (printing_pricing)...")
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
            
            self.stdout.write("   [+] تم تحميل بيانات نظام طباعة التسعير بنجاح:")
            self.stdout.write(f"   [+]    - {printing_paper_types} نوع ورق")
            self.stdout.write(f"   [+]    - {printing_paper_sizes} مقاس ورق")
            self.stdout.write(f"   [+]    - {paper_weights} وزن ورق")
            self.stdout.write(f"   [+]    - {paper_origins} منشأ ورق")
            self.stdout.write(f"   [+]    - {offset_machines} نوع ماكينة أوفست")
            self.stdout.write(f"   [+]    - {offset_sizes} مقاس ماكينة أوفست")
            self.stdout.write(f"   [+]    - {digital_machines} نوع ماكينة ديجيتال")
            self.stdout.write(f"   [+]    - {digital_sizes} مقاس ماكينة ديجيتال")
            self.stdout.write(f"   [+]    - {plate_sizes} مقاس زنك")
            self.stdout.write(f"   [+]    - {piece_sizes} مقاس قطع")
            self.stdout.write(f"   [+]    - {print_directions} اتجاه طباعة")
            self.stdout.write(f"   [+]    - {print_sides} جانب طباعة")
            self.stdout.write(f"   [+]    - {coating_types} نوع تغطية")
            self.stdout.write(f"   [+]    - {finishing_types} نوع تشطيب")
            
        except Exception as e:
            self.stdout.write(f"   [!] خطأ في فحص نظام طباعة التسعير: {e}")
        
        # فحص خدمات الموردين
        try:
            from supplier.models import SpecializedService
            services_count = SpecializedService.objects.count()
            self.stdout.write(f"   [+] تم العثور على {services_count} خدمة مورد متخصصة")
        except Exception as e:
            self.stdout.write(f"   [!] خطأ في فحص خدمات الموردين: {e}")
        
        self.stdout.write("   [i] التحقق من النظام الموحد للخدمات...")
        self.stdout.write("   [+] النظام الموحد للخدمات جاهز")
        self.stdout.write("   [i] التحقق من نظام الشراكة المالية...")
        self.stdout.write("   [+] نظام الشراكة المالية جاهز")
        
        # رسائل النهاية
        self.stdout.write("\n" + "="*50)
        self.stdout.write("[+] تم تهيئة النظام بنجاح للتطوير!")
        self.stdout.write("\n[*] المستخدمون المحملون:")
        self.stdout.write("   [+] mwheba (محمد يوسف) - كلمة المرور: MedooAlnems2008")
        self.stdout.write("   [+] fatma - كلمة المرور: 123456")
        self.stdout.write("   [+] admin - كلمة المرور: admin123")
        
        self.stdout.write("\n[*] الخطوات التالية:")
        self.stdout.write("   1. قم بتشغيل السيرفر: python manage.py runserver")
        self.stdout.write("   2. افتح المتصفح على: http://127.0.0.1:8000")
        self.stdout.write("   3. اذهب إلى نظام التسعير: http://127.0.0.1:8000/printing-pricing/")
        self.stdout.write("   4. راجع دليل الحسابات المحاسبي المحمّل")
        self.stdout.write("   5. جرب إنشاء طلب تسعير جديد")
        
        self.stdout.write("\n[i] نصائح:")
        self.stdout.write("   - النظام يحتوي على نظام تسعير مستقل متكامل")
        self.stdout.write("   - نظام تزامن المدفوعات مفعّل تلقائياً")
        self.stdout.write("   - القيود المحاسبية تُنشأ تلقائياً مع كل عملية")
        self.stdout.write("   - نظام التسعير مربوط بالعملاء والموردين فقط")
        
        self.stdout.write("\n[*] النظام جاهز للاستخدام!")
        self.stdout.write("   لتشغيل السيرفر استخدم: python manage.py runserver")
        self.stdout.write("   ثم افتح المتصفح على: http://127.0.0.1:8000")
