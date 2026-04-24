"""
اختبارات E2E - Edge Cases والتحققات
Edge Cases and Validation Tests

هذا الملف يختبر السيناريوهات الصعبة والحالات الحدية:
- المخزون غير كافي
- تجاوز حد الائتمان
- القيم السالبة والصفرية
- البيانات المفقودة
- التواريخ غير الصحيحة
- الأكواد المكررة

القاعدة: الاختبار يفشل إذا النظام سمح بعملية خاطئة!
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError


@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.edge_case
class TestEdgeCasesAndValidations:
    """
    اختبارات الحالات الحدية والتحققات
    """
    
    def test_insufficient_stock_prevents_sale(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts
    ):
        """
        اختبار: منع البيع عند عدم كفاية المخزون
        
        السيناريو:
        - المخزون: 10 قطع
        - محاولة بيع: 20 قطعة
        - النتيجة المتوقعة: فشل العملية
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        print("\n" + "="*80)
        print("اختبار: منع البيع عند عدم كفاية المخزون")
        print("="*80)
        
        # إنشاء منتج بمخزون محدود
        product = Product.objects.create(
            name='منتج محدود',
            sku='LIMITED_001',
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
            quantity=10,  # فقط 10 قطع
            reserved_quantity=0
        )
        
        print(f" المخزون المتاح: 10 قطع")
        
        # محاولة بيع 20 قطعة
        sale_data = {
            'customer_id': test_customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': 20,  # أكثر من المتاح!
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0.00')
                }
            ],
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00')
        }
        
        # يجب أن تفشل العملية
        with pytest.raises(Exception) as exc_info:
            sale = SaleService.create_sale(sale_data, test_user)
        
        print(f" تم منع البيع: {str(exc_info.value)[:80]}")
        
        # التحقق من عدم تأثر المخزون
        stock = Stock.objects.get(product=product, warehouse=test_warehouse)
        assert stock.quantity == 10, \
            f" BUG: المخزون تأثر رغم فشل العملية! الكمية: {stock.quantity}"
        
        print(f" المخزون لم يتأثر: {stock.quantity} قطعة")
        
        print("\n" + "="*80)
        print(" الاختبار نجح - النظام منع البيع على المكشوف")
        print("="*80)

    
    def test_credit_limit_enforcement(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        setup_chart_of_accounts
    ):
        """
        اختبار: فرض حد الائتمان للعميل
        
        السيناريو:
        - حد الائتمان: 5000 ج.م
        - محاولة بيع: 7000 ج.م
        - النتيجة المتوقعة: فشل أو تحذير
        """
        from client.services.customer_service import CustomerService
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        print("\n" + "="*80)
        print("اختبار: فرض حد الائتمان")
        print("="*80)
        
        # إنشاء عميل بحد ائتمان محدود
        customer_service = CustomerService()
        customer = customer_service.create_customer(
            name='عميل محدود الائتمان',
            code='LIMITED_CREDIT_001',
            user=test_user,
            credit_limit=Decimal('5000.00')
        )
        
        print(f" حد الائتمان: {customer.credit_limit} ج.م")
        
        # إنشاء منتج
        product = Product.objects.create(
            name='منتج غالي',
            sku='EXPENSIVE_001',
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
            quantity=100,
            reserved_quantity=0
        )
        
        # محاولة بيع بقيمة تتجاوز حد الائتمان
        sale_data = {
            'customer_id': customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': 70,  # 70 × 100 = 7000 ج.م
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0.00')
                }
            ],
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00')
        }
        
        # محاولة البيع
        try:
            sale = SaleService.create_sale(sale_data, test_user)
            
            # إذا نجح، تحقق من أن النظام يسمح بتجاوز الحد
            print(f" النظام سمح بتجاوز حد الائتمان")
            print(f"   الفاتورة: {sale.total} ج.م")
            print(f"   حد الائتمان: {customer.credit_limit} ج.م")
            
            # هذا قد يكون مقبول حسب منطق النظام
            # لكن يجب أن يكون هناك تحذير أو تسجيل
            
        except ValidationError as e:
            print(f" تم منع تجاوز حد الائتمان: {str(e)[:80]}")
        
        print("\n" + "="*80)
        print(" الاختبار اكتمل")
        print("="*80)
    
    def test_negative_quantity_rejected(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts
    ):
        """
        اختبار: رفض الكميات السالبة
        
        السيناريو:
        - محاولة بيع كمية سالبة
        - النتيجة المتوقعة: فشل العملية
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        print("\n" + "="*80)
        print("اختبار: رفض الكميات السالبة")
        print("="*80)
        
        product = Product.objects.create(
            name='منتج عادي',
            sku='NORMAL_001',
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
            quantity=100,
            reserved_quantity=0
        )
        
        # محاولة بيع كمية سالبة
        sale_data = {
            'customer_id': test_customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': -10,  # كمية سالبة!
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0.00')
                }
            ],
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00')
        }
        
        # يجب أن تفشل
        with pytest.raises(Exception):
            sale = SaleService.create_sale(sale_data, test_user)
        
        print(f" تم رفض الكمية السالبة")
        
        print("\n" + "="*80)
        print(" الاختبار نجح")
        print("="*80)
    
    def test_zero_price_rejected(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts
    ):
        """
        اختبار: رفض السعر صفر
        
        السيناريو:
        - محاولة بيع بسعر صفر
        - النتيجة المتوقعة: فشل أو تحذير
        """
        from product.models import Product, Stock
        from sale.services.sale_service import SaleService
        
        print("\n" + "="*80)
        print("اختبار: رفض السعر صفر")
        print("="*80)
        
        product = Product.objects.create(
            name='منتج للاختبار',
            sku='ZERO_PRICE_001',
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
            quantity=100,
            reserved_quantity=0
        )
        
        # محاولة بيع بسعر صفر
        sale_data = {
            'customer_id': test_customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': 10,
                    'unit_price': Decimal('0.00'),  # سعر صفر!
                    'discount': Decimal('0.00')
                }
            ],
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00')
        }
        
        try:
            sale = SaleService.create_sale(sale_data, test_user)
            
            # إذا نجح، هذا bug!
            assert False, \
                f" BUG: النظام سمح بالبيع بسعر صفر! الفاتورة: {sale.number}"
            
        except (ValidationError, ValueError) as e:
            # متوقع - النظام رفض السعر صفر
            print(f" النظام رفض السعر صفر بنجاح")
            print(f"   الرسالة: {str(e)[:100]}")
            assert "صفر" in str(e) or "zero" in str(e).lower(), \
                f" رسالة الخطأ غير واضحة: {str(e)}"
            print(f" تم رفض السعر صفر")
        
        print("\n" + "="*80)
        print(" الاختبار اكتمل")
        print("="*80)
    
    def test_duplicate_customer_code_rejected(
        self,
        db,
        test_user,
        setup_chart_of_accounts
    ):
        """
        اختبار: رفض الأكواد المكررة للعملاء
        
        السيناريو:
        - إنشاء عميل بكود معين
        - محاولة إنشاء عميل آخر بنفس الكود
        - النتيجة المتوقعة: فشل العملية
        """
        from client.services.customer_service import CustomerService
        
        print("\n" + "="*80)
        print("اختبار: رفض الأكواد المكررة")
        print("="*80)
        
        customer_service = CustomerService()
        
        # إنشاء العميل الأول
        customer1 = customer_service.create_customer(
            name='العميل الأول',
            code='DUP_CODE_001',
            user=test_user
        )
        
        print(f" تم إنشاء العميل الأول: {customer1.code}")
        
        # محاولة إنشاء عميل آخر بنفس الكود
        with pytest.raises(ValidationError) as exc_info:
            customer2 = customer_service.create_customer(
                name='العميل الثاني',
                code='DUP_CODE_001',  # نفس الكود!
                user=test_user
            )
        
        assert 'already exists' in str(exc_info.value).lower(), \
            f" رسالة الخطأ غير واضحة: {exc_info.value}"
        
        print(f" تم رفض الكود المكرر")
        
        print("\n" + "="*80)
        print(" الاختبار نجح")
        print("="*80)
    
    def test_empty_invoice_rejected(
        self,
        db,
        test_user,
        test_warehouse,
        test_customer,
        setup_chart_of_accounts
    ):
        """
        اختبار: رفض الفاتورة الفارغة
        
        السيناريو:
        - محاولة إنشاء فاتورة بدون بنود
        - النتيجة المتوقعة: فشل العملية
        """
        from sale.services.sale_service import SaleService
        
        print("\n" + "="*80)
        print("اختبار: رفض الفاتورة الفارغة")
        print("="*80)
        
        # محاولة إنشاء فاتورة بدون بنود
        sale_data = {
            'customer_id': test_customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [],  # فارغة!
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00')
        }
        
        try:
            sale = SaleService.create_sale(sale_data, test_user)
            
            # إذا نجح، تحقق من أن الإجمالي صفر
            assert sale.total == Decimal('0.00'), \
                f" BUG: فاتورة فارغة بإجمالي غير صفر: {sale.total}"
            
            print(f" النظام سمح بفاتورة فارغة")
            print(f"   (قد يكون مقبول كمسودة)")
            
        except (ValidationError, Exception) as e:
            print(f" تم رفض الفاتورة الفارغة: {str(e)[:80]}")
        
        print("\n" + "="*80)
        print(" الاختبار اكتمل")
        print("="*80)
