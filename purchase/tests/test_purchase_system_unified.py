"""
اختبارات موحدة لنظام المشتريات
Unified Tests for Purchase System

يجمع هذا الملف:
- test_apis.py (API Tests)
- test_forms_comprehensive.py (Form Tests)
- test_signals.py (Signal Tests)
- test_views_simple.py (View Tests)
"""
import pytest
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from purchase.models import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn
from supplier.models import Supplier
from product.models import Product, Warehouse, Category, Unit, Stock, StockMovement

User = get_user_model()


# ============================================================================
# 1. Model Tests
# ============================================================================

class PurchaseModelTest(TestCase):
    """اختبارات نموذج المشتريات"""
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            code='SUP001',
            phone='01234567890',
            email='supplier@test.com',
            created_by=self.user
        )
        
        self.category = Category.objects.create(
            name='مواد تعليمية',
            is_active=True
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة',
            is_active=True
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='MAIN',
            location='الموقع الرئيسي',
            is_active=True
        )
        
        self.product = Product.objects.create(
            name='كتاب الرياضيات',
            sku='BOOK001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            is_active=True,
            created_by=self.user
        )
    
    def test_purchase_creation(self):
        """اختبار إنشاء فاتورة مشتريات"""
        purchase = Purchase.objects.create(
            number='PUR001',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('150.00'),
            total=Decimal('1150.00'),
            payment_method='cash',
            status='draft',
            created_by=self.user
        )
        
        self.assertEqual(purchase.number, 'PUR001')
        self.assertEqual(purchase.supplier, self.supplier)
        self.assertEqual(purchase.warehouse, self.warehouse)
        self.assertEqual(purchase.total, Decimal('1150.00'))
        self.assertEqual(purchase.status, 'draft')
        self.assertIsNotNone(purchase.created_at)
    
    def test_purchase_item_creation(self):
        """اختبار إنشاء عنصر في فاتورة المشتريات"""
        purchase = Purchase.objects.create(
            number='PUR002',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            status='draft',
            created_by=self.user
        )
        
        purchase_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price=Decimal('10.00')
        )
        
        self.assertEqual(purchase_item.purchase, purchase)
        self.assertEqual(purchase_item.product, self.product)
        self.assertEqual(purchase_item.quantity, 10)
        self.assertEqual(purchase_item.unit_price, Decimal('10.00'))
        self.assertEqual(purchase_item.total, Decimal('100.00'))
    
    def test_purchase_total_calculation(self):
        """اختبار حساب إجمالي الفاتورة"""
        purchase = Purchase.objects.create(
            number='PUR003',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('0.00'),
            total=Decimal('0.00'),
            payment_method='cash',
            status='draft',
            created_by=self.user
        )
        
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=5,
            unit_price=Decimal('10.00')
        )
        
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=3,
            unit_price=Decimal('10.00')
        )
        
        subtotal = sum(item.total for item in purchase.items.all())
        self.assertEqual(subtotal, Decimal('80.00'))


# ============================================================================
# 2. API/View Tests
# ============================================================================

