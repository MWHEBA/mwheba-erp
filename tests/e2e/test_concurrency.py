"""
اختبارات E2E - Concurrency & Race Conditions
Concurrency and Race Condition Tests

هذا الملف يختبر السلوك المتزامن للنظام:
- بيع نفس المنتج من عدة مستخدمين في نفس الوقت
- دفعات متزامنة على نفس الفاتورة
- إنشاء قيود محاسبية متزامنة
- تحديث المخزون المتزامن
- Database locks والـ transactions

القاعدة: النظام يجب أن يحافظ على سلامة البيانات تحت الضغط!
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from django.db import transaction, IntegrityError
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading


@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.race_condition
@pytest.mark.slow
class TestConcurrentSales:
    """
    اختبارات البيع المتزامن
    """
    
    def test_concurrent_sales_same_product(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        setup_chart_of_accounts,
        race_condition_detector
    ):
        """
        اختبار: 10 مستخدمين يحاولون بيع نفس المنتج في نفس الوقت
        
        السيناريو:
        - المخزون: 100 قطعة
        - 10 مستخدمين يحاولون بيع 15 قطعة لكل واحد
        - الإجمالي المطلوب: 150 قطعة (أكثر من المتاح!)
        
        النتيجة المتوقعة:
        - بعض العمليات تنجح (حتى نفاد المخزون)
        - بعض العمليات تفشل (مخزون غير كافي)
        - المخزون النهائي صحيح (لا يصبح سالب!)
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        from client.services.customer_service import CustomerService
        
        print("\n" + "="*80)
        print("اختبار: البيع المتزامن لنفس المنتج")
        print("="*80)
        
        # إنشاء منتج بمخزون محدود
        product = Product.objects.create(
            name='منتج شعبي',
            sku='CONCURRENT_001',
            category=test_category,
            unit=test_unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            is_active=True,
            created_by=test_user
        )
        
        initial_stock = 100
        stock = Stock.objects.create(
            product=product,
            warehouse=test_warehouse,
            quantity=initial_stock,
            reserved_quantity=0
        )
        
        print(f"   المخزون الأولي: {initial_stock} قطعة")
        
        # إنشاء 10 عملاء
        customer_service = CustomerService()
        customers = []
        for i in range(10):
            customer = customer_service.create_customer(
                name=f'عميل متزامن {i+1}',
                code=f'CONC_CUST_{i+1}',
                user=test_user
            )
            customers.append(customer)
        
        print(f"   عدد العملاء: {len(customers)}")
        
        # دالة البيع
        def attempt_sale(customer_index):
            """محاولة بيع 15 قطعة"""
            try:
                # إضافة تأخير عشوائي صغير لتقليل الـ lock contention
                import random
                time.sleep(random.uniform(0.01, 0.05))
                
                customer = customers[customer_index]
                
                sale_data = {
                    'customer_id': customer.id,
                    'warehouse_id': test_warehouse.id,
                    'payment_method': 'credit',
                    'items': [
                        {
                            'product_id': product.id,
                            'quantity': 15,  # كل واحد يطلب 15
                            'unit_price': Decimal('100.00'),
                            'discount': Decimal('0')
                        }
                    ],
                    'discount': Decimal('0'),
                    'tax': Decimal('0')
                }
                
                # استخدام transaction جديدة لكل محاولة مع retry
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with transaction.atomic():
                            sale = SaleService.create_sale(sale_data, test_user)
                            return {'success': True, 'sale_id': sale.id, 'customer': customer_index}
                    except Exception as e:
                        if 'Lock wait timeout' in str(e) and attempt < max_retries - 1:
                            time.sleep(0.1 * (attempt + 1))  # exponential backoff
                            continue
                        raise
                
            except Exception as e:
                return {'success': False, 'error': str(e)[:100], 'customer': customer_index}
        
        # تشغيل متزامن
        print(f"\n   >> بدء البيع المتزامن...")
        start_time = time.time()
        
        results, errors = race_condition_detector.run_concurrent(
            attempt_sale,
            [(i,) for i in range(10)],
            max_workers=10
        )
        
        elapsed = time.time() - start_time
        print(f"   الوقت المستغرق: {elapsed:.2f}s")
        
        # تحليل النتائج
        successful_sales = [r for r in results if r.get('success')]
        failed_sales = [r for r in results if not r.get('success')]
        
        print(f"\n   النتائج:")
        print(f"      نجح: {len(successful_sales)}")
        print(f"      فشل: {len(failed_sales)}")
        
        # التحققات الحرجة
        stock.refresh_from_db()
        final_stock = stock.quantity
        
        print(f"\n   المخزون:")
        print(f"      الأولي: {initial_stock}")
        print(f"      النهائي: {final_stock}")
        print(f"      المباع: {initial_stock - final_stock}")
        
        # 1. المخزون لا يجب أن يكون سالب!
        assert final_stock >= 0, \
            f" CRITICAL BUG: المخزون أصبح سالب! {final_stock}"
        
        # 2. المخزون المباع = عدد المبيعات الناجحة × 15
        expected_sold = len(successful_sales) * 15
        actual_sold = initial_stock - final_stock
        
        assert actual_sold == expected_sold, \
            f" BUG: المخزون المباع {actual_sold} != المتوقع {expected_sold}"
        
        # 3. يجب أن يكون هناك على الأقل بعض المبيعات الناجحة
        assert len(successful_sales) > 0, \
            f" BUG: لم تنجح أي عملية بيع!"
        
        # 4. يجب أن يكون هناك بعض الفشل (لأن الإجمالي 150 > 100)
        assert len(failed_sales) > 0, \
            f" BUG: نجحت جميع العمليات رغم عدم كفاية المخزون!"
        
        print("\n" + "="*80)
        print(" الاختبار نجح - النظام تعامل مع التزامن بشكل صحيح")
        print("="*80)
    
    def test_concurrent_payments_same_invoice(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts,
        race_condition_detector
    ):
        """
        اختبار: دفعات متزامنة على نفس الفاتورة
        
        السيناريو:
        - فاتورة بقيمة 10,000 ج.م
        - 5 موظفين يحاولون تسجيل دفعة 3,000 ج.م في نفس الوقت
        - الإجمالي المطلوب: 15,000 ج.م (أكثر من قيمة الفاتورة!)
        
        النتيجة المتوقعة:
        - بعض الدفعات تنجح
        - بعض الدفعات تفشل (تجاوز قيمة الفاتورة)
        - إجمالي الدفعات <= قيمة الفاتورة
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        from sale.models import SalePayment
        
        print("\n" + "="*80)
        print("اختبار: الدفعات المتزامنة على نفس الفاتورة")
        print("="*80)
        
        # إنشاء منتج وفاتورة
        product = Product.objects.create(
            name='منتج للدفعات',
            sku='PAYMENT_TEST_001',
            category=test_category,
            unit=test_unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            is_active=True,
            created_by=test_user
        )
        
        Stock.objects.create(
            product=product,
            warehouse=test_warehouse,
            quantity=1000,
            reserved_quantity=0
        )
        
        sale_data = {
            'customer_id': test_customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': 100,
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0')
                }
            ],
            'discount': Decimal('0'),
            'tax': Decimal('0')
        }
        
        sale = SaleService.create_sale(sale_data, test_user)
        invoice_total = sale.total
        
        print(f"   قيمة الفاتورة: {invoice_total} ج.م")
        
        # دالة الدفع
        def attempt_payment(payment_index):
            """محاولة تسجيل دفعة 3000 ج.م"""
            try:
                # إضافة تأخير عشوائي صغير
                import random
                time.sleep(random.uniform(0.01, 0.05))
                
                payment_data = {
                    'amount': Decimal('3000.00'),
                    'payment_method': '10100',
                    'payment_date': timezone.now().date(),
                    'notes': f'دفعة متزامنة {payment_index + 1}'
                }
                
                # استخدام retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with transaction.atomic():
                            payment = SaleService.process_payment(sale, payment_data, test_user)
                            return {'success': True, 'payment_id': payment.id, 'index': payment_index}
                    except Exception as e:
                        if 'Lock wait timeout' in str(e) and attempt < max_retries - 1:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        raise
                
            except Exception as e:
                return {'success': False, 'error': str(e)[:100], 'index': payment_index}
        
        # تشغيل متزامن
        print(f"\n    بدء الدفعات المتزامنة...")
        
        results, errors = race_condition_detector.run_concurrent(
            attempt_payment,
            [(i,) for i in range(5)],
            max_workers=5
        )
        
        # تحليل النتائج
        successful_payments = [r for r in results if r.get('success')]
        failed_payments = [r for r in results if not r.get('success')]
        
        print(f"\n    النتائج:")
        print(f"       نجح: {len(successful_payments)}")
        print(f"       فشل: {len(failed_payments)}")
        
        # حساب إجمالي الدفعات
        from django.db import models
        total_paid = SalePayment.objects.filter(
            sale=sale,
            status='posted'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        
        print(f"\n    الدفعات:")
        print(f"      الإجمالي: {total_paid} ج.م")
        print(f"      قيمة الفاتورة: {invoice_total} ج.م")
        
        # التحققات
        # 1. إجمالي الدفعات لا يتجاوز قيمة الفاتورة
        assert total_paid <= invoice_total, \
            f" BUG: الدفعات {total_paid} تجاوزت قيمة الفاتورة {invoice_total}!"
        
        # 2. يجب أن يكون هناك على الأقل دفعة واحدة ناجحة
        assert len(successful_payments) > 0, \
            f" BUG: لم تنجح أي دفعة!"
        
        print("\n" + "="*80)
        print(" الاختبار نجح - الدفعات المتزامنة تعمل بشكل صحيح")
        print("="*80)
    
    def test_concurrent_stock_updates(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        setup_chart_of_accounts,
        race_condition_detector
    ):
        """
        اختبار: تحديثات متزامنة للمخزون
        
        السيناريو:
        - 5 عمليات شراء متزامنة (كل واحدة تضيف 20 قطعة)
        - 5 عمليات بيع متزامنة (كل واحدة تخصم 10 قطع)
        
        النتيجة المتوقعة:
        - المخزون النهائي = الأولي + (5×20) - (5×10) = الأولي + 50
        """
        from product.models import Product, Stock
        from purchase.services.purchase_service import PurchaseService
        from sale.services.sale_service import SaleService
        from supplier.services.supplier_service import SupplierService
        from client.services.customer_service import CustomerService
        
        print("\n" + "="*80)
        print("اختبار: تحديثات المخزون المتزامنة")
        print("="*80)
        
        # إنشاء منتج
        product = Product.objects.create(
            name='منتج للتحديثات',
            sku='STOCK_UPDATE_001',
            category=test_category,
            unit=test_unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            is_active=True,
            created_by=test_user
        )
        
        initial_stock = 100
        stock = Stock.objects.create(
            product=product,
            warehouse=test_warehouse,
            quantity=initial_stock,
            reserved_quantity=0
        )
        
        print(f"   المخزون الأولي: {initial_stock}")
        
        # إنشاء مورد وعميل
        supplier_service = SupplierService()
        supplier = supplier_service.create_supplier(
            name='مورد التحديثات',
            code='STOCK_SUP_001',
            user=test_user
        )
        
        customer_service = CustomerService()
        customer = customer_service.create_customer(
            name='عميل التحديثات',
            code='STOCK_CUST_001',
            user=test_user
        )
        
        # دالة الشراء
        def attempt_purchase(index):
            try:
                # إضافة تأخير عشوائي صغير
                import random
                time.sleep(random.uniform(0.01, 0.05))
                
                purchase_data = {
                    'supplier_id': supplier.id,
                    'warehouse_id': test_warehouse.id,
                    'payment_method': 'credit',
                    'items': [
                        {
                            'product_id': product.id,
                            'quantity': 20,
                            'unit_price': Decimal('50.00'),
                            'discount': Decimal('0')
                        }
                    ],
                    'discount': Decimal('0'),
                    'tax': Decimal('0')
                }
                
                # استخدام retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with transaction.atomic():
                            purchase = PurchaseService.create_purchase(purchase_data, test_user)
                            return {'type': 'purchase', 'success': True, 'id': purchase.id}
                    except Exception as e:
                        if 'Lock wait timeout' in str(e) and attempt < max_retries - 1:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        raise
                
            except Exception as e:
                return {'type': 'purchase', 'success': False, 'error': str(e)[:100]}
        
        # دالة البيع
        def attempt_sale(index):
            try:
                # إضافة تأخير عشوائي صغير
                import random
                time.sleep(random.uniform(0.01, 0.05))
                
                sale_data = {
                    'customer_id': customer.id,
                    'warehouse_id': test_warehouse.id,
                    'payment_method': 'credit',
                    'items': [
                        {
                            'product_id': product.id,
                            'quantity': 10,
                            'unit_price': Decimal('100.00'),
                            'discount': Decimal('0')
                        }
                    ],
                    'discount': Decimal('0'),
                    'tax': Decimal('0')
                }
                
                # استخدام retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with transaction.atomic():
                            sale = SaleService.create_sale(sale_data, test_user)
                            return {'type': 'sale', 'success': True, 'id': sale.id}
                    except Exception as e:
                        if 'Lock wait timeout' in str(e) and attempt < max_retries - 1:
                            time.sleep(0.1 * (attempt + 1))
                            continue
                        raise
                
            except Exception as e:
                return {'type': 'sale', 'success': False, 'error': str(e)[:100]}
        
        # تشغيل متزامن (مشتريات ومبيعات معاً)
        print(f"\n    بدء التحديثات المتزامنة...")
        
        operations = []
        operations.extend([('purchase', i) for i in range(5)])
        operations.extend([('sale', i) for i in range(5)])
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for op_type, index in operations:
                if op_type == 'purchase':
                    futures.append(executor.submit(attempt_purchase, index))
                else:
                    futures.append(executor.submit(attempt_sale, index))
            
            results = [f.result() for f in futures]
        
        # تحليل النتائج
        purchases = [r for r in results if r.get('type') == 'purchase' and r.get('success')]
        sales = [r for r in results if r.get('type') == 'sale' and r.get('success')]
        
        print(f"\n    النتائج:")
        print(f"      مشتريات ناجحة: {len(purchases)}")
        print(f"      مبيعات ناجحة: {len(sales)}")
        
        # التحقق من المخزون النهائي
        stock.refresh_from_db()
        final_stock = stock.quantity
        
        expected_stock = initial_stock + (len(purchases) * 20) - (len(sales) * 10)
        
        print(f"\n    المخزون:")
        print(f"      الأولي: {initial_stock}")
        print(f"      النهائي: {final_stock}")
        print(f"      المتوقع: {expected_stock}")
        
        assert final_stock == expected_stock, \
            f" BUG: المخزون النهائي {final_stock} != المتوقع {expected_stock}"
        
        print("\n" + "="*80)
        print(" الاختبار نجح - تحديثات المخزون المتزامنة دقيقة")
        print("="*80)


# Import models for aggregation
from django.db import models
