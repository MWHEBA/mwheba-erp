"""
اختبارات E2E - Property-Based Testing
Property-Based Tests with Hypothesis

هذا الملف يستخدم Hypothesis لاختبار النظام بقيم عشوائية واقعية:
- اختبار المبيعات بكميات وأسعار عشوائية
- اختبار المشتريات بقيم متنوعة
- اختبار الحدود القصوى (max values)
- اختبار الأرقام العشرية الدقيقة
- اختبار Unicode والحروف الخاصة

القاعدة: النظام يجب أن يعمل مع أي قيم صحيحة!
"""
import pytest
from decimal import Decimal, InvalidOperation
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from hypothesis.extra.django import TestCase
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


# استراتيجيات مخصصة للبيانات العربية
arabic_names = st.text(
    alphabet='ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأإئؤة ',
    min_size=3,
    max_size=50
).filter(lambda x: x.strip() and len(x.strip()) >= 3)

arabic_companies = st.sampled_from([
    'شركة النور للتجارة',
    'مؤسسة الأمل التجارية',
    'شركة الفجر للمقاولات',
    'مؤسسة البناء الحديث',
    'شركة التقدم الصناعية',
    'مؤسسة النجاح التجارية',
    'شركة الرواد للتوريدات',
    'مؤسسة الإبداع التجارية'
])

# أسعار واقعية
realistic_prices = st.decimals(
    min_value='0.01',
    max_value='999999.99',
    places=2
).filter(lambda x: x > 0)

# كميات واقعية
realistic_quantities = st.integers(min_value=1, max_value=10000)

# كميات صغيرة للاختبارات السريعة
small_quantities = st.integers(min_value=1, max_value=100)


