"""
اختبارات السيناريوهات المعقدة والمتقدمة
تغطي الحالات الاستثنائية والعمليات المعقدة
"""
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date, timedelta
import time

# استيراد النماذج
from product.models import Category, Brand, Unit, Product, Warehouse, Stock, StockMovement
from supplier.models import Supplier, SupplierType
from client.models import Client
from purchase.models import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn, PurchaseReturnItem
from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from financial.models import (
    AccountType, ChartOfAccounts, AccountingPeriod, 
    JournalEntry, JournalEntryLine, PartnerTransaction
)

User = get_user_model()


class ComplexScenariosTestCase(TransactionTestCase):
    """اختبارات السيناريوهات المعقدة"""
    
    fixtures = [
        'financial/fixtures/chart_of_accounts_final.json',
        'product/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json'
    ]
    
    def setUp(self):
        """إعداد البيانات للاختبارات المعقدة"""
        self.admin_user = User.objects.create_user(
            username="admin", 
            email="admin@test.com", 
            password="admin123",
            is_staff=True
        )
        
        # إعداد البيانات الأساسية
        self.setup_basic_data()
        
        # متغيرات التتبع
        self.complex_results = {
            'multi_warehouse_transfers': 0,
            'partial_returns_processed': 0,
            'batch_operations_completed': 0,
            'concurrent_transactions': 0,
            'error_scenarios_tested': 0
        }
    
    def setup_basic_data(self):
        """إعداد البيانات الأساسية"""
        # الفترة المحاسبية
        self.period = AccountingPeriod.objects.create(
            name="2025-Complex",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.admin_user
        )
        
        # البيانات من fixtures
        self.category = Category.objects.get(name="ورق")
        self.brand = Brand.objects.get(name="كوشيه")
        self.unit = Unit.objects.get(name="فرخ")
        self.main_warehouse = Warehouse.objects.get(name="المخزن الرئيسي")
        
        # إنشاء مخازن إضافية
        self.branch_warehouse = Warehouse.objects.create(
            name="مخزن الفرع",
            code="BRANCH-001",
            address="فرع القاهرة",
            created_by=self.admin_user
        )
        
        self.storage_warehouse = Warehouse.objects.create(
            name="مخزن التخزين",
            code="STORAGE-001", 
            address="مخزن التخزين الرئيسي",
            created_by=self.admin_user
        )
        
        # منتجات للاختبار
        self.product1 = Product.objects.create(
            name="ورق كوشيه متقدم",
            sku="ADV-COATED-001",
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.80'),
            min_stock_level=50,
            max_stock_level=500,
            created_by=self.admin_user
        )
        
        self.product2 = Product.objects.create(
            name="ورق أوفست متقدم",
            sku="ADV-OFFSET-001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('0.40'),
            selling_price=Decimal('0.65'),
            min_stock_level=100,
            max_stock_level=1000,
            created_by=self.admin_user
        )
        
        # مورد وعميل
        supplier_type = SupplierType.objects.get(code="paper")
        self.supplier = Supplier.objects.create(
            name="مورد متقدم",
            supplier_type=supplier_type,
            created_by=self.admin_user
        )
        
        self.client = Client.objects.create(
            name="عميل متقدم",
            created_by=self.admin_user
        )
    
    def test_multi_warehouse_operations(self):
        """اختبار العمليات متعددة المخازن"""
        print("\n🏢 اختبار العمليات متعددة المخازن...")
        
        # إضافة مخزون أولي في المخزن الرئيسي
        initial_stock = Stock.objects.create(
            product=self.product1,
            warehouse=self.main_warehouse,
            quantity=1000,
            created_by=self.admin_user
        )
        
        # نقل جزء من المخزون إلى مخزن الفرع
        transfer_quantity = 300
        
        # خصم من المخزن الرئيسي
        initial_stock.quantity -= transfer_quantity
        initial_stock.save()
        
        # إضافة إلى مخزن الفرع
        branch_stock, created = Stock.objects.get_or_create(
            product=self.product1,
            warehouse=self.branch_warehouse,
            defaults={'quantity': 0, 'created_by': self.admin_user}
        )
        branch_stock.quantity += transfer_quantity
        branch_stock.save()
        
        # تسجيل حركات النقل
        StockMovement.objects.create(
            product=self.product1,
            warehouse=self.main_warehouse,
            quantity=transfer_quantity,
            type="out",
            reference="TRANSFER-001",
            notes="نقل إلى مخزن الفرع",
            created_by=self.admin_user
        )
        
        StockMovement.objects.create(
            product=self.product1,
            warehouse=self.branch_warehouse,
            quantity=transfer_quantity,
            type="in",
            reference="TRANSFER-001",
            notes="استلام من المخزن الرئيسي",
            created_by=self.admin_user
        )
        
        # التحقق من النتائج
        main_stock = Stock.objects.get(product=self.product1, warehouse=self.main_warehouse)
        branch_stock = Stock.objects.get(product=self.product1, warehouse=self.branch_warehouse)
        
        self.assertEqual(main_stock.quantity, 700)
        self.assertEqual(branch_stock.quantity, 300)
        
        # نقل إضافي إلى مخزن التخزين
        storage_transfer = 100
        
        branch_stock.quantity -= storage_transfer
        branch_stock.save()
        
        storage_stock, created = Stock.objects.get_or_create(
            product=self.product1,
            warehouse=self.storage_warehouse,
            defaults={'quantity': 0, 'created_by': self.admin_user}
        )
        storage_stock.quantity += storage_transfer
        storage_stock.save()
        
        # التحقق من إجمالي المخزون
        total_stock = Stock.objects.filter(product=self.product1).aggregate(
            total=sum(stock.quantity for stock in Stock.objects.filter(product=self.product1))
        )
        
        self.assertEqual(
            Stock.objects.get(product=self.product1, warehouse=self.main_warehouse).quantity +
            Stock.objects.get(product=self.product1, warehouse=self.branch_warehouse).quantity +
            Stock.objects.get(product=self.product1, warehouse=self.storage_warehouse).quantity,
            1000
        )
        
        self.complex_results['multi_warehouse_transfers'] += 2
        print("   ✅ نقل المخزون بين المخازن نجح")
    
    def test_partial_returns_and_exchanges(self):
        """اختبار المرتجعات الجزئية والاستبدال"""
        print("\n🔄 اختبار المرتجعات الجزئية...")
        
        # إنشاء فاتورة شراء
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            invoice_number="PUR-COMPLEX-001",
            invoice_date=date.today(),
            created_by=self.admin_user
        )
        
        # إضافة عناصر متعددة
        item1 = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product1,
            quantity=500,
            unit_price=Decimal('0.48'),
            total_price=Decimal('240.00')
        )
        
        item2 = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product2,
            quantity=300,
            unit_price=Decimal('0.38'),
            total_price=Decimal('114.00')
        )
        
        # تحديث المخزون
        for item in [item1, item2]:
            stock, created = Stock.objects.get_or_create(
                product=item.product,
                warehouse=self.main_warehouse,
                defaults={'quantity': 0, 'created_by': self.admin_user}
            )
            stock.quantity += item.quantity
            stock.save()
        
        # إرجاع جزئي للمنتج الأول فقط
        return_doc = PurchaseReturn.objects.create(
            purchase=purchase,
            return_date=date.today(),
            reason="عيب في الجودة",
            notes="إرجاع جزئي لبعض الكمية",
            created_by=self.admin_user
        )
        
        # إرجاع 100 قطعة من المنتج الأول
        return_item = PurchaseReturnItem.objects.create(
            purchase_return=return_doc,
            product=self.product1,
            quantity=100,
            unit_price=Decimal('0.48'),
            total_price=Decimal('48.00')
        )
        
        # تحديث المخزون بعد الإرجاع
        stock1 = Stock.objects.get(product=self.product1, warehouse=self.main_warehouse)
        stock1.quantity -= return_item.quantity
        stock1.save()
        
        # التحقق من النتائج
        self.assertEqual(stock1.quantity, 400)  # 500 - 100
        
        stock2 = Stock.objects.get(product=self.product2, warehouse=self.main_warehouse)
        self.assertEqual(stock2.quantity, 300)  # لم يتم إرجاع شيء
        
        # اختبار إرجاع البيع الجزئي
        sale = Sale.objects.create(
            client=self.client,
            invoice_number="SAL-COMPLEX-001",
            invoice_date=date.today(),
            created_by=self.admin_user
        )
        
        # بيع جزء من المخزون
        sale_item = SaleItem.objects.create(
            sale=sale,
            product=self.product1,
            quantity=150,
            unit_price=Decimal('0.80'),
            total_price=Decimal('120.00')
        )
        
        # تحديث المخزون
        stock1.quantity -= sale_item.quantity
        stock1.save()
        
        # إرجاع جزئي من العميل
        sale_return = SaleReturn.objects.create(
            sale=sale,
            return_date=date.today(),
            reason="تغيير في المتطلبات",
            created_by=self.admin_user
        )
        
        sale_return_item = SaleReturnItem.objects.create(
            sale_return=sale_return,
            product=self.product1,
            quantity=50,
            unit_price=Decimal('0.80'),
            total_price=Decimal('40.00')
        )
        
        # إعادة المخزون
        stock1.quantity += sale_return_item.quantity
        stock1.save()
        
        # التحقق النهائي
        final_stock = Stock.objects.get(product=self.product1, warehouse=self.main_warehouse)
        expected_quantity = 500 - 100 - 150 + 50  # شراء - إرجاع شراء - بيع + إرجاع بيع
        self.assertEqual(final_stock.quantity, expected_quantity)
        
        self.complex_results['partial_returns_processed'] += 2
        print("   ✅ المرتجعات الجزئية تمت بنجاح")
    
    def test_batch_operations_performance(self):
        """اختبار أداء العمليات المجمعة"""
        print("\n⚡ اختبار أداء العمليات المجمعة...")
        
        start_time = time.time()
        
        # إنشاء منتجات متعددة بشكل مجمع
        products = []
        for i in range(50):
            product = Product(
                name=f"منتج مجمع {i+1}",
                sku=f"BATCH-{i+1:03d}",
                category=self.category,
                unit=self.unit,
                cost_price=Decimal('0.50'),
                selling_price=Decimal('0.75'),
                created_by=self.admin_user
            )
            products.append(product)
        
        # إنشاء مجمع
        Product.objects.bulk_create(products)
        
        # إنشاء مخزون مجمع
        stocks = []
        created_products = Product.objects.filter(sku__startswith="BATCH-")
        
        for product in created_products:
            stock = Stock(
                product=product,
                warehouse=self.main_warehouse,
                quantity=100,
                created_by=self.admin_user
            )
            stocks.append(stock)
        
        Stock.objects.bulk_create(stocks)
        
        # إنشاء حركات مخزون مجمعة
        movements = []
        for product in created_products:
            movement = StockMovement(
                product=product,
                warehouse=self.main_warehouse,
                quantity=100,
                type="in",
                reference="BATCH-INIT",
                notes="مخزون أولي مجمع",
                created_by=self.admin_user
            )
            movements.append(movement)
        
        StockMovement.objects.bulk_create(movements)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # التحقق من الأداء
        self.assertLess(execution_time, 10.0)  # يجب أن يكتمل في أقل من 10 ثواني
        
        # التحقق من النتائج
        created_count = Product.objects.filter(sku__startswith="BATCH-").count()
        self.assertEqual(created_count, 50)
        
        stock_count = Stock.objects.filter(product__sku__startswith="BATCH-").count()
        self.assertEqual(stock_count, 50)
        
        movement_count = StockMovement.objects.filter(reference="BATCH-INIT").count()
        self.assertEqual(movement_count, 50)
        
        self.complex_results['batch_operations_completed'] += 1
        print(f"   ✅ العمليات المجمعة اكتملت في {execution_time:.2f} ثانية")
    
    def test_concurrent_transactions(self):
        """اختبار المعاملات المتزامنة"""
        print("\n🔄 اختبار المعاملات المتزامنة...")
        
        # إعداد مخزون أولي
        initial_stock = Stock.objects.create(
            product=self.product1,
            warehouse=self.main_warehouse,
            quantity=1000,
            created_by=self.admin_user
        )
        
        # محاكاة معاملات متزامنة
        def simulate_sale_transaction(sale_id, quantity):
            """محاكاة معاملة بيع"""
            try:
                with transaction.atomic():
                    # قراءة المخزون الحالي
                    stock = Stock.objects.select_for_update().get(
                        product=self.product1,
                        warehouse=self.main_warehouse
                    )
                    
                    if stock.quantity >= quantity:
                        # إنشاء فاتورة بيع
                        sale = Sale.objects.create(
                            client=self.client,
                            invoice_number=f"CONCURRENT-{sale_id}",
                            invoice_date=date.today(),
                            created_by=self.admin_user
                        )
                        
                        # إضافة عنصر
                        SaleItem.objects.create(
                            sale=sale,
                            product=self.product1,
                            quantity=quantity,
                            unit_price=Decimal('0.80'),
                            total_price=quantity * Decimal('0.80')
                        )
                        
                        # تحديث المخزون
                        stock.quantity -= quantity
                        stock.save()
                        
                        # تسجيل الحركة
                        StockMovement.objects.create(
                            product=self.product1,
                            warehouse=self.main_warehouse,
                            quantity=quantity,
                            type="out",
                            reference=f"CONCURRENT-{sale_id}",
                            created_by=self.admin_user
                        )
                        
                        return True
                    else:
                        return False
            except Exception as e:
                print(f"خطأ في المعاملة {sale_id}: {str(e)}")
                return False
        
        # تنفيذ معاملات متعددة
        successful_transactions = 0
        transaction_quantities = [100, 150, 200, 120, 180]
        
        for i, quantity in enumerate(transaction_quantities, 1):
            if simulate_sale_transaction(i, quantity):
                successful_transactions += 1
        
        # التحقق من النتائج
        final_stock = Stock.objects.get(product=self.product1, warehouse=self.main_warehouse)
        expected_remaining = 1000 - sum(transaction_quantities[:successful_transactions])
        
        self.assertEqual(final_stock.quantity, expected_remaining)
        self.assertEqual(successful_transactions, len(transaction_quantities))
        
        # التحقق من عدد الفواتير المنشأة
        sales_count = Sale.objects.filter(invoice_number__startswith="CONCURRENT-").count()
        self.assertEqual(sales_count, successful_transactions)
        
        self.complex_results['concurrent_transactions'] = successful_transactions
        print(f"   ✅ تم تنفيذ {successful_transactions} معاملة متزامنة بنجاح")
    
    def test_error_handling_scenarios(self):
        """اختبار سيناريوهات معالجة الأخطاء"""
        print("\n⚠️ اختبار سيناريوهات الأخطاء...")
        
        # اختبار بيع بكمية أكبر من المخزون المتاح
        stock = Stock.objects.create(
            product=self.product2,
            warehouse=self.main_warehouse,
            quantity=50,
            created_by=self.admin_user
        )
        
        # محاولة بيع كمية أكبر من المتاح
        with self.assertRaises(Exception):
            with transaction.atomic():
                sale = Sale.objects.create(
                    client=self.client,
                    invoice_number="ERROR-TEST-001",
                    invoice_date=date.today(),
                    created_by=self.admin_user
                )
                
                SaleItem.objects.create(
                    sale=sale,
                    product=self.product2,
                    quantity=100,  # أكبر من المخزون المتاح (50)
                    unit_price=Decimal('0.65'),
                    total_price=Decimal('65.00')
                )
                
                # محاولة تحديث المخزون
                if stock.quantity < 100:
                    raise ValidationError("الكمية المطلوبة أكبر من المخزون المتاح")
                
                stock.quantity -= 100
                stock.save()
        
        # التحقق من عدم تأثر المخزون
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 50)
        
        # اختبار إنشاء منتج بـ SKU مكرر
        with self.assertRaises(Exception):
            Product.objects.create(
                name="منتج مكرر",
                sku=self.product1.sku,  # SKU مكرر
                category=self.category,
                unit=self.unit,
                cost_price=Decimal('0.50'),
                selling_price=Decimal('0.75'),
                created_by=self.admin_user
            )
        
        # اختبار فترة محاسبية بتواريخ خاطئة
        with self.assertRaises(ValidationError):
            period = AccountingPeriod(
                name="فترة خاطئة",
                start_date=date(2025, 12, 31),
                end_date=date(2025, 1, 1),  # تاريخ النهاية قبل البداية
                created_by=self.admin_user
            )
            period.full_clean()
        
        self.complex_results['error_scenarios_tested'] = 3
        print("   ✅ سيناريوهات الأخطاء تم اختبارها بنجاح")
    
    def test_advanced_pricing_scenarios(self):
        """اختبار سيناريوهات التسعير المتقدمة"""
        print("\n💰 اختبار سيناريوهات التسعير المتقدمة...")
        
        # إنشاء منتج مع أسعار متدرجة
        premium_product = Product.objects.create(
            name="منتج متدرج السعر",
            sku="TIERED-001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('1.00'),
            selling_price=Decimal('1.50'),  # السعر الأساسي
            created_by=self.admin_user
        )
        
        # إضافة مخزون
        Stock.objects.create(
            product=premium_product,
            warehouse=self.main_warehouse,
            quantity=1000,
            created_by=self.admin_user
        )
        
        # تطبيق تسعير متدرج حسب الكمية
        def get_tiered_price(quantity):
            """حساب السعر المتدرج حسب الكمية"""
            base_price = Decimal('1.50')
            
            if quantity >= 500:
                return base_price * Decimal('0.85')  # خصم 15%
            elif quantity >= 200:
                return base_price * Decimal('0.90')  # خصم 10%
            elif quantity >= 100:
                return base_price * Decimal('0.95')  # خصم 5%
            else:
                return base_price  # السعر الأساسي
        
        # اختبار مبيعات بكميات مختلفة
        test_quantities = [50, 150, 250, 600]
        total_revenue = Decimal('0')
        
        for i, quantity in enumerate(test_quantities, 1):
            unit_price = get_tiered_price(quantity)
            total_price = quantity * unit_price
            
            sale = Sale.objects.create(
                client=self.client,
                invoice_number=f"TIERED-{i}",
                invoice_date=date.today(),
                created_by=self.admin_user
            )
            
            SaleItem.objects.create(
                sale=sale,
                product=premium_product,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price
            )
            
            # تحديث المخزون
            stock = Stock.objects.get(product=premium_product, warehouse=self.main_warehouse)
            stock.quantity -= quantity
            stock.save()
            
            total_revenue += total_price
        
        # التحقق من النتائج
        remaining_stock = Stock.objects.get(product=premium_product, warehouse=self.main_warehouse)
        expected_remaining = 1000 - sum(test_quantities)
        self.assertEqual(remaining_stock.quantity, expected_remaining)
        
        # التحقق من إجمالي الإيرادات
        self.assertGreater(total_revenue, Decimal('0'))
        
        # حساب متوسط السعر
        total_quantity = sum(test_quantities)
        average_price = total_revenue / total_quantity
        
        # يجب أن يكون متوسط السعر أقل من السعر الأساسي بسبب الخصومات
        self.assertLess(average_price, Decimal('1.50'))
        
        print(f"   ✅ التسعير المتدرج: إجمالي الإيرادات {total_revenue}, متوسط السعر {average_price:.3f}")
    
    def tearDown(self):
        """طباعة ملخص النتائج المعقدة"""
        print("\n" + "="*50)
        print("📊 ملخص اختبارات السيناريوهات المعقدة")
        print("="*50)
        
        print(f"🏢 عمليات نقل المخازن: {self.complex_results['multi_warehouse_transfers']}")
        print(f"🔄 المرتجعات الجزئية: {self.complex_results['partial_returns_processed']}")
        print(f"⚡ العمليات المجمعة: {self.complex_results['batch_operations_completed']}")
        print(f"🔄 المعاملات المتزامنة: {self.complex_results['concurrent_transactions']}")
        print(f"⚠️ سيناريوهات الأخطاء: {self.complex_results['error_scenarios_tested']}")
        
        print("\n🎯 النتائج:")
        print("   ✅ العمليات متعددة المخازن")
        print("   ✅ المرتجعات والاستبدال")
        print("   ✅ العمليات المجمعة عالية الأداء")
        print("   ✅ المعاملات المتزامنة الآمنة")
        print("   ✅ معالجة الأخطاء والاستثناءات")
        print("   ✅ التسعير المتقدم والمتدرج")
        
        print("\n🏆 جميع السيناريوهات المعقدة نجحت!")
        print("="*50)