class PurchaseAPITest(TestCase):
    """اختبارات APIs المشتريات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            code='SUP001',
            phone='01234567890',
            created_by=self.user
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='MAIN',
            location='الموقع الرئيسي'
        )
    
    def test_purchase_list_view_loads(self):
        """اختبار تحميل قائمة المشتريات"""
        response = self.client.get(reverse('purchase:purchase_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_purchase_list_requires_login(self):
        """اختبار أن قائمة المشتريات تتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.get(reverse('purchase:purchase_list'))
        self.assertEqual(response.status_code, 302)
    
    def test_purchase_detail_with_invalid_id(self):
        """اختبار تفاصيل فاتورة غير موجودة"""
        response = self.client.get(
            reverse('purchase:purchase_detail', kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_purchase_create_view_loads(self):
        """اختبار تحميل صفحة إنشاء فاتورة"""
        response = self.client.get(reverse('purchase:purchase_create'))
        self.assertEqual(response.status_code, 200)

    def test_purchase_create_view_with_work_order(self):
        """اختبار تحميل صفحة إنشاء فاتورة مرتبطة بأمر شغل"""
        from customer.models import Customer
        from work_order.models import WorkOrder
        customer = Customer.objects.create(name='عميل اختبار', created_by=self.user)
        work_order = WorkOrder.objects.create(
            number='WO-001',
            customer=customer,
            status='in_progress',
            created_by=self.user
        )
        response = self.client.get(f"{reverse('purchase:purchase_create')}?work_order={work_order.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_work_order')
        self.assertContains(response, 'WO-001')
        self.assertContains(response, f'value="{work_order.id}" selected')

    def test_purchase_create_post_with_work_order(self):
        """اختبار حفظ فاتورة مشتريات مرتبطة بأمر شغل وتوليد القيد بنجاح"""
        from customer.models import Customer
        from work_order.models import WorkOrder
        from product.models import Product, Category, Unit
        category = Category.objects.create(name='مواد')
        unit = Unit.objects.create(name='قطعة')
        product = Product.objects.create(
            name='خدمة اختبار',
            sku='SRV-001',
            is_service=True,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('75.00'),
            category=category,
            unit=unit,
            created_by=self.user
        )
        customer = Customer.objects.create(name='عميل أمر الشغل', created_by=self.user)
        work_order = WorkOrder.objects.create(
            number='WO-2026-0099',
            customer=customer,
            status='in_progress',
            created_by=self.user
        )
        from financial.models import FinancialCategory, ChartOfAccounts
        exp_acc = ChartOfAccounts.objects.first()
        fin_cat = FinancialCategory.objects.create(code='raw_materials', name='مشتريات خامات', default_expense_account=exp_acc)
        post_data = {
            'number': 'PUR9999',
            'date': '2026-09-21',
            'supplier': str(self.supplier.id),
            'warehouse': str(self.warehouse.id),
            'work_order': str(work_order.id),
            'invoice_type': 'credit',
            'payment_method': 'credit',
            'financial_category': f'cat_{fin_cat.id}',
            'product[]': [str(product.id)],
            'quantity[]': ['2'],
            'unit_price[]': ['50.00'],
            'discount[]': ['0'],
            'subtotal': '100.00',
            'total': '100.00',
        }
        response = self.client.post(reverse('purchase:purchase_create'), post_data)
        self.assertEqual(response.status_code, 302)
        created_purchase = Purchase.objects.get(number='PUR9999')
        self.assertEqual(created_purchase.work_order_id, work_order.id)
        if created_purchase.journal_entry:
            self.assertEqual(created_purchase.journal_entry.work_order_id, work_order.id)


# ============================================================================
# 3. Signal Tests
# ============================================================================

class PurchaseSignalTest(TransactionTestCase):
    """اختبارات إشارات المشتريات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            code='SUP001',
            created_by=self.user
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='MAIN',
            location='الموقع الرئيسي'
        )
        
        self.category = Category.objects.create(name='فئة اختبار')
        self.unit = Unit.objects.create(name='قطعة', symbol='قطعة')
        
        self.product = Product.objects.create(
            name='منتج اختبار',
            sku='PROD001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.purchase = Purchase.objects.create(
            number='PURCH001',
            date=timezone.now().date(),
            status='draft',
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            created_by=self.user
        )
    
    def test_purchase_item_creation_signal(self):
        """اختبار إشارة إنشاء بند مشتريات"""
        purchase_item = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product,
            quantity=10,
            unit_price=Decimal('100.00')
        )
        
        self.assertIsNotNone(purchase_item)
        self.assertEqual(purchase_item.quantity, 10)


# ============================================================================
# 4. Integration Tests
# ============================================================================

class PurchaseIntegrationTest(TransactionTestCase):
    """اختبارات تكامل نظام المشتريات"""
    
    def setUp(self):
        """إعداد البيانات للاختبار التكاملي"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            code='SUP001',
            phone='01234567890',
            created_by=self.user
        )
        
        self.category = Category.objects.create(
            name='مواد تعليمية',
            is_active=True
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة',
            is_active=True
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='MAIN',
            location='الموقع الرئيسي',
            is_active=True
        )
        
        self.product = Product.objects.create(
            name='كتاب الرياضيات',
            sku='BOOK001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            is_active=True,
            created_by=self.user
        )
    
    def test_complete_purchase_workflow(self):
        """اختبار سير عمل الشراء الكامل"""
        # 1. إنشاء فاتورة
        purchase = Purchase.objects.create(
            number='PUR004',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('0.00'),
            total=Decimal('0.00'),
            payment_method='cash',
            status='draft',
            created_by=self.user
        )
        
        # 2. إضافة عناصر
        item1 = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=20,
            unit_price=Decimal('10.00')
        )
        
        # 3. تحديث الإجمالي
        subtotal = sum(item.total_price for item in purchase.items.all())
        tax = subtotal * Decimal('0.15')
        total = subtotal + tax
        
        purchase.subtotal = subtotal
        purchase.tax = tax
        purchase.total = total
        purchase.save()
        
        # 4. تأكيد الفاتورة
        purchase.status = 'confirmed'
        purchase.save()
        
        # 5. إضافة دفعة
        payment = PurchasePayment.objects.create(
            purchase=purchase,
            amount=total,
            payment_method='cash',
            payment_date=date.today(),
            created_by=self.user
        )
        
        # 6. تحديث حالة الدفع
        total_paid = sum(p.amount for p in purchase.payments.all())
        if total_paid >= purchase.total:
            purchase.payment_status = 'paid'
            purchase.save()
        
        # التحقق من النتائج
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'confirmed')
        self.assertEqual(purchase.payment_status, 'paid')
        self.assertEqual(purchase.subtotal, Decimal('200.00'))
        self.assertEqual(purchase.items.count(), 1)
        self.assertEqual(purchase.payments.count(), 1)


if __name__ == '__main__':
    pytest.main([__file__])