@pytest.mark.e2e
@pytest.mark.property
@pytest.mark.critical
class TestPropertyBasedSales:
    """
    اختبارات Property-Based للمبيعات
    """
    
    @settings(
        max_examples=20,  # عدد الأمثلة للاختبار
        deadline=10000,  # 10 ثواني لكل مثال
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
    )
    @given(
        quantity=small_quantities,
        unit_price=realistic_prices,
        discount_percent=st.decimals(min_value='0', max_value='100', places=2)
    )
    def test_sale_with_random_values(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts,
        quantity,
        unit_price,
        discount_percent
    ):
        """
        اختبار: إنشاء فاتورة بيع بقيم عشوائية
        
        Property: لأي كمية وسعر صحيحين، يجب أن:
        - تُنشأ الفاتورة بنجاح
        - الإجمالي = (الكمية × السعر) - الخصم
        - المخزون ينقص بالكمية الصحيحة
        - القيد المحاسبي متوازن
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        from financial.models import JournalEntry
        
        # تجاهل القيم غير المنطقية
        assume(quantity > 0)
        assume(unit_price > Decimal('0.01'))
        assume(discount_percent >= 0 and discount_percent <= 100)
        
        print(f"\n� Testing with: qty={quantity}, price={unit_price}, discount={discount_percent}%")
        
        try:
            # إنشاء منتج
            product = Product.objects.create(
                name=f'منتج اختبار {quantity}',
                sku=f'PROP_TEST_{quantity}_{int(unit_price)}',
                category=test_category,
                unit=test_unit,
                cost_price=unit_price * Decimal('0.7'),  # 70% من سعر البيع
                selling_price=unit_price,
                is_active=True,
                created_by=test_user
            )
            
            # إنشاء مخزون كافي
            initial_stock = quantity * 2  # ضعف الكمية المطلوبة
            stock = Stock.objects.create(
                product=product,
                warehouse=test_warehouse,
                quantity=initial_stock,
                reserved_quantity=0
            )
            
            # حساب الخصم والإجمالي المتوقع
            subtotal = Decimal(quantity) * unit_price
            discount_amount = subtotal * (discount_percent / Decimal('100'))
            expected_total = subtotal - discount_amount
            
            # إنشاء فاتورة
            sale_data = {
                'customer_id': test_customer.id,
                'warehouse_id': test_warehouse.id,
                'payment_method': 'credit',
                'items': [
                    {
                        'product_id': product.id,
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'discount': discount_amount
                    }
                ],
                'discount': Decimal('0'),
                'tax': Decimal('0')
            }
            
            sale = SaleService.create_sale(sale_data, test_user)
            
            # ==================== التحققات ====================
            
            # 1. الإجمالي صحيح (مع تسامح للأخطاء العشرية)
            assert abs(sale.total - expected_total) < Decimal('0.01'), \
                f" الإجمالي خاطئ: {sale.total} != {expected_total}"
            
            # 2. المخزون نقص بالكمية الصحيحة
            stock.refresh_from_db()
            expected_stock = initial_stock - quantity
            assert stock.quantity == expected_stock, \
                f" المخزون خاطئ: {stock.quantity} != {expected_stock}"
            
            # 3. القيد المحاسبي متوازن
            if sale.journal_entry:
                entry = sale.journal_entry
                lines = entry.lines.all()
                
                total_debit = sum(line.debit for line in lines)
                total_credit = sum(line.credit for line in lines)
                
                assert abs(total_debit - total_credit) < Decimal('0.01'), \
                    f" القيد غير متوازن: مدين={total_debit}, دائن={total_credit}"
            
            print(f" Success: total={sale.total}, stock={stock.quantity}")
            
        except Exception as e:
            # تسجيل الفشل مع التفاصيل
            print(f" FAILED with qty={quantity}, price={unit_price}, discount={discount_percent}%")
            print(f"   Error: {str(e)}")
            raise
    
    @settings(max_examples=15, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        customer_name=arabic_names,
        credit_limit=realistic_prices
    )
    def test_customer_creation_with_unicode(
        self,
        db,
        test_user,
        setup_chart_of_accounts,
        customer_name,
        credit_limit
    ):
        """
        اختبار: إنشاء عميل بأسماء عربية متنوعة
        
        Property: لأي اسم عربي صحيح، يجب أن:
        - يُنشأ العميل بنجاح
        - الاسم يُحفظ بشكل صحيح (Unicode)
        - الحساب المحاسبي يُنشأ تلقائياً
        """
        from client.services.customer_service import CustomerService
        
        assume(len(customer_name.strip()) >= 3)
        assume(credit_limit > 0)
        
        print(f"\n� Testing customer: '{customer_name}', limit={credit_limit}")
        
        try:
            service = CustomerService()
            customer = service.create_customer(
                name=customer_name,
                code=f'PROP_CUST_{abs(hash(customer_name)) % 100000}',
                user=test_user,
                credit_limit=credit_limit
            )
            
            # التحققات
            assert customer.name == customer_name, \
                f" الاسم لم يُحفظ بشكل صحيح: '{customer.name}' != '{customer_name}'"
            
            assert customer.financial_account is not None, \
                f" الحساب المحاسبي لم يُنشأ للعميل: {customer_name}"
            
            assert customer.credit_limit == credit_limit, \
                f" حد الائتمان خاطئ: {customer.credit_limit} != {credit_limit}"
            
            print(f" Customer created: {customer.code}")
            
        except Exception as e:
            print(f" FAILED with name='{customer_name}', limit={credit_limit}")
            print(f"   Error: {str(e)}")
            raise
    
    @settings(max_examples=10, deadline=15000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        num_items=st.integers(min_value=1, max_value=10),
        base_price=st.decimals(min_value='10', max_value='1000', places=2)
    )
    def test_multi_item_invoice_totals(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts,
        num_items,
        base_price
    ):
        """
        اختبار: فاتورة متعددة البنود بأسعار عشوائية
        
        Property: لأي عدد من البنود، يجب أن:
        - الإجمالي = مجموع البنود
        - المخزون ينقص لكل منتج
        - القيد المحاسبي يشمل جميع التكاليف
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        assume(num_items > 0 and num_items <= 10)
        assume(base_price > 0)
        
        print(f"\n� Testing invoice with {num_items} items, base_price={base_price}")
        
        try:
            # إنشاء منتجات
            products = []
            items_data = []
            expected_total = Decimal('0')
            
            for i in range(num_items):
                price = base_price * Decimal(str(i + 1))
                quantity = (i + 1) * 5
                
                product = Product.objects.create(
                    name=f'منتج {i+1}',
                    sku=f'MULTI_{i+1}_{int(price)}',
                    category=test_category,
                    unit=test_unit,
                    cost_price=price * Decimal('0.7'),
                    selling_price=price,
                    is_active=True,
                    created_by=test_user
                )
                
                Stock.objects.create(
                    product=product,
                    warehouse=test_warehouse,
                    quantity=quantity * 2,
                    reserved_quantity=0
                )
                
                products.append(product)
                
                item_total = Decimal(quantity) * price
                expected_total += item_total
                
                items_data.append({
                    'product_id': product.id,
                    'quantity': quantity,
                    'unit_price': price,
                    'discount': Decimal('0')
                })
            
            # إنشاء فاتورة
            sale_data = {
                'customer_id': test_customer.id,
                'warehouse_id': test_warehouse.id,
                'payment_method': 'credit',
                'items': items_data,
                'discount': Decimal('0'),
                'tax': Decimal('0')
            }
            
            sale = SaleService.create_sale(sale_data, test_user)
            
            # التحققات
            assert abs(sale.total - expected_total) < Decimal('0.01'), \
                f" الإجمالي خاطئ: {sale.total} != {expected_total}"
            
            assert sale.items.count() == num_items, \
                f" عدد البنود خاطئ: {sale.items.count()} != {num_items}"
            
            print(f" Invoice created: {num_items} items, total={sale.total}")
            
        except Exception as e:
            print(f" FAILED with {num_items} items, base_price={base_price}")
            print(f"   Error: {str(e)}")
            raise


