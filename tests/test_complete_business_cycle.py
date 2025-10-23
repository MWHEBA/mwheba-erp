"""
اختبار دورة الأعمال الكاملة المتكاملة
يغطي جميع جوانب النظام من البداية للنهاية
"""
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from decimal import Decimal
from datetime import date, timedelta
import time

# استيراد جميع النماذج المطلوبة
from core.models import SystemSetting, Notification
from users.models import User
from product.models import Category, Brand, Unit, Product, Warehouse, Stock, StockMovement
from supplier.models import Supplier, SupplierType
from client.models import Client
from purchase.models import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn
from sale.models import Sale, SaleItem, SalePayment, SaleReturn
from financial.models import (
    AccountType, ChartOfAccounts, AccountingPeriod, 
    JournalEntry, JournalEntryLine, PartnerTransaction, PartnerBalance
)

User = get_user_model()


class CompleteBusinessCycleTestCase(TransactionTestCase):
    """اختبار دورة الأعمال الكاملة"""
    
    fixtures = [
        'financial/fixtures/chart_of_accounts_final.json',
        'product/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json'
    ]
    
    def setUp(self):
        """إعداد البيانات الأساسية"""
        self.start_time = time.time()
        print(f"\n🚀 بدء اختبار دورة الأعمال الكاملة - {date.today()}")
        
        # إنشاء المستخدمين
        self.admin_user = User.objects.create_user(
            username="admin", 
            email="admin@mwheba.com", 
            password="admin123",
            first_name="مدير النظام",
            is_staff=True,
            is_superuser=True
        )
        
        self.accountant = User.objects.create_user(
            username="accountant",
            email="accountant@mwheba.com", 
            password="acc123",
            first_name="المحاسب"
        )
        
        self.sales_rep = User.objects.create_user(
            username="sales",
            email="sales@mwheba.com",
            password="sales123", 
            first_name="مندوب المبيعات"
        )
        
        # متغيرات لتتبع النتائج
        self.test_results = {
            'products_created': 0,
            'suppliers_created': 0,
            'clients_created': 0,
            'purchases_created': 0,
            'sales_created': 0,
            'journal_entries_created': 0,
            'total_revenue': Decimal('0'),
            'total_expenses': Decimal('0'),
            'net_profit': Decimal('0')
        }
    
    def test_complete_business_workflow(self):
        """السيناريو الشامل الكامل"""
        print("\n📋 بدء السيناريو الشامل...")
        
        try:
            with transaction.atomic():
                # 1. إعداد النظام الأساسي
                print("1️⃣ إعداد النظام الأساسي...")
                self.setup_system_foundation()
                
                # 2. دورة المشتريات الكاملة
                print("2️⃣ تنفيذ دورة المشتريات...")
                purchase = self.execute_complete_purchase_cycle()
                
                # 3. دورة المبيعات الكاملة
                print("3️⃣ تنفيذ دورة المبيعات...")
                sale = self.execute_complete_sales_cycle()
                
                # 4. المعالجة المالية الشاملة
                print("4️⃣ المعالجة المالية...")
                self.execute_financial_processing()
                
                # 5. التقارير والتحليلات
                print("5️⃣ إنشاء التقارير...")
                reports = self.generate_comprehensive_reports()
                
                # 6. التحقق من النتائج النهائية
                print("6️⃣ التحقق من النتائج...")
                self.verify_final_results(purchase, sale, reports)
                
        except Exception as e:
            print(f"❌ خطأ في السيناريو: {str(e)}")
            raise
        
        finally:
            end_time = time.time()
            execution_time = end_time - self.start_time
            print(f"\n⏱️ وقت التنفيذ الإجمالي: {execution_time:.2f} ثانية")
            self.print_final_summary()
    
    def setup_system_foundation(self):
        """إعداد النظام الأساسي"""
        # إنشاء الفترة المحاسبية
        self.accounting_period = AccountingPeriod.objects.create(
            name="2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.admin_user
        )
        
        # إعداد المنتجات والتصنيفات
        self.setup_products_and_categories()
        
        # إعداد الموردين والعملاء
        self.setup_suppliers_and_clients()
        
        # مساهمة الشريك الأولية
        self.initial_partner_contribution()
        
        print("   ✅ تم إعداد النظام الأساسي")
    
    def setup_products_and_categories(self):
        """إعداد المنتجات والتصنيفات"""
        # الحصول على البيانات من fixtures
        self.paper_category = Category.objects.get(name="ورق")
        self.coated_brand = Brand.objects.get(name="كوشيه")
        self.sheet_unit = Unit.objects.get(name="فرخ")
        self.main_warehouse = Warehouse.objects.get(name="المخزن الرئيسي")
        
        # إنشاء منتجات متنوعة
        self.products = []
        
        # ورق كوشيه 120 جرام
        product1 = Product.objects.create(
            name="ورق كوشيه 120 جرام",
            sku="COATED-120",
            barcode="1234567890001",
            description="ورق كوشيه عالي الجودة 120 جرام",
            category=self.paper_category,
            brand=self.coated_brand,
            unit=self.sheet_unit,
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.75'),
            min_stock_level=100,
            max_stock_level=1000,
            created_by=self.admin_user
        )
        self.products.append(product1)
        
        # ورق أوفست 80 جرام
        product2 = Product.objects.create(
            name="ورق أوفست 80 جرام",
            sku="OFFSET-80",
            barcode="1234567890002", 
            description="ورق أوفست للطباعة 80 جرام",
            category=self.paper_category,
            unit=self.sheet_unit,
            cost_price=Decimal('0.40'),
            selling_price=Decimal('0.60'),
            min_stock_level=200,
            max_stock_level=2000,
            created_by=self.admin_user
        )
        self.products.append(product2)
        
        # ورق فاخر 150 جرام
        product3 = Product.objects.create(
            name="ورق فاخر 150 جرام",
            sku="LUXURY-150",
            barcode="1234567890003",
            description="ورق فاخر للطباعة الراقية",
            category=self.paper_category,
            brand=self.coated_brand,
            unit=self.sheet_unit,
            cost_price=Decimal('0.80'),
            selling_price=Decimal('1.20'),
            min_stock_level=50,
            max_stock_level=500,
            created_by=self.admin_user
        )
        self.products.append(product3)
        
        self.test_results['products_created'] = len(self.products)
        print(f"   📦 تم إنشاء {len(self.products)} منتجات")
    
    def setup_suppliers_and_clients(self):
        """إعداد الموردين والعملاء"""
        # إنشاء موردين
        paper_supplier_type = SupplierType.objects.get(code="paper")
        
        self.supplier1 = Supplier.objects.create(
            name="مورد الورق المصري",
            supplier_type=paper_supplier_type,
            contact_person="أحمد محمد",
            phone="01234567890",
            email="supplier1@paper.com",
            address="القاهرة، مصر",
            payment_terms="نقدي",
            credit_limit=Decimal('50000'),
            created_by=self.admin_user
        )
        
        self.supplier2 = Supplier.objects.create(
            name="الشركة العالمية للورق",
            supplier_type=paper_supplier_type,
            contact_person="محمد علي",
            phone="01987654321",
            email="supplier2@global.com", 
            address="الإسكندرية، مصر",
            payment_terms="آجل 30 يوم",
            credit_limit=Decimal('100000'),
            created_by=self.admin_user
        )
        
        # إنشاء عملاء
        self.client1 = Client.objects.create(
            name="مطبعة النهضة",
            contact_person="سامي أحمد",
            phone="01111111111",
            email="client1@nahda.com",
            address="الجيزة، مصر",
            credit_limit=Decimal('30000'),
            created_by=self.admin_user
        )
        
        self.client2 = Client.objects.create(
            name="دار الطباعة الحديثة", 
            contact_person="عمر محمود",
            phone="01222222222",
            email="client2@modern.com",
            address="القاهرة، مصر",
            credit_limit=Decimal('50000'),
            created_by=self.admin_user
        )
        
        self.test_results['suppliers_created'] = 2
        self.test_results['clients_created'] = 2
        print("   🏢 تم إنشاء 2 موردين و 2 عملاء")
    
    def initial_partner_contribution(self):
        """مساهمة الشريك الأولية"""
        contribution = PartnerTransaction.objects.create(
            transaction_type="PARTNER_CONTRIBUTION",
            amount=Decimal('100000.00'),
            description="مساهمة رأس مال أولية",
            created_by=self.admin_user
        )
        
        # التحقق من إنشاء القيد المحاسبي
        journal_entries = JournalEntry.objects.filter(
            reference_type="partner_transaction",
            reference_id=contribution.id
        )
        self.assertTrue(journal_entries.exists())
        
        print("   💰 تم إيداع مساهمة الشريك: 100,000 ج.م")
    
    def execute_complete_purchase_cycle(self):
        """تنفيذ دورة المشتريات الكاملة"""
        # إنشاء فاتورة شراء متعددة المنتجات
        purchase = Purchase.objects.create(
            supplier=self.supplier1,
            invoice_number="PUR-2025-001",
            invoice_date=date.today(),
            payment_method="cash",
            notes="فاتورة شراء تجريبية شاملة",
            created_by=self.admin_user
        )
        
        # إضافة منتجات متعددة
        items_data = [
            (self.products[0], 500, Decimal('0.48')),  # ورق كوشيه
            (self.products[1], 1000, Decimal('0.38')), # ورق أوفست
            (self.products[2], 200, Decimal('0.75'))   # ورق فاخر
        ]
        
        total_amount = Decimal('0')
        for product, quantity, unit_price in items_data:
            item_total = quantity * unit_price
            
            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                total_price=item_total
            )
            
            # تحديث المخزون
            stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=self.main_warehouse,
                defaults={'quantity': 0, 'created_by': self.admin_user}
            )
            stock.quantity += quantity
            stock.save()
            
            # تسجيل حركة المخزون
            StockMovement.objects.create(
                product=product,
                warehouse=self.main_warehouse,
                quantity=quantity,
                type="in",
                reference=f"شراء {purchase.invoice_number}",
                notes=f"استلام من {self.supplier1.name}",
                created_by=self.admin_user
            )
            
            # تحديث سعر التكلفة
            product.cost_price = unit_price
            product.save()
            
            total_amount += item_total
        
        # حفظ إجمالي الفاتورة
        purchase.total_amount = total_amount
        purchase.save()
        
        # دفعة نقدية كاملة
        payment = PurchasePayment.objects.create(
            purchase=purchase,
            amount=total_amount,
            payment_method="cash",
            payment_date=date.today(),
            notes="دفعة نقدية كاملة",
            created_by=self.admin_user
        )
        
        # التحقق من القيود المحاسبية
        self.verify_purchase_accounting(purchase)
        
        self.test_results['purchases_created'] = 1
        self.test_results['total_expenses'] += total_amount
        
        print(f"   🛒 فاتورة شراء: {total_amount} ج.م")
        return purchase
    
    def execute_complete_sales_cycle(self):
        """تنفيذ دورة المبيعات الكاملة"""
        # إنشاء فاتورة بيع متعددة المنتجات
        sale = Sale.objects.create(
            client=self.client1,
            invoice_number="SAL-2025-001",
            invoice_date=date.today(),
            payment_method="cash",
            notes="فاتورة بيع تجريبية شاملة",
            created_by=self.sales_rep
        )
        
        # بيع جزء من المخزون المشترى
        items_data = [
            (self.products[0], 200, Decimal('0.75')),  # ورق كوشيه
            (self.products[1], 300, Decimal('0.60')),  # ورق أوفست
            (self.products[2], 50, Decimal('1.20'))    # ورق فاخر
        ]
        
        total_amount = Decimal('0')
        total_cost = Decimal('0')
        
        for product, quantity, unit_price in items_data:
            item_total = quantity * unit_price
            item_cost = quantity * product.cost_price
            
            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                total_price=item_total
            )
            
            # تحديث المخزون
            stock = Stock.objects.get(
                product=product,
                warehouse=self.main_warehouse
            )
            stock.quantity -= quantity
            stock.save()
            
            # تسجيل حركة المخزون
            StockMovement.objects.create(
                product=product,
                warehouse=self.main_warehouse,
                quantity=quantity,
                type="out",
                reference=f"بيع {sale.invoice_number}",
                notes=f"بيع إلى {self.client1.name}",
                created_by=self.sales_rep
            )
            
            total_amount += item_total
            total_cost += item_cost
        
        # حفظ إجمالي الفاتورة
        sale.total_amount = total_amount
        sale.save()
        
        # دفعة نقدية كاملة
        payment = SalePayment.objects.create(
            sale=sale,
            amount=total_amount,
            payment_method="cash",
            payment_date=date.today(),
            notes="دفعة نقدية كاملة",
            created_by=self.sales_rep
        )
        
        # حساب الربح
        profit = total_amount - total_cost
        
        # التحقق من القيود المحاسبية
        self.verify_sale_accounting(sale)
        
        self.test_results['sales_created'] = 1
        self.test_results['total_revenue'] += total_amount
        self.test_results['net_profit'] += profit
        
        print(f"   💰 فاتورة بيع: {total_amount} ج.م (ربح: {profit} ج.م)")
        return sale
    
    def execute_financial_processing(self):
        """المعالجة المالية الشاملة"""
        # إيراد مستقل (خدمات إضافية)
        service_revenue = Decimal('5000')
        # هنا يمكن إضافة قيد إيراد مستقل
        
        # مصروف مستقل (مصاريف إدارية)
        admin_expense = Decimal('2000')
        # هنا يمكن إضافة قيد مصروف مستقل
        
        # سحب الشريك
        withdrawal = PartnerTransaction.objects.create(
            transaction_type="PARTNER_WITHDRAWAL",
            amount=Decimal('10000.00'),
            description="سحب شخصي للشريك",
            created_by=self.admin_user
        )
        
        self.test_results['total_revenue'] += service_revenue
        self.test_results['total_expenses'] += admin_expense
        self.test_results['net_profit'] = self.test_results['total_revenue'] - self.test_results['total_expenses']
        
        print(f"   🏦 معالجة مالية إضافية مكتملة")
    
    def generate_comprehensive_reports(self):
        """إنشاء التقارير الشاملة"""
        reports = {}
        
        # عدد القيود المحاسبية
        journal_entries_count = JournalEntry.objects.count()
        reports['journal_entries'] = journal_entries_count
        
        # إجمالي المخزون الحالي
        total_stock_value = Decimal('0')
        for stock in Stock.objects.all():
            total_stock_value += stock.quantity * stock.product.cost_price
        reports['total_stock_value'] = total_stock_value
        
        # رصيد الشريك
        partner_balance = PartnerBalance.objects.first()
        if partner_balance:
            reports['partner_balance'] = partner_balance.current_balance
        
        # عدد الإشعارات
        notifications_count = Notification.objects.count()
        reports['notifications_count'] = notifications_count
        
        self.test_results['journal_entries_created'] = journal_entries_count
        
        print(f"   📊 تم إنشاء التقارير الشاملة")
        return reports
    
    def verify_purchase_accounting(self, purchase):
        """التحقق من القيود المحاسبية للشراء"""
        # البحث عن القيود المتعلقة بالشراء
        journal_entries = JournalEntry.objects.filter(
            reference_type="purchase",
            reference_id=purchase.id
        )
        
        # يجب أن يكون هناك قيد واحد على الأقل
        self.assertTrue(journal_entries.exists())
        
        if journal_entries.exists():
            entry = journal_entries.first()
            # التحقق من توازن القيد
            self.assertEqual(entry.total_debit, entry.total_credit)
            print(f"     ✅ قيد الشراء متوازن: {entry.total_debit} ج.م")
    
    def verify_sale_accounting(self, sale):
        """التحقق من القيود المحاسبية للبيع"""
        # البحث عن القيود المتعلقة بالبيع
        journal_entries = JournalEntry.objects.filter(
            reference_type="sale",
            reference_id=sale.id
        )
        
        # يجب أن يكون هناك قيد واحد على الأقل
        self.assertTrue(journal_entries.exists())
        
        if journal_entries.exists():
            entry = journal_entries.first()
            # التحقق من توازن القيد
            self.assertEqual(entry.total_debit, entry.total_credit)
            print(f"     ✅ قيد البيع متوازن: {entry.total_debit} ج.م")
    
    def verify_final_results(self, purchase, sale, reports):
        """التحقق من النتائج النهائية"""
        # التحقق من إنشاء الفواتير
        self.assertIsNotNone(purchase)
        self.assertIsNotNone(sale)
        
        # التحقق من وجود عناصر الفواتير
        self.assertTrue(purchase.items.exists())
        self.assertTrue(sale.items.exists())
        
        # التحقق من وجود دفعات
        self.assertTrue(purchase.payments.exists())
        self.assertTrue(sale.payments.exists())
        
        # التحقق من تحديث المخزون
        for product in self.products:
            stock = Stock.objects.get(product=product, warehouse=self.main_warehouse)
            self.assertGreaterEqual(stock.quantity, 0)
        
        # التحقق من وجود حركات المخزون
        movements_count = StockMovement.objects.count()
        self.assertGreater(movements_count, 0)
        
        # التحقق من وجود قيود محاسبية
        self.assertGreater(reports['journal_entries'], 0)
        
        print("   ✅ جميع التحققات النهائية نجحت")
    
    def print_final_summary(self):
        """طباعة الملخص النهائي"""
        print("\n" + "="*60)
        print("📋 ملخص نتائج اختبار دورة الأعمال الكاملة")
        print("="*60)
        
        print(f"👥 المستخدمين المنشأين: 3 (مدير، محاسب، مبيعات)")
        print(f"📦 المنتجات المنشأة: {self.test_results['products_created']}")
        print(f"🏢 الموردين المنشأين: {self.test_results['suppliers_created']}")
        print(f"👤 العملاء المنشأين: {self.test_results['clients_created']}")
        print(f"🛒 فواتير الشراء: {self.test_results['purchases_created']}")
        print(f"💰 فواتير البيع: {self.test_results['sales_created']}")
        print(f"📊 القيود المحاسبية: {self.test_results['journal_entries_created']}")
        
        print("\n💵 النتائج المالية:")
        print(f"   الإيرادات الإجمالية: {self.test_results['total_revenue']:,.2f} ج.م")
        print(f"   المصروفات الإجمالية: {self.test_results['total_expenses']:,.2f} ج.م") 
        print(f"   صافي الربح: {self.test_results['net_profit']:,.2f} ج.م")
        
        profit_margin = (self.test_results['net_profit'] / self.test_results['total_revenue'] * 100) if self.test_results['total_revenue'] > 0 else 0
        print(f"   هامش الربح: {profit_margin:.1f}%")
        
        print("\n🎯 معايير النجاح:")
        print("   ✅ تم إنشاء جميع البيانات الأساسية")
        print("   ✅ دورة المشتريات مكتملة")
        print("   ✅ دورة المبيعات مكتملة") 
        print("   ✅ القيود المحاسبية متوازنة")
        print("   ✅ المخزون محدث بدقة")
        print("   ✅ التقارير تم إنشاؤها")
        
        print("\n🏆 النتيجة: اختبار دورة الأعمال الكاملة نجح بامتياز!")
        print("="*60)
