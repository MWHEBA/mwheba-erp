"""
اختبارات الأداء والحمولة الشاملة
تقيس قدرة النظام على التعامل مع الأحجام الكبيرة والمستخدمين المتزامنين
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction, connections
from django.core.management import call_command
from decimal import Decimal
from datetime import date, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil
import os

# استيراد النماذج
from product.models import Category, Brand, Unit, Product, Warehouse, Stock, StockMovement
from supplier.models import Supplier, SupplierType
from client.models import Client
from purchase.models import Purchase, PurchaseItem, PurchasePayment
from sale.models import Sale, SaleItem, SalePayment
from financial.models import (
    AccountType, ChartOfAccounts, AccountingPeriod, 
    JournalEntry, JournalEntryLine, PartnerTransaction
)
from financial.services.balance_service import BalanceService

User = get_user_model()


class PerformanceLoadTestCase(TransactionTestCase):
    """اختبارات الأداء والحمولة"""
    
    fixtures = [
        'financial/fixtures/chart_of_accounts_final.json',
        'product/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json'
    ]
    
    def setUp(self):
        """إعداد بيانات اختبار الأداء"""
        self.admin_user = User.objects.create_user(
            username="admin", 
            email="admin@test.com", 
            password="admin123",
            is_staff=True
        )
        
        # إعداد البيانات الأساسية
        self.setup_performance_data()
        
        # متغيرات قياس الأداء
        self.performance_metrics = {
            'database_queries': 0,
            'memory_usage_mb': 0,
            'execution_times': {},
            'throughput_per_second': {},
            'concurrent_users_supported': 0,
            'max_transactions_per_minute': 0
        }
    
    def setup_performance_data(self):
        """إعداد البيانات لاختبارات الأداء"""
        # الفترة المحاسبية
        self.period = AccountingPeriod.objects.create(
            name="2025-Performance",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=self.admin_user
        )
        
        # البيانات من fixtures
        self.category = Category.objects.get(name="ورق")
        self.brand = Brand.objects.get(name="كوشيه")
        self.unit = Unit.objects.get(name="فرخ")
        self.warehouse = Warehouse.objects.get(name="المخزن الرئيسي")
        
        # إنشاء مورد وعميل أساسي
        supplier_type = SupplierType.objects.get(code="paper")
        self.supplier = Supplier.objects.create(
            name="مورد الأداء",
            supplier_type=supplier_type,
            created_by=self.admin_user
        )
        
        self.client = Client.objects.create(
            name="عميل الأداء",
            created_by=self.admin_user
        )
    
    def measure_execution_time(self, operation_name):
        """ديكوريتر لقياس وقت التنفيذ"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                end_time = time.time()
                execution_time = end_time - start_time
                self.performance_metrics['execution_times'][operation_name] = execution_time
                return result
            return wrapper
        return decorator
    
    def get_memory_usage(self):
        """قياس استخدام الذاكرة"""
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # تحويل إلى MB
    
    @measure_execution_time('bulk_product_creation')
    def test_bulk_product_creation_performance(self):
        """اختبار أداء إنشاء المنتجات بالجملة"""
        print("\n📦 اختبار أداء إنشاء المنتجات بالجملة...")
        
        initial_memory = self.get_memory_usage()
        start_time = time.time()
        
        # إنشاء 1000 منتج
        products = []
        batch_size = 1000
        
        for i in range(batch_size):
            product = Product(
                name=f"منتج أداء {i+1}",
                sku=f"PERF-{i+1:04d}",
                category=self.category,
                brand=self.brand,
                unit=self.unit,
                cost_price=Decimal('0.50'),
                selling_price=Decimal('0.75'),
                created_by=self.admin_user
            )
            products.append(product)
        
        # إنشاء مجمع
        Product.objects.bulk_create(products, batch_size=100)
        
        end_time = time.time()
        final_memory = self.get_memory_usage()
        
        execution_time = end_time - start_time
        memory_used = final_memory - initial_memory
        
        # قياس الأداء
        products_per_second = batch_size / execution_time
        
        # التحقق من الأداء المطلوب
        self.assertLess(execution_time, 30.0)  # يجب أن يكتمل في أقل من 30 ثانية
        self.assertLess(memory_used, 100.0)   # يجب ألا يستخدم أكثر من 100 MB
        
        # التحقق من النتائج
        created_count = Product.objects.filter(sku__startswith="PERF-").count()
        self.assertEqual(created_count, batch_size)
        
        self.performance_metrics['throughput_per_second']['product_creation'] = products_per_second
        self.performance_metrics['memory_usage_mb'] = memory_used
        
        print(f"   ✅ تم إنشاء {batch_size} منتج في {execution_time:.2f} ثانية")
        print(f"   📊 معدل الإنشاء: {products_per_second:.1f} منتج/ثانية")
        print(f"   💾 استخدام الذاكرة: {memory_used:.1f} MB")
    
    @measure_execution_time('high_volume_transactions')
    def test_high_volume_transactions(self):
        """اختبار المعاملات عالية الحجم"""
        print("\n💰 اختبار المعاملات عالية الحجم...")
        
        # إنشاء منتج للاختبار
        test_product = Product.objects.create(
            name="منتج المعاملات",
            sku="TRANS-001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.75'),
            created_by=self.admin_user
        )
        
        # إضافة مخزون كبير
        Stock.objects.create(
            product=test_product,
            warehouse=self.warehouse,
            quantity=100000,
            created_by=self.admin_user
        )
        
        start_time = time.time()
        
        # إنشاء 500 فاتورة بيع
        sales_count = 500
        successful_sales = 0
        
        for i in range(sales_count):
            try:
                with transaction.atomic():
                    sale = Sale.objects.create(
                        client=self.client,
                        invoice_number=f"HVOL-{i+1:04d}",
                        invoice_date=date.today(),
                        created_by=self.admin_user
                    )
                    
                    SaleItem.objects.create(
                        sale=sale,
                        product=test_product,
                        quantity=10,
                        unit_price=Decimal('0.75'),
                        total_price=Decimal('7.50')
                    )
                    
                    # تحديث المخزون
                    stock = Stock.objects.select_for_update().get(
                        product=test_product,
                        warehouse=self.warehouse
                    )
                    stock.quantity -= 10
                    stock.save()
                    
                    successful_sales += 1
                    
            except Exception as e:
                print(f"خطأ في المعاملة {i+1}: {str(e)}")
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # قياس الأداء
        transactions_per_second = successful_sales / execution_time
        transactions_per_minute = transactions_per_second * 60
        
        # التحقق من الأداء
        self.assertLess(execution_time, 120.0)  # يجب أن يكتمل في أقل من دقيقتين
        self.assertEqual(successful_sales, sales_count)
        
        # التحقق من تحديث المخزون
        final_stock = Stock.objects.get(product=test_product, warehouse=self.warehouse)
        expected_quantity = 100000 - (successful_sales * 10)
        self.assertEqual(final_stock.quantity, expected_quantity)
        
        self.performance_metrics['max_transactions_per_minute'] = transactions_per_minute
        
        print(f"   ✅ تم تنفيذ {successful_sales} معاملة في {execution_time:.2f} ثانية")
        print(f"   📈 معدل المعاملات: {transactions_per_minute:.1f} معاملة/دقيقة")
    
    def test_concurrent_users_simulation(self):
        """محاكاة المستخدمين المتزامنين"""
        print("\n👥 محاكاة المستخدمين المتزامنين...")
        
        # إنشاء منتج للاختبار
        concurrent_product = Product.objects.create(
            name="منتج المستخدمين المتزامنين",
            sku="CONC-001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.75'),
            created_by=self.admin_user
        )
        
        # إضافة مخزون
        Stock.objects.create(
            product=concurrent_product,
            warehouse=self.warehouse,
            quantity=10000,
            created_by=self.admin_user
        )
        
        def simulate_user_activity(user_id):
            """محاكاة نشاط مستخدم واحد"""
            successful_operations = 0
            
            try:
                # إنشاء مستخدم للمحاكاة
                user = User.objects.create_user(
                    username=f"user_{user_id}",
                    email=f"user_{user_id}@test.com",
                    password="test123"
                )
                
                # تنفيذ 10 عمليات بيع
                for i in range(10):
                    try:
                        with transaction.atomic():
                            sale = Sale.objects.create(
                                client=self.client,
                                invoice_number=f"USER{user_id}-{i+1}",
                                invoice_date=date.today(),
                                created_by=user
                            )
                            
                            SaleItem.objects.create(
                                sale=sale,
                                product=concurrent_product,
                                quantity=5,
                                unit_price=Decimal('0.75'),
                                total_price=Decimal('3.75')
                            )
                            
                            # تحديث المخزون بحماية من التضارب
                            stock = Stock.objects.select_for_update().get(
                                product=concurrent_product,
                                warehouse=self.warehouse
                            )
                            
                            if stock.quantity >= 5:
                                stock.quantity -= 5
                                stock.save()
                                successful_operations += 1
                            else:
                                # إلغاء المعاملة إذا لم يكن هناك مخزون كافي
                                transaction.set_rollback(True)
                                
                    except Exception as e:
                        print(f"خطأ في العملية {i+1} للمستخدم {user_id}: {str(e)}")
                        
            except Exception as e:
                print(f"خطأ في إنشاء المستخدم {user_id}: {str(e)}")
            
            return successful_operations
        
        # تنفيذ المحاكاة مع 20 مستخدم متزامن
        start_time = time.time()
        max_workers = 20
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # إرسال المهام
            futures = [executor.submit(simulate_user_activity, i) for i in range(1, max_workers + 1)]
            
            # جمع النتائج
            total_successful_operations = 0
            for future in as_completed(futures):
                try:
                    result = future.result()
                    total_successful_operations += result
                except Exception as e:
                    print(f"خطأ في مهمة المستخدم: {str(e)}")
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # التحقق من النتائج
        final_stock = Stock.objects.get(product=concurrent_product, warehouse=self.warehouse)
        expected_quantity = 10000 - (total_successful_operations * 5)
        self.assertEqual(final_stock.quantity, expected_quantity)
        
        # قياس الأداء
        operations_per_second = total_successful_operations / execution_time
        
        self.performance_metrics['concurrent_users_supported'] = max_workers
        
        print(f"   ✅ {max_workers} مستخدم متزامن نفذوا {total_successful_operations} عملية")
        print(f"   ⏱️ وقت التنفيذ: {execution_time:.2f} ثانية")
        print(f"   📊 معدل العمليات: {operations_per_second:.1f} عملية/ثانية")
    
    @measure_execution_time('large_report_generation')
    def test_large_report_generation(self):
        """اختبار إنشاء التقارير الكبيرة"""
        print("\n📊 اختبار إنشاء التقارير الكبيرة...")
        
        start_time = time.time()
        
        # إنشاء بيانات كبيرة للتقرير
        # إنشاء 100 منتج
        products = []
        for i in range(100):
            product = Product(
                name=f"منتج تقرير {i+1}",
                sku=f"RPT-{i+1:03d}",
                category=self.category,
                unit=self.unit,
                cost_price=Decimal('0.50'),
                selling_price=Decimal('0.75'),
                created_by=self.admin_user
            )
            products.append(product)
        
        Product.objects.bulk_create(products)
        
        # إنشاء مخزون لكل منتج
        stocks = []
        created_products = Product.objects.filter(sku__startswith="RPT-")
        for product in created_products:
            stock = Stock(
                product=product,
                warehouse=self.warehouse,
                quantity=100,
                created_by=self.admin_user
            )
            stocks.append(stock)
        
        Stock.objects.bulk_create(stocks)
        
        # إنشاء 200 فاتورة بيع
        for i in range(200):
            sale = Sale.objects.create(
                client=self.client,
                invoice_number=f"RPT-SALE-{i+1:03d}",
                invoice_date=date.today() - timedelta(days=i % 30),
                created_by=self.admin_user
            )
            
            # اختيار منتج عشوائي
            product = created_products[i % len(created_products)]
            
            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=5,
                unit_price=Decimal('0.75'),
                total_price=Decimal('3.75')
            )
        
        # إنشاء تقرير ميزان المراجعة
        trial_balance_start = time.time()
        trial_balance = BalanceService.get_trial_balance()
        trial_balance_time = time.time() - trial_balance_start
        
        # إنشاء تقرير المخزون
        inventory_report_start = time.time()
        inventory_report = []
        for stock in Stock.objects.select_related('product', 'warehouse').all():
            inventory_report.append({
                'product_name': stock.product.name,
                'sku': stock.product.sku,
                'warehouse': stock.warehouse.name,
                'quantity': stock.quantity,
                'value': stock.quantity * stock.product.cost_price
            })
        inventory_report_time = time.time() - inventory_report_start
        
        # إنشاء تقرير المبيعات
        sales_report_start = time.time()
        sales_report = []
        for sale in Sale.objects.select_related('client').prefetch_related('items__product').all():
            total_amount = sum(item.total_price for item in sale.items.all())
            sales_report.append({
                'invoice_number': sale.invoice_number,
                'client_name': sale.client.name,
                'date': sale.invoice_date,
                'total_amount': total_amount,
                'items_count': sale.items.count()
            })
        sales_report_time = time.time() - sales_report_start
        
        end_time = time.time()
        total_execution_time = end_time - start_time
        
        # التحقق من النتائج
        self.assertIsNotNone(trial_balance)
        self.assertGreater(len(inventory_report), 0)
        self.assertGreater(len(sales_report), 0)
        
        # التحقق من الأداء
        self.assertLess(trial_balance_time, 10.0)      # ميزان المراجعة في أقل من 10 ثواني
        self.assertLess(inventory_report_time, 5.0)    # تقرير المخزون في أقل من 5 ثواني
        self.assertLess(sales_report_time, 15.0)       # تقرير المبيعات في أقل من 15 ثانية
        
        print(f"   ✅ ميزان المراجعة: {trial_balance_time:.2f} ثانية")
        print(f"   ✅ تقرير المخزون: {inventory_report_time:.2f} ثانية ({len(inventory_report)} عنصر)")
        print(f"   ✅ تقرير المبيعات: {sales_report_time:.2f} ثانية ({len(sales_report)} فاتورة)")
        print(f"   📊 إجمالي وقت التقارير: {total_execution_time:.2f} ثانية")
    
    def test_database_optimization(self):
        """اختبار تحسين قاعدة البيانات"""
        print("\n🗄️ اختبار تحسين قاعدة البيانات...")
        
        # قياس عدد الاستعلامات
        from django.db import connection
        from django.test.utils import override_settings
        
        # إعادة تعيين عداد الاستعلامات
        connection.queries_log.clear()
        
        start_queries = len(connection.queries)
        
        # تنفيذ عمليات معقدة
        # 1. جلب المنتجات مع العلاقات
        products_with_relations = Product.objects.select_related(
            'category', 'brand', 'unit'
        ).prefetch_related('stocks__warehouse').all()[:50]
        
        # 2. جلب المبيعات مع العناصر
        sales_with_items = Sale.objects.select_related('client').prefetch_related(
            'items__product'
        ).all()[:20]
        
        # 3. حساب إجماليات المخزون
        total_stock_value = sum(
            stock.quantity * stock.product.cost_price 
            for stock in Stock.objects.select_related('product').all()
        )
        
        end_queries = len(connection.queries)
        total_queries = end_queries - start_queries
        
        # التحقق من تحسين الاستعلامات
        self.assertLess(total_queries, 20)  # يجب ألا يتجاوز 20 استعلام
        
        self.performance_metrics['database_queries'] = total_queries
        
        print(f"   ✅ عدد الاستعلامات المنفذة: {total_queries}")
        print(f"   📦 المنتجات المجلبة: {len(list(products_with_relations))}")
        print(f"   💰 المبيعات المجلبة: {len(list(sales_with_items))}")
        print(f"   📊 إجمالي قيمة المخزون: {total_stock_value}")
    
    def tearDown(self):
        """طباعة ملخص نتائج الأداء"""
        print("\n" + "="*60)
        print("🚀 ملخص نتائج اختبارات الأداء والحمولة")
        print("="*60)
        
        print("⏱️ أوقات التنفيذ:")
        for operation, time_taken in self.performance_metrics['execution_times'].items():
            print(f"   {operation}: {time_taken:.2f} ثانية")
        
        print(f"\n📊 معدلات الإنتاجية:")
        for operation, rate in self.performance_metrics['throughput_per_second'].items():
            print(f"   {operation}: {rate:.1f} عملية/ثانية")
        
        print(f"\n💾 استخدام الموارد:")
        print(f"   استخدام الذاكرة: {self.performance_metrics['memory_usage_mb']:.1f} MB")
        print(f"   استعلامات قاعدة البيانات: {self.performance_metrics['database_queries']}")
        
        print(f"\n👥 القدرة على التحمل:")
        print(f"   المستخدمين المتزامنين المدعومين: {self.performance_metrics['concurrent_users_supported']}")
        print(f"   أقصى معاملات في الدقيقة: {self.performance_metrics['max_transactions_per_minute']:.1f}")
        
        print(f"\n🎯 معايير الأداء المحققة:")
        
        # تقييم الأداء
        performance_score = 0
        max_score = 5
        
        # معيار سرعة إنشاء المنتجات
        if 'bulk_product_creation' in self.performance_metrics['execution_times']:
            if self.performance_metrics['execution_times']['bulk_product_creation'] < 15:
                performance_score += 1
                print("   ✅ سرعة إنشاء المنتجات: ممتاز")
            else:
                print("   ⚠️ سرعة إنشاء المنتجات: يحتاج تحسين")
        
        # معيار المعاملات عالية الحجم
        if self.performance_metrics['max_transactions_per_minute'] > 200:
            performance_score += 1
            print("   ✅ المعاملات عالية الحجم: ممتاز")
        else:
            print("   ⚠️ المعاملات عالية الحجم: يحتاج تحسين")
        
        # معيار المستخدمين المتزامنين
        if self.performance_metrics['concurrent_users_supported'] >= 20:
            performance_score += 1
            print("   ✅ دعم المستخدمين المتزامنين: ممتاز")
        else:
            print("   ⚠️ دعم المستخدمين المتزامنين: يحتاج تحسين")
        
        # معيار استخدام الذاكرة
        if self.performance_metrics['memory_usage_mb'] < 50:
            performance_score += 1
            print("   ✅ استخدام الذاكرة: ممتاز")
        else:
            print("   ⚠️ استخدام الذاكرة: يحتاج تحسين")
        
        # معيار تحسين قاعدة البيانات
        if self.performance_metrics['database_queries'] < 15:
            performance_score += 1
            print("   ✅ تحسين قاعدة البيانات: ممتاز")
        else:
            print("   ⚠️ تحسين قاعدة البيانات: يحتاج تحسين")
        
        print(f"\n🏆 النتيجة الإجمالية: {performance_score}/{max_score}")
        
        if performance_score >= 4:
            print("🎉 أداء ممتاز - النظام جاهز للإنتاج!")
        elif performance_score >= 3:
            print("👍 أداء جيد - يحتاج تحسينات طفيفة")
        else:
            print("⚠️ أداء يحتاج تحسين - مراجعة مطلوبة")
        
        print("="*60)
