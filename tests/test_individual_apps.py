"""
اختبارات التطبيقات الفردية لنظام MWHEBA ERP
يغطي كل تطبيق منفرداً بجميع وظائفه الأساسية
"""

import time
import json
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.test import TestCase, TransactionTestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

# Core imports
from core.models import SystemSetting, DashboardStat, Notification

# Users imports  
User = get_user_model()

# Product imports
from product.models import (
    Category, Brand, Product, ProductImage, 
    StockMovement, InventoryTransaction
)

# Supplier imports
from supplier.models import (
    SupplierType, SupplierTypeSettings, Supplier,
    PaperServiceDetails, OffsetPrintingDetails,
    DigitalPrintingDetails, PlateServiceDetails
)

# Client imports
from client.models import Client, ClientAccount, ClientTransaction

# Purchase imports
from purchase.models import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn

# Sale imports  
from sale.models import Sale, SaleItem, SalePayment, SaleReturn

# Financial imports
from financial.models import (
    ChartOfAccounts, JournalEntry, AccountingPeriod,
    EnhancedBalance, PartnerTransaction, PartnerBalance
)

# Printing Pricing imports
from printing_pricing.models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    OffsetMachineType, DigitalMachineType, PieceSize, PlateSize
)


class CoreAppTestCase(TestCase):
    """اختبارات تطبيق Core"""
    
    fixtures = ['core/fixtures/initial_data.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@test.com", 
            password="admin123",
            is_staff=True,
            is_superuser=True
        )
        
    def test_system_settings_crud(self):
        """اختبار إعدادات النظام"""
        print("🔧 اختبار إعدادات النظام...")
        
        # إنشاء إعداد جديد
        setting = SystemSetting.objects.create(
            key="company_name",
            value="شركة مهيبة للطباعة",
            description="اسم الشركة"
        )
        
        self.assertEqual(setting.key, "company_name")
        self.assertEqual(setting.value, "شركة مهيبة للطباعة")
        
        # تعديل الإعداد
        setting.value = "مهيبة للطباعة والنشر"
        setting.save()
        
        updated_setting = SystemSetting.objects.get(key="company_name")
        self.assertEqual(updated_setting.value, "مهيبة للطباعة والنشر")
        
        # حذف الإعداد
        setting.delete()
        self.assertFalse(SystemSetting.objects.filter(key="company_name").exists())
        
    def test_notifications_system(self):
        """اختبار نظام الإشعارات"""
        print("🔔 اختبار نظام الإشعارات...")
        
        # إنشاء إشعار
        notification = Notification.objects.create(
            title="إشعار تجريبي",
            message="هذا إشعار للاختبار",
            notification_type="info",
            user=self.admin_user
        )
        
        self.assertFalse(notification.is_read)
        
        # وضع علامة مقروء
        notification.mark_as_read()
        self.assertTrue(notification.is_read)
        
        # إحصائيات الإشعارات
        unread_count = Notification.objects.filter(
            user=self.admin_user, 
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)