@pytest.mark.e2e
@pytest.mark.property
@pytest.mark.edge_case
class TestPropertyBasedEdgeCases:
    """
    اختبارات Property-Based للحالات الحدية
    """
    
    @settings(max_examples=10, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        quantity=st.integers(min_value=1, max_value=100),
        available_stock=st.integers(min_value=0, max_value=50)
    )
    def test_insufficient_stock_property(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts,
        quantity,
        available_stock
    ):
        """
        اختبار: محاولة البيع بمخزون غير كافي
        
        Property: إذا كانت الكمية المطلوبة > المخزون المتاح:
        - يجب أن تفشل العملية
        - المخزون لا يتأثر
        - لا يُنشأ قيد محاسبي
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        # نختبر فقط الحالات التي فيها الكمية أكبر من المخزون
        assume(quantity > available_stock)
        
        print(f"\n� Testing: qty={quantity} > stock={available_stock}")
        
        try:
            product = Product.objects.create(
                name=f'منتج محدود',
                sku=f'LIMITED_{quantity}_{available_stock}',
                category=test_category,
                unit=test_unit,
                cost_price=Decimal('50.00'),
                selling_price=Decimal('100.00'),
                is_active=True,
                created_by=test_user
            )
            
            stock = Stock.objects.create(
                product=product,
                warehouse=test_warehouse,
                quantity=available_stock,
                reserved_quantity=0
            )
            
            sale_data = {
                'customer_id': test_customer.id,
                'warehouse_id': test_warehouse.id,
                'payment_method': 'credit',
                'items': [
                    {
                        'product_id': product.id,
                        'quantity': quantity,
                        'unit_price': Decimal('100.00'),
                        'discount': Decimal('0')
                    }
                ],
                'discount': Decimal('0'),
                'tax': Decimal('0')
            }
            
            # يجب أن تفشل
            with pytest.raises(Exception):
                sale = SaleService.create_sale(sale_data, test_user)
            
            # التحقق من عدم تأثر المخزون
            stock.refresh_from_db()
            assert stock.quantity == available_stock, \
                f" المخزون تأثر رغم الفشل: {stock.quantity} != {available_stock}"
            
            print(f" Correctly rejected: qty={quantity} > stock={available_stock}")
            
        except AssertionError:
            # إذا لم تفشل العملية، هذا bug!
            print(f" BUG: System allowed sale with insufficient stock!")
            print(f"   Requested: {quantity}, Available: {available_stock}")
            raise
    
    @settings(max_examples=10, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        price=st.decimals(
            min_value='0.000001',
            max_value='0.01',
            places=6
        )
    )
    def test_very_small_prices(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts,
        price
    ):
        """
        اختبار: أسعار صغيرة جداً (decimal precision)
        
        Property: النظام يجب أن يتعامل مع الأسعار الصغيرة جداً بدقة
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        assume(price > 0)
        
        print(f"\n� Testing tiny price: {price}")
        
        try:
            product = Product.objects.create(
                name='منتج رخيص جداً',
                sku=f'TINY_{str(price).replace(".", "_")}',
                category=test_category,
                unit=test_unit,
                cost_price=price * Decimal('0.5'),
                selling_price=price,
                is_active=True,
                created_by=test_user
            )
            
            Stock.objects.create(
                product=product,
                warehouse=test_warehouse,
                quantity=100,
                reserved_quantity=0
            )
            
            sale_data = {
                'customer_id': test_customer.id,
                'warehouse_id': test_warehouse.id,
                'payment_method': 'credit',
                'items': [
                    {
                        'product_id': product.id,
                        'quantity': 10,
                        'unit_price': price,
                        'discount': Decimal('0')
                    }
                ],
                'discount': Decimal('0'),
                'tax': Decimal('0')
            }
            
            sale = SaleService.create_sale(sale_data, test_user)
            
            # التحقق من الدقة
            expected_total = Decimal('10') * price
            assert abs(sale.total - expected_total) < Decimal('0.000001'), \
                f" خطأ في الدقة: {sale.total} != {expected_total}"
            
            print(f" Handled tiny price correctly: {price}")
            
        except Exception as e:
            print(f" FAILED with tiny price: {price}")
            print(f"   Error: {str(e)}")
            raise
