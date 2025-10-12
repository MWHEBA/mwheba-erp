from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from product.models import Product, Category
from sale.models import Sale
from purchase.models import Purchase
from financial.models import Transaction
import json

User = get_user_model()

class PermissionTestCase(TestCase):
    """
    اختبارات الأذونات والصلاحيات في النظام
    """
    def setUp(self):
        """
        إعداد البيانات المطلوبة للاختبارات
        """
        # إنشاء المستخدمين
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        
        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='regularpass123'
        )
        
        self.manager_user = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='managerpass123'
        )
        
        self.finance_user = User.objects.create_user(
            username='finance',
            email='finance@example.com',
            password='financepass123'
        )
        
        # إنشاء المجموعات
        self.regular_group = Group.objects.create(name='موظف عادي')
        self.manager_group = Group.objects.create(name='مدير')
        self.finance_group = Group.objects.create(name='محاسب')
        
        # إعداد الأذونات حسب نوع المحتوى
        product_type = ContentType.objects.get_for_model(Product)
        category_type = ContentType.objects.get_for_model(Category)
        sale_type = ContentType.objects.get_for_model(Sale)
        purchase_type = ContentType.objects.get_for_model(Purchase)
        transaction_type = ContentType.objects.get_for_model(Transaction)
        
        # أذونات المنتجات
        view_product = Permission.objects.get(content_type=product_type, codename='view_product')
        add_product = Permission.objects.get(content_type=product_type, codename='add_product')
        change_product = Permission.objects.get(content_type=product_type, codename='change_product')
        delete_product = Permission.objects.get(content_type=product_type, codename='delete_product')
        
        # أذونات المبيعات
        view_sale = Permission.objects.get(content_type=sale_type, codename='view_sale')
        add_sale = Permission.objects.get(content_type=sale_type, codename='add_sale')
        change_sale = Permission.objects.get(content_type=sale_type, codename='change_sale')
        
        # أذونات المعاملات المالية
        view_transaction = Permission.objects.get(content_type=transaction_type, codename='view_transaction')
        add_transaction = Permission.objects.get(content_type=transaction_type, codename='add_transaction')
        
        # إضافة الأذونات للمجموعات
        # الموظف العادي - يمكنه فقط عرض المنتجات وإضافة المبيعات
        self.regular_group.permissions.add(view_product, view_sale, add_sale)
        
        # المدير - يمكنه إدارة المنتجات والمبيعات
        self.manager_group.permissions.add(
            view_product, add_product, change_product, delete_product,
            view_sale, add_sale, change_sale
        )
        
        # المحاسب - يمكنه عرض المبيعات وإدارة المعاملات المالية
        self.finance_group.permissions.add(
            view_sale, view_transaction, add_transaction
        )
        
        # إضافة المستخدمين للمجموعات
        self.regular_user.groups.add(self.regular_group)
        self.manager_user.groups.add(self.manager_group)
        self.finance_user.groups.add(self.finance_group)
        
        # إنشاء عميل HTTP
        self.client = Client()
        
        # إنشاء بيانات اختبار
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.admin_user
        )
        
        self.product = Product.objects.create(
            name='منتج اختبار',
            code='TEST001',
            category=self.category,
            purchase_price=100,
            sale_price=150,
            created_by=self.admin_user
        )
    
    def test_anonymous_access(self):
        """
        اختبار منع المستخدمين غير المسجلين من الوصول إلى صفحات النظام
        """
        # محاولة الوصول إلى صفحة المنتجات
        response = self.client.get(reverse('product:product_list'))
        self.assertNotEqual(response.status_code, 200)
        
        # محاولة الوصول إلى صفحة المبيعات
        response = self.client.get(reverse('sale:sale_list'))
        self.assertNotEqual(response.status_code, 200)
        
        # محاولة الوصول إلى صفحة التقارير المالية
        response = self.client.get(reverse('financial:transaction_list'))
        self.assertNotEqual(response.status_code, 200)
    
    def test_regular_user_permissions(self):
        """
        اختبار أذونات الموظف العادي
        """
        self.client.login(username='regular', password='regularpass123')
        
        # يمكنه عرض المنتجات
        response = self.client.get(reverse('product:product_list'))
        self.assertEqual(response.status_code, 200)
        
        # يمكنه عرض صفحة المبيعات
        response = self.client.get(reverse('sale:sale_list'))
        self.assertEqual(response.status_code, 200)
        
        # لا يمكنه إضافة منتج جديد
        response = self.client.get(reverse('product:product_create'))
        self.assertNotEqual(response.status_code, 200)
        
        # لا يمكنه الوصول إلى صفحة التقارير المالية
        response = self.client.get(reverse('financial:transaction_list'))
        self.assertNotEqual(response.status_code, 200)
    
    def test_manager_permissions(self):
        """
        اختبار أذونات المدير
        """
        self.client.login(username='manager', password='managerpass123')
        
        # يمكنه عرض المنتجات
        response = self.client.get(reverse('product:product_list'))
        self.assertEqual(response.status_code, 200)
        
        # يمكنه إضافة منتج جديد
        response = self.client.get(reverse('product:product_create'))
        self.assertEqual(response.status_code, 200)
        
        # يمكنه تحرير منتج
        response = self.client.get(
            reverse('product:product_edit', args=[self.product.id])
        )
        self.assertEqual(response.status_code, 200)
        
        # يمكنه عرض المبيعات وإنشاء مبيعات جديدة
        response = self.client.get(reverse('sale:sale_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('sale:sale_create'))
        self.assertEqual(response.status_code, 200)
        
        # لا يمكنه الوصول إلى المعاملات المالية
        response = self.client.get(reverse('financial:transaction_list'))
        self.assertNotEqual(response.status_code, 200)
    
    def test_finance_permissions(self):
        """
        اختبار أذونات المحاسب
        """
        self.client.login(username='finance', password='financepass123')
        
        # لا يمكنه إضافة أو تعديل المنتجات
        response = self.client.get(reverse('product:product_create'))
        self.assertNotEqual(response.status_code, 200)
        
        # يمكنه عرض المبيعات
        response = self.client.get(reverse('sale:sale_list'))
        self.assertEqual(response.status_code, 200)
        
        # يمكنه الوصول إلى المعاملات المالية
        response = self.client.get(reverse('financial:transaction_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('financial:transaction_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_model_permissions(self):
        """
        اختبار أذونات النماذج (عن طريق الكود بدلاً من HTTP)
        """
        # الموظف العادي لا يمكنه إنشاء منتجات
        self.assertFalse(self.regular_user.has_perm('product.add_product'))
        
        # المدير يمكنه إنشاء وتعديل المنتجات
        self.assertTrue(self.manager_user.has_perm('product.add_product'))
        self.assertTrue(self.manager_user.has_perm('product.change_product'))
        
        # المحاسب يمكنه إنشاء معاملات مالية
        self.assertTrue(self.finance_user.has_perm('financial.add_transaction'))
        
        # المحاسب لا يمكنه إنشاء منتجات
        self.assertFalse(self.finance_user.has_perm('product.add_product'))
    
    def test_superuser_permissions(self):
        """
        اختبار صلاحيات المدير العام (سوبر يوزر)
        """
        self.client.login(username='admin', password='adminpass123')
        
        # المدير العام يمكنه الوصول إلى جميع الصفحات
        response = self.client.get(reverse('product:product_list'))
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(reverse('product:product_create'))
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(reverse('sale:sale_list'))
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get(reverse('financial:transaction_list'))
        self.assertEqual(response.status_code, 200)
        
        # المدير العام لديه جميع الأذونات
        self.assertTrue(self.admin_user.has_perm('product.add_product'))
        self.assertTrue(self.admin_user.has_perm('sale.add_sale'))
        self.assertTrue(self.admin_user.has_perm('financial.add_transaction')) 