class UsersAppTestCase(TestCase):
    """اختبارات تطبيق Users"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="admin123", 
            is_staff=True,
            is_superuser=True
        )
        
    def test_user_management(self):
        """اختبار إدارة المستخدمين"""
        print("👥 اختبار إدارة المستخدمين...")
        
        # إنشاء مستخدم جديد
        user = User.objects.create_user(
            username="testuser",
            email="test@test.com",
            password="test123",
            first_name="مستخدم",
            last_name="تجريبي"
        )
        
        self.assertEqual(user.username, "testuser")
        self.assertTrue(user.check_password("test123"))
        
        # تعديل بيانات المستخدم
        user.first_name = "أحمد"
        user.last_name = "محمد"
        user.save()
        
        updated_user = User.objects.get(username="testuser")
        self.assertEqual(updated_user.first_name, "أحمد")
        
        # تعطيل المستخدم
        user.is_active = False
        user.save()
        self.assertFalse(user.is_active)
        
    def test_permissions_and_groups(self):
        """اختبار الصلاحيات والمجموعات"""
        print("🔐 اختبار الصلاحيات والمجموعات...")
        
        # إنشاء مجموعة
        group = Group.objects.create(name="محاسبين")
        
        # إضافة صلاحيات للمجموعة
        permissions = Permission.objects.filter(
            content_type__app_label='financial'
        )[:3]
        group.permissions.set(permissions)
        
        # إنشاء مستخدم وإضافته للمجموعة
        user = User.objects.create_user(
            username="accountant",
            password="acc123"
        )
        user.groups.add(group)
        
        # التحقق من الصلاحيات
        self.assertTrue(user.groups.filter(name="محاسبين").exists())


class ProductAppTestCase(TestCase):
    """اختبارات تطبيق Product"""
    
    fixtures = ['product/fixtures/initial_data.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
    def test_category_management(self):
        """اختبار إدارة التصنيفات"""
        print("📂 اختبار إدارة التصنيفات...")
        
        # إنشاء تصنيف رئيسي
        main_category = Category.objects.create(
            name="ورق طباعة",
            description="جميع أنواع ورق الطباعة"
        )
        
        # إنشاء تصنيف فرعي
        sub_category = Category.objects.create(
            name="ورق كوشيه",
            description="ورق كوشيه عالي الجودة",
            parent=main_category
        )
        
        self.assertEqual(sub_category.parent, main_category)
        self.assertIn(sub_category, main_category.children.all())
        
    def test_product_lifecycle(self):
        """اختبار دورة حياة المنتج"""
        print("📦 اختبار دورة حياة المنتج...")
        
        # إنشاء تصنيف
        category = Category.objects.create(name="ورق A4")
        
        # إنشاء علامة تجارية
        brand = Brand.objects.create(
            name="Double A",
            description="علامة تجارية عالمية"
        )
        
        # إنشاء منتج
        product = Product.objects.create(
            name="ورق A4 80 جرام",
            category=category,
            brand=brand,
            sku="DA-A4-80",
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.75'),
            minimum_stock=100,
            maximum_stock=1000
        )
        
        self.assertEqual(product.current_stock, 0)
        self.assertEqual(product.cost_price, Decimal('0.50'))
        
        # إضافة مخزون
        product.add_stock(500, "استلام أولي")
        self.assertEqual(product.current_stock, 500)
        
        # خصم مخزون
        product.deduct_stock(100, "بيع")
        self.assertEqual(product.current_stock, 400)


class SupplierAppTestCase(TestCase):
    """اختبارات تطبيق Supplier"""
    
    fixtures = [
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
    def test_supplier_management(self):
        """اختبار إدارة الموردين"""
        print("🏭 اختبار إدارة الموردين...")
        
        # الحصول على نوع مورد
        supplier_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
        # إنشاء مورد
        supplier = Supplier.objects.create(
            name="مورد الورق المصري",
            supplier_type=supplier_type,
            email="supplier@paper.com",
            phone="01234567890",
            address="القاهرة، مصر"
        )
        
        self.assertEqual(supplier.name, "مورد الورق المصري")
        self.assertEqual(supplier.supplier_type, supplier_type)
        
    def test_specialized_services(self):
        """اختبار الخدمات المتخصصة"""
        print("⚙️ اختبار الخدمات المتخصصة...")
        
        # إنشاء مورد ورق
        supplier_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
        supplier = Supplier.objects.create(
            name="مورد ورق",
            supplier_type=supplier_type
        )
        
        # إضافة خدمة ورق
        paper_service = PaperServiceDetails.objects.create(
            supplier=supplier,
            paper_type="كوشيه",
            gsm=120,
            sheet_size="70.00x100.00",
            country_of_origin="مصر",
            price_per_sheet=Decimal('2.50')
        )
        
        self.assertEqual(paper_service.paper_type, "كوشيه")
        self.assertEqual(paper_service.gsm, 120)


class FinancialAppTestCase(TestCase):
    """اختبارات تطبيق Financial"""
    
    fixtures = ['financial/fixtures/chart_of_accounts_final.json']
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
    def test_chart_of_accounts(self):
        """اختبار دليل الحسابات"""
        print("📊 اختبار دليل الحسابات...")
        
        # إنشاء حساب جديد
        account = ChartOfAccounts.objects.create(
            account_code="1001",
            account_name="صندوق فرعي",
            account_type="asset",
            parent_account=ChartOfAccounts.objects.filter(
                account_name__contains="الصندوق"
            ).first()
        )
        
        self.assertEqual(account.account_code, "1001")
        self.assertEqual(account.account_type, "asset")
        
    def test_journal_entries(self):
        """اختبار القيود المحاسبية"""
        print("📝 اختبار القيود المحاسبية...")
        
        # الحصول على حسابات
        cash_account = ChartOfAccounts.objects.filter(
            account_name__contains="الصندوق"
        ).first()
        
        sales_account = ChartOfAccounts.objects.filter(
            account_name__contains="المبيعات"
        ).first()
        
        if cash_account and sales_account:
            # إنشاء قيد محاسبي
            entry = JournalEntry.objects.create(
                account=cash_account,
                debit_amount=Decimal('1000.00'),
                credit_amount=Decimal('0.00'),
                description="بيع نقدي",
                entry_date=date.today()
            )
            
            # قيد مقابل
            JournalEntry.objects.create(
                account=sales_account,
                debit_amount=Decimal('0.00'),
                credit_amount=Decimal('1000.00'),
                description="بيع نقدي",
                entry_date=date.today()
            )
            
            self.assertEqual(entry.debit_amount, Decimal('1000.00'))
            
    def test_partner_transactions(self):
        """اختبار معاملات الشريك"""
        print("🤝 اختبار معاملات الشريك...")
        
        # مساهمة الشريك
        contribution = PartnerTransaction.objects.create(
            transaction_type="PARTNER_CONTRIBUTION",
            amount=Decimal('10000.00'),
            description="مساهمة رأس مال أولية"
        )
        
        self.assertEqual(contribution.amount, Decimal('10000.00'))
        self.assertEqual(contribution.transaction_type, "PARTNER_CONTRIBUTION")


class PrintingPricingAppTestCase(TestCase):
    """اختبارات تطبيق Printing Pricing"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123"
        )
        
    def test_paper_settings(self):
        """اختبار إعدادات الورق"""
        print("📄 اختبار إعدادات الورق...")
        
        # إنشاء نوع ورق
        paper_type = PaperType.objects.create(
            name="كوشيه",
            description="ورق كوشيه عالي الجودة"
        )
        
        # إنشاء مقاس ورق
        paper_size = PaperSize.objects.create(
            name="A4",
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            unit="cm"
        )
        
        # إنشاء وزن ورق
        paper_weight = PaperWeight.objects.create(
            weight=120,
            unit="gsm"
        )
        
        self.assertEqual(paper_type.name, "كوشيه")
        self.assertEqual(paper_size.width, Decimal('21.0'))
        self.assertEqual(paper_weight.weight, 120)
        
    def test_machine_settings(self):
        """اختبار إعدادات الماكينات"""
        print("🖨️ اختبار إعدادات الماكينات...")
        
        # إنشاء نوع ماكينة أوفست
        offset_machine = OffsetMachineType.objects.create(
            name="Heidelberg SM52",
            code="sm52",
            manufacturer="Heidelberg"
        )
        
        # إنشاء نوع ماكينة ديجيتال
        digital_machine = DigitalMachineType.objects.create(
            name="HP Indigo 7900",
            code="hp7900", 
            manufacturer="HP"
        )
        
        self.assertEqual(offset_machine.name, "Heidelberg SM52")
        self.assertEqual(digital_machine.manufacturer, "HP")


# تشغيل جميع الاختبارات
if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests([
        "tests.test_individual_apps"
    ])
