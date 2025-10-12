from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from sale.models import Customer, Sale, SaleItem, SaleReturn, SaleReturnItem
from product.models import Category, Unit, Product, Warehouse, Stock, Brand
from decimal import Decimal
import json

User = get_user_model()

class SaleViewsTest(TestCase):
    """
    اختبارات وظائف عرض المبيعات
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء عميل للاختبار
        self.customer = Customer.objects.create(
            name='عميل المبيعات',
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
        
        # إنشاء عملية بيع
        self.sale = Sale.objects.create(
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            reference='SL-001',
            status='completed',
            created_by=self.user
        )
        
        # إنشاء عناصر البيع
        self.sale_item1 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product1,
            quantity=5,
            price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.sale_item2 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product2,
            quantity=3,
            price=Decimal('300.00'),
            created_by=self.user
        )
    
    def test_sale_list_view(self):
        """
        اختبار صفحة قائمة المبيعات
        """
        url = reverse('sale:sale_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_list.html')
        self.assertContains(response, 'SL-001')
        self.assertContains(response, 'عميل المبيعات')
        self.assertContains(response, 'completed')
    
    def test_sale_detail_view(self):
        """
        اختبار صفحة تفاصيل المبيعات
        """
        url = reverse('sale:sale_detail', args=[self.sale.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_detail.html')
        self.assertContains(response, 'SL-001')
        self.assertContains(response, 'عميل المبيعات')
        self.assertContains(response, 'منتج اختبار 1')
        self.assertContains(response, 'منتج اختبار 2')
        self.assertContains(response, '5')  # كمية المنتج الأول
        self.assertContains(response, '3')  # كمية المنتج الثاني
        self.assertContains(response, '150.00')  # سعر المنتج الأول
        self.assertContains(response, '300.00')  # سعر المنتج الثاني
    
    def test_sale_create_view(self):
        """
        اختبار صفحة إنشاء مبيعات جديدة
        """
        url = reverse('sale:sale_create')
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_form.html')
        self.assertContains(response, 'إنشاء فاتورة مبيعات جديدة')
        
        # اختبار طلب POST لإنشاء مبيعات جديدة
        sale_data = {
            'date': timezone.now().date().isoformat(),
            'customer': self.customer.id,
            'warehouse': self.warehouse.id,
            'reference': 'SL-002',
            'status': 'draft',
            'notes': 'ملاحظات للمبيعات الجديدة',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product1.id,
            'items-0-quantity': '1',
            'items-0-price': '150.00',
        }
        
        response = self.client.post(url, sale_data, follow=True)
        
        # التحقق من نجاح الإنشاء
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود فاتورة المبيعات الجديدة
        new_sale = Sale.objects.filter(reference='SL-002').first()
        self.assertIsNotNone(new_sale)
        self.assertEqual(new_sale.customer, self.customer)
        self.assertEqual(new_sale.warehouse, self.warehouse)
        self.assertEqual(new_sale.status, 'draft')
        self.assertEqual(new_sale.notes, 'ملاحظات للمبيعات الجديدة')
        
        # التحقق من عناصر المبيعات
        self.assertEqual(new_sale.items.count(), 1)
        sale_item = new_sale.items.first()
        self.assertEqual(sale_item.product, self.product1)
        self.assertEqual(sale_item.quantity, 1)
        self.assertEqual(sale_item.price, Decimal('150.00'))
    
    def test_sale_edit_view(self):
        """
        اختبار صفحة تعديل المبيعات
        """
        url = reverse('sale:sale_edit', args=[self.sale.id])
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_form.html')
        self.assertContains(response, 'تعديل فاتورة مبيعات')
        self.assertContains(response, 'SL-001')
        
        # اختبار طلب POST لتعديل المبيعات
        edit_data = {
            'date': timezone.now().date().isoformat(),
            'customer': self.customer.id,
            'warehouse': self.warehouse.id,
            'reference': 'SL-001-EDIT',
            'status': 'pending',
            'notes': 'ملاحظات محدثة للمبيعات',
            'items-TOTAL_FORMS': '2',
            'items-INITIAL_FORMS': '2',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-id': self.sale_item1.id,
            'items-0-sale': self.sale.id,
            'items-0-product': self.product1.id,
            'items-0-quantity': '3',  # تغيير من 5 إلى 3
            'items-0-price': '160.00',  # تغيير من 150 إلى 160
            'items-1-id': self.sale_item2.id,
            'items-1-sale': self.sale.id,
            'items-1-product': self.product2.id,
            'items-1-quantity': '1',
            'items-1-price': '300.00',
        }
        
        response = self.client.post(url, edit_data, follow=True)
        
        # التحقق من نجاح التعديل
        self.assertEqual(response.status_code, 200)
        
        # التحقق من تحديث فاتورة المبيعات
        updated_sale = Sale.objects.get(id=self.sale.id)
        self.assertEqual(updated_sale.reference, 'SL-001-EDIT')
        self.assertEqual(updated_sale.status, 'pending')
        self.assertEqual(updated_sale.notes, 'ملاحظات محدثة للمبيعات')
        
        # التحقق من تحديث عناصر المبيعات
        updated_item1 = SaleItem.objects.get(id=self.sale_item1.id)
        self.assertEqual(updated_item1.quantity, 3)
        self.assertEqual(updated_item1.price, Decimal('160.00'))


class SaleReturnViewsTest(TestCase):
    """
    اختبارات وظائف عرض مرتجعات المبيعات
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء عميل للاختبار
        self.customer = Customer.objects.create(
            name='عميل المبيعات',
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
        
        # إنشاء عملية بيع
        self.sale = Sale.objects.create(
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            reference='SL-001',
            status='completed',
            created_by=self.user
        )
        
        # إنشاء عناصر البيع
        self.sale_item1 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product1,
            quantity=5,
            price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.sale_item2 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product2,
            quantity=3,
            price=Decimal('300.00'),
            created_by=self.user
        )
        
        # إنشاء مرتجع مبيعات
        self.sale_return = SaleReturn.objects.create(
            date=timezone.now().date(),
            sale=self.sale,
            warehouse=self.warehouse,
            reference='SRET-001',
            notes='ملاحظات للمرتجع',
            created_by=self.user
        )
        
        # إنشاء عناصر مرتجع المبيعات
        self.return_item1 = SaleReturnItem.objects.create(
            sale_return=self.sale_return,
            product=self.product1,
            quantity=2,
            price=Decimal('150.00'),
            reason='منتج تالف',
            created_by=self.user
        )
        
        self.return_item2 = SaleReturnItem.objects.create(
            sale_return=self.sale_return,
            product=self.product2,
            quantity=1,
            price=Decimal('300.00'),
            reason='منتج خاطئ',
            created_by=self.user
        )
    
    def test_sale_return_list_view(self):
        """
        اختبار صفحة قائمة مرتجعات المبيعات
        """
        url = reverse('sale:sale_return_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_return_list.html')
        self.assertContains(response, 'SRET-001')
        self.assertContains(response, 'عميل المبيعات')  # من خلال فاتورة البيع
    
    def test_sale_return_detail_view(self):
        """
        اختبار صفحة تفاصيل مرتجع المبيعات
        """
        url = reverse('sale:sale_return_detail', args=[self.sale_return.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_return_detail.html')
        self.assertContains(response, 'SRET-001')
        self.assertContains(response, 'SL-001')  # رقم فاتورة البيع الأصلية
        self.assertContains(response, 'منتج اختبار 1')
        self.assertContains(response, 'منتج اختبار 2')
        self.assertContains(response, '2')  # كمية المرتجع للمنتج الأول
        self.assertContains(response, '1')  # كمية المرتجع للمنتج الثاني
        self.assertContains(response, 'منتج تالف')
        self.assertContains(response, 'منتج خاطئ')
    
    def test_sale_return_create_view(self):
        """
        اختبار صفحة إنشاء مرتجع مبيعات جديد
        """
        url = reverse('sale:sale_return_create', args=[self.sale.id])
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/sale_return_form.html')
        self.assertContains(response, 'إنشاء مرتجع مبيعات جديد')
        self.assertContains(response, 'SL-001')  # رقم فاتورة البيع
        
        # اختبار طلب POST لإنشاء مرتجع مبيعات جديد
        return_data = {
            'date': timezone.now().date().isoformat(),
            'sale': self.sale.id,
            'warehouse': self.warehouse.id,
            'reference': 'SRET-002',
            'notes': 'ملاحظات للمرتجع الجديد',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product1.id,
            'items-0-quantity': '1',
            'items-0-price': '150.00',
            'items-0-reason': 'منتج غير مطابق للمواصفات',
        }
        
        response = self.client.post(url, return_data, follow=True)
        
        # التحقق من نجاح الإنشاء
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود مرتجع المبيعات الجديد
        new_return = SaleReturn.objects.filter(reference='SRET-002').first()
        self.assertIsNotNone(new_return)
        self.assertEqual(new_return.sale, self.sale)
        self.assertEqual(new_return.warehouse, self.warehouse)
        self.assertEqual(new_return.notes, 'ملاحظات للمرتجع الجديد')
        
        # التحقق من عناصر المرتجع
        self.assertEqual(new_return.items.count(), 1)
        return_item = new_return.items.first()
        self.assertEqual(return_item.product, self.product1)
        self.assertEqual(return_item.quantity, 1)
        self.assertEqual(return_item.price, Decimal('150.00'))
        self.assertEqual(return_item.reason, 'منتج غير مطابق للمواصفات')


class CustomerViewsTest(TestCase):
    """
    اختبارات وظائف عرض العملاء
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء عملاء للاختبار
        self.customer1 = Customer.objects.create(
            name='عميل اختبار 1',
            phone='01234567890',
            email='customer1@test.com',
            address='عنوان العميل 1',
            created_by=self.user
        )
        
        self.customer2 = Customer.objects.create(
            name='عميل اختبار 2',
            phone='09876543210',
            email='customer2@test.com',
            address='عنوان العميل 2',
            created_by=self.user
        )
    
    def test_customer_list_view(self):
        """
        اختبار صفحة قائمة العملاء
        """
        url = reverse('sale:customer_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/customer_list.html')
        self.assertContains(response, 'عميل اختبار 1')
        self.assertContains(response, 'عميل اختبار 2')
        self.assertContains(response, '01234567890')
        self.assertContains(response, '09876543210')
    
    def test_customer_detail_view(self):
        """
        اختبار صفحة تفاصيل العميل
        """
        url = reverse('sale:customer_detail', args=[self.customer1.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/customer_detail.html')
        self.assertContains(response, 'عميل اختبار 1')
        self.assertContains(response, '01234567890')
        self.assertContains(response, 'customer1@test.com')
        self.assertContains(response, 'عنوان العميل 1')
    
    def test_customer_create_view(self):
        """
        اختبار صفحة إنشاء عميل جديد
        """
        url = reverse('sale:customer_create')
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/customer_form.html')
        self.assertContains(response, 'إضافة عميل جديد')
        
        # اختبار طلب POST لإنشاء عميل جديد
        customer_data = {
            'name': 'عميل جديد',
            'phone': '01111222333',
            'email': 'new@customer.com',
            'address': 'عنوان العميل الجديد',
        }
        
        response = self.client.post(url, customer_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # التحقق من إنشاء العميل بنجاح
        new_customer = Customer.objects.filter(name='عميل جديد').first()
        self.assertIsNotNone(new_customer)
        self.assertEqual(new_customer.phone, '01111222333')
        self.assertEqual(new_customer.email, 'new@customer.com')
        self.assertEqual(new_customer.address, 'عنوان العميل الجديد')
    
    def test_customer_edit_view(self):
        """
        اختبار صفحة تعديل العميل
        """
        url = reverse('sale:customer_edit', args=[self.customer1.id])
        
        # اختبار طلب GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sale/customer_form.html')
        self.assertContains(response, 'تعديل عميل')
        self.assertContains(response, 'عميل اختبار 1')
        
        # اختبار طلب POST لتعديل العميل
        edit_data = {
            'name': 'عميل محدث',
            'phone': '01234567899',
            'email': 'updated@customer.com',
            'address': 'عنوان محدث للعميل',
        }
        
        response = self.client.post(url, edit_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # التحقق من تحديث العميل بنجاح
        updated_customer = Customer.objects.get(id=self.customer1.id)
        self.assertEqual(updated_customer.name, 'عميل محدث')
        self.assertEqual(updated_customer.phone, '01234567899')
        self.assertEqual(updated_customer.email, 'updated@customer.com')
        self.assertEqual(updated_customer.address, 'عنوان محدث للعميل')
    
    def test_customer_delete_view(self):
        """
        اختبار حذف عميل
        """
        url = reverse('sale:customer_delete', args=[self.customer1.id])
        response = self.client.post(url, follow=True)
        
        # التحقق من تحويل المستخدم بعد الحذف
        self.assertEqual(response.status_code, 200)
        
        # التحقق من حذف العميل بنجاح (الحذف الناعم)
        self.assertFalse(Customer.objects.filter(id=self.customer1.id).exists())
        
        # التحقق من وجود العميل في all_objects (حذف ناعم)
        self.assertTrue(Customer.all_objects.filter(id=self.customer1.id).exists()) 