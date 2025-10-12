from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone
from purchase.models import Supplier, Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from product.models import Category, Unit, Product, Warehouse, Stock, Brand
from decimal import Decimal
import json

User = get_user_model()

class PurchaseViewsTest(TestCase):
    """
    اختبارات وظائف عرض المشتريات
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name='مورد المنتجات',
            phone='01234567890',
            created_by=self.user
        )
        
        # إنشاء مستودع
        self.warehouse = Warehouse.objects.create(
            name='المستودع الرئيسي',
            location='موقع المستودع',
            created_by=self.user
        )
        
        # إنشاء فئة ووحدة وعلامة تجارية
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.user
        )
        
        self.brand = Brand.objects.create(
            name='علامة تجارية',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            created_by=self.user
        )
        
        # إنشاء منتجات للاختبار
        self.product1 = Product.objects.create(
            name='منتج اختبار 1',
            code='TEST001',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('100.00'),
            sale_price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.product2 = Product.objects.create(
            name='منتج اختبار 2',
            code='TEST002',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('200.00'),
            sale_price=Decimal('300.00'),
            created_by=self.user
        )
        
        # إنشاء مخزون للمنتجات
        self.stock1 = Stock.objects.create(
            product=self.product1,
            warehouse=self.warehouse,
            quantity=10,
            created_by=self.user
        )
        
        self.stock2 = Stock.objects.create(
            product=self.product2,
            warehouse=self.warehouse,
            quantity=5,
            created_by=self.user
        )
        
        # إنشاء عملية شراء
        self.purchase = Purchase.objects.create(
            date=timezone.now().date(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            reference='PO-001',
            status='completed',
            created_by=self.user
        )
        
        # إنشاء عناصر الشراء
        self.purchase_item1 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product1,
            quantity=5,
            price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.purchase_item2 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product2,
            quantity=3,
            price=Decimal('200.00'),
            created_by=self.user
        )
    
    def test_purchase_list_view(self):
        """
        اختبار صفحة قائمة المشتريات
        """
        url = reverse('purchase:purchase_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_list.html')
        self.assertContains(response, 'PO-001')
        self.assertContains(response, 'مورد المنتجات')
        self.assertContains(response, 'completed')
    
    def test_purchase_detail_view(self):
        """
        اختبار صفحة تفاصيل المشتريات
        """
        url = reverse('purchase:purchase_detail', args=[self.purchase.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_detail.html')
        self.assertContains(response, 'PO-001')
        self.assertContains(response, 'مورد المنتجات')
        self.assertContains(response, 'منتج اختبار 1')
        self.assertContains(response, 'منتج اختبار 2')
        self.assertContains(response, '5') # كمية المنتج الأول
        self.assertContains(response, '3') # كمية المنتج الثاني
        self.assertContains(response, '100.00') # سعر المنتج الأول
        self.assertContains(response, '200.00') # سعر المنتج الثاني
    
    def test_purchase_create_view(self):
        """
        اختبار صفحة إنشاء مشتريات جديدة
        """
        url = reverse('purchase:purchase_create')
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_form.html')
        self.assertContains(response, 'إنشاء فاتورة مشتريات جديدة')
        
        # اختبار طلب POST لإنشاء مشتريات جديدة
        purchase_data = {
            'date': timezone.now().date().isoformat(),
            'supplier': self.supplier.id,
            'warehouse': self.warehouse.id,
            'reference': 'PO-002',
            'status': 'draft',
            'notes': 'ملاحظات للمشتريات الجديدة',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product1.id,
            'items-0-quantity': '2',
            'items-0-price': '100.00',
        }
        
        response = self.client.post(url, purchase_data, follow=True)
        
        # التحقق من نجاح الإنشاء
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود فاتورة المشتريات الجديدة
        new_purchase = Purchase.objects.filter(reference='PO-002').first()
        self.assertIsNotNone(new_purchase)
        self.assertEqual(new_purchase.supplier, self.supplier)
        self.assertEqual(new_purchase.warehouse, self.warehouse)
        self.assertEqual(new_purchase.status, 'draft')
        self.assertEqual(new_purchase.notes, 'ملاحظات للمشتريات الجديدة')
        
        # التحقق من عناصر المشتريات
        self.assertEqual(new_purchase.items.count(), 1)
        purchase_item = new_purchase.items.first()
        self.assertEqual(purchase_item.product, self.product1)
        self.assertEqual(purchase_item.quantity, 2)
        self.assertEqual(purchase_item.price, Decimal('100.00'))
    
    def test_purchase_edit_view(self):
        """
        اختبار صفحة تعديل المشتريات
        """
        url = reverse('purchase:purchase_edit', args=[self.purchase.id])
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_form.html')
        self.assertContains(response, 'تعديل فاتورة مشتريات')
        self.assertContains(response, 'PO-001')
        
        # اختبار طلب POST لتعديل المشتريات
        edit_data = {
            'date': timezone.now().date().isoformat(),
            'supplier': self.supplier.id,
            'warehouse': self.warehouse.id,
            'reference': 'PO-001-EDIT',
            'status': 'pending',
            'notes': 'ملاحظات محدثة للمشتريات',
            'items-TOTAL_FORMS': '2',
            'items-INITIAL_FORMS': '2',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-id': self.purchase_item1.id,
            'items-0-purchase': self.purchase.id,
            'items-0-product': self.product1.id,
            'items-0-quantity': '6',  # تغيير من 5 إلى 6
            'items-0-price': '110.00',  # تغيير من 100 إلى 110
            'items-1-id': self.purchase_item2.id,
            'items-1-purchase': self.purchase.id,
            'items-1-product': self.product2.id,
            'items-1-quantity': '3',
            'items-1-price': '200.00',
        }
        
        response = self.client.post(url, edit_data, follow=True)
        
        # التحقق من نجاح التعديل
        self.assertEqual(response.status_code, 200)
        
        # التحقق من تحديث فاتورة المشتريات
        updated_purchase = Purchase.objects.get(id=self.purchase.id)
        self.assertEqual(updated_purchase.reference, 'PO-001-EDIT')
        self.assertEqual(updated_purchase.status, 'pending')
        self.assertEqual(updated_purchase.notes, 'ملاحظات محدثة للمشتريات')
        
        # التحقق من تحديث عناصر المشتريات
        updated_item1 = PurchaseItem.objects.get(id=self.purchase_item1.id)
        self.assertEqual(updated_item1.quantity, 6)
        self.assertEqual(updated_item1.price, Decimal('110.00'))


class PurchaseReturnViewsTest(TestCase):
    """
    اختبارات وظائف عرض مرتجعات المشتريات
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name='مورد المنتجات',
            phone='01234567890',
            created_by=self.user
        )
        
        # إنشاء مستودع
        self.warehouse = Warehouse.objects.create(
            name='المستودع الرئيسي',
            location='موقع المستودع',
            created_by=self.user
        )
        
        # إنشاء فئة ووحدة وعلامة تجارية
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.user
        )
        
        self.brand = Brand.objects.create(
            name='علامة تجارية',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            created_by=self.user
        )
        
        # إنشاء منتجات للاختبار
        self.product1 = Product.objects.create(
            name='منتج اختبار 1',
            code='TEST001',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('100.00'),
            sale_price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.product2 = Product.objects.create(
            name='منتج اختبار 2',
            code='TEST002',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('200.00'),
            sale_price=Decimal('300.00'),
            created_by=self.user
        )
        
        # إنشاء مخزون للمنتجات
        self.stock1 = Stock.objects.create(
            product=self.product1,
            warehouse=self.warehouse,
            quantity=20,
            created_by=self.user
        )
        
        self.stock2 = Stock.objects.create(
            product=self.product2,
            warehouse=self.warehouse,
            quantity=15,
            created_by=self.user
        )
        
        # إنشاء عملية شراء
        self.purchase = Purchase.objects.create(
            date=timezone.now().date(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            reference='PO-001',
            status='completed',
            created_by=self.user
        )
        
        # إنشاء عناصر الشراء
        self.purchase_item1 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product1,
            quantity=10,
            price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.purchase_item2 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product2,
            quantity=5,
            price=Decimal('200.00'),
            created_by=self.user
        )
        
        # إنشاء مرتجع شراء
        self.purchase_return = PurchaseReturn.objects.create(
            date=timezone.now().date(),
            purchase=self.purchase,
            warehouse=self.warehouse,
            reference='PRET-001',
            notes='ملاحظات للمرتجع',
            created_by=self.user
        )
        
        # إنشاء عناصر مرتجع الشراء
        self.return_item1 = PurchaseReturnItem.objects.create(
            purchase_return=self.purchase_return,
            product=self.product1,
            quantity=2,
            price=Decimal('100.00'),
            reason='منتج تالف',
            created_by=self.user
        )
        
        self.return_item2 = PurchaseReturnItem.objects.create(
            purchase_return=self.purchase_return,
            product=self.product2,
            quantity=1,
            price=Decimal('200.00'),
            reason='منتج خاطئ',
            created_by=self.user
        )
    
    def test_purchase_return_list_view(self):
        """
        اختبار صفحة قائمة مرتجعات المشتريات
        """
        url = reverse('purchase:purchase_return_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_return_list.html')
        self.assertContains(response, 'PRET-001')
        self.assertContains(response, 'مورد المنتجات')  # من خلال فاتورة الشراء
    
    def test_purchase_return_detail_view(self):
        """
        اختبار صفحة تفاصيل مرتجع الشراء
        """
        url = reverse('purchase:purchase_return_detail', args=[self.purchase_return.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_return_detail.html')
        self.assertContains(response, 'PRET-001')
        self.assertContains(response, 'PO-001')  # رقم فاتورة الشراء الأصلية
        self.assertContains(response, 'منتج اختبار 1')
        self.assertContains(response, 'منتج اختبار 2')
        self.assertContains(response, '2')  # كمية المرتجع للمنتج الأول
        self.assertContains(response, '1')  # كمية المرتجع للمنتج الثاني
        self.assertContains(response, 'منتج تالف')
        self.assertContains(response, 'منتج خاطئ')
    
    def test_purchase_return_create_view(self):
        """
        اختبار صفحة إنشاء مرتجع شراء جديد
        """
        url = reverse('purchase:purchase_return_create', args=[self.purchase.id])
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/purchase_return_form.html')
        self.assertContains(response, 'إنشاء مرتجع مشتريات جديد')
        self.assertContains(response, 'PO-001')  # رقم فاتورة الشراء
        
        # اختبار طلب POST لإنشاء مرتجع شراء جديد
        return_data = {
            'date': timezone.now().date().isoformat(),
            'purchase': self.purchase.id,
            'warehouse': self.warehouse.id,
            'reference': 'PRET-002',
            'notes': 'ملاحظات للمرتجع الجديد',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product1.id,
            'items-0-quantity': '1',
            'items-0-price': '100.00',
            'items-0-reason': 'منتج غير مطابق للمواصفات',
        }
        
        response = self.client.post(url, return_data, follow=True)
        
        # التحقق من نجاح الإنشاء
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود مرتجع الشراء الجديد
        new_return = PurchaseReturn.objects.filter(reference='PRET-002').first()
        self.assertIsNotNone(new_return)
        self.assertEqual(new_return.purchase, self.purchase)
        self.assertEqual(new_return.warehouse, self.warehouse)
        self.assertEqual(new_return.notes, 'ملاحظات للمرتجع الجديد')
        
        # التحقق من عناصر المرتجع
        self.assertEqual(new_return.items.count(), 1)
        return_item = new_return.items.first()
        self.assertEqual(return_item.product, self.product1)
        self.assertEqual(return_item.quantity, 1)
        self.assertEqual(return_item.price, Decimal('100.00'))
        self.assertEqual(return_item.reason, 'منتج غير مطابق للمواصفات')


class SupplierViewsTest(TestCase):
    """
    اختبارات وظائف عرض الموردين
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء موردين للاختبار
        self.supplier1 = Supplier.objects.create(
            name='مورد اختبار 1',
            phone='01234567890',
            email='supplier1@test.com',
            address='عنوان المورد 1',
            created_by=self.user
        )
        
        self.supplier2 = Supplier.objects.create(
            name='مورد اختبار 2',
            phone='09876543210',
            email='supplier2@test.com',
            address='عنوان المورد 2',
            created_by=self.user
        )
    
    def test_supplier_list_view(self):
        """
        اختبار صفحة قائمة الموردين
        """
        url = reverse('purchase:supplier_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/supplier_list.html')
        self.assertContains(response, 'مورد اختبار 1')
        self.assertContains(response, 'مورد اختبار 2')
        self.assertContains(response, '01234567890')
        self.assertContains(response, '09876543210')
    
    def test_supplier_detail_view(self):
        """
        اختبار صفحة تفاصيل المورد
        """
        url = reverse('purchase:supplier_detail', args=[self.supplier1.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/supplier_detail.html')
        self.assertContains(response, 'مورد اختبار 1')
        self.assertContains(response, '01234567890')
        self.assertContains(response, 'supplier1@test.com')
        self.assertContains(response, 'عنوان المورد 1')
    
    def test_supplier_create_view(self):
        """
        اختبار صفحة إنشاء مورد جديد
        """
        url = reverse('purchase:supplier_create')
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/supplier_form.html')
        self.assertContains(response, 'إضافة مورد جديد')
        
        # اختبار طلب POST لإنشاء مورد جديد
        supplier_data = {
            'name': 'مورد جديد',
            'phone': '01111222333',
            'email': 'new@supplier.com',
            'address': 'عنوان المورد الجديد',
        }
        
        response = self.client.post(url, supplier_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # التحقق من إنشاء المورد بنجاح
        new_supplier = Supplier.objects.filter(name='مورد جديد').first()
        self.assertIsNotNone(new_supplier)
        self.assertEqual(new_supplier.phone, '01111222333')
        self.assertEqual(new_supplier.email, 'new@supplier.com')
        self.assertEqual(new_supplier.address, 'عنوان المورد الجديد')
    
    def test_supplier_edit_view(self):
        """
        اختبار صفحة تعديل مورد
        """
        url = reverse('purchase:supplier_edit', args=[self.supplier1.id])
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'purchase/supplier_form.html')
        self.assertContains(response, 'تعديل مورد')
        self.assertContains(response, 'مورد اختبار 1')
        
        # اختبار طلب POST لتعديل المورد
        edit_data = {
            'name': 'مورد محدث',
            'phone': '01234567899',
            'email': 'updated@supplier.com',
            'address': 'عنوان محدث للمورد',
        }
        
        response = self.client.post(url, edit_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # التحقق من تحديث المورد بنجاح
        updated_supplier = Supplier.objects.get(id=self.supplier1.id)
        self.assertEqual(updated_supplier.name, 'مورد محدث')
        self.assertEqual(updated_supplier.phone, '01234567899')
        self.assertEqual(updated_supplier.email, 'updated@supplier.com')
        self.assertEqual(updated_supplier.address, 'عنوان محدث للمورد')
    
    def test_supplier_delete_view(self):
        """
        اختبار حذف مورد
        """
        url = reverse('purchase:supplier_delete', args=[self.supplier1.id])
        response = self.client.post(url, follow=True)
        
        # التحقق من تحويل المستخدم بعد الحذف
        self.assertEqual(response.status_code, 200)
        
        # التحقق من حذف المورد بنجاح (الحذف الناعم)
        self.assertFalse(Supplier.objects.filter(id=self.supplier1.id).exists())
        
        # التحقق من وجود المورد في all_objects (حذف ناعم)
        self.assertTrue(Supplier.all_objects.filter(id=self.supplier1.id).exists()) 