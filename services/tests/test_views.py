from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

# استيراد آمن للنماذج المرتبطة
try:
    from supplier.models import SupplierType, SpecializedService, Supplier
except ImportError:
    # إنشاء نماذج وهمية للاختبار
    class SupplierType:
        objects = None
        
    class SpecializedService:
        objects = None
        
    class Supplier:
        objects = None

User = get_user_model()


class ServicesViewsTestCase(TestCase):
    """اختبارات شاملة لـ Views الخدمات"""
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # تسجيل دخول المستخدم
        self.client.login(username='testuser', password='testpass123')
        
        # إنشاء بيانات اختبار إذا كانت النماذج متاحة
        if all([SupplierType, SpecializedService, Supplier]):
            self.supplier_type = SupplierType.objects.create(
                name='طباعة أوفست',
                code='offset_printing',
                slug='offset-printing',
                icon='fas fa-print',
                display_order=1,
                is_active=True
            )
            
            self.supplier = Supplier.objects.create(
                name='مطبعة الاختبار',
                phone='01234567890',
                email='supplier@test.com',
                address='عنوان المطبعة',
                is_active=True,
                supplier_rating=4.5
            )
            
            self.service = SpecializedService.objects.create(
                name='ماكينة طباعة اختبار',
                category=self.supplier_type,
                supplier=self.supplier,
                setup_cost=Decimal('100.00'),
                impression_cost=Decimal('0.50'),
                is_active=True
            )
        else:
            self.supplier_type = None
            self.supplier = None
            self.service = None


class ServicesHomeViewTest(ServicesViewsTestCase):
    """اختبارات الصفحة الرئيسية للخدمات"""
    
    def test_services_home_view_get(self):
        """اختبار عرض الصفحة الرئيسية للخدمات"""
        url = reverse('services:services_home')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'الخدمات المتخصصة')
        
        # التحقق من وجود المتغيرات في السياق
        self.assertIn('service_types', response.context)
        self.assertIn('total_services', response.context)
        self.assertIn('total_suppliers', response.context)
        self.assertIn('total_categories', response.context)
        self.assertIn('avg_rating', response.context)
        self.assertIn('page_title', response.context)
        self.assertIn('breadcrumb_items', response.context)
        
        # التحقق من القيم
        self.assertEqual(response.context['page_title'], 'الخدمات المتخصصة')
        self.assertIsInstance(response.context['total_services'], int)
        self.assertIsInstance(response.context['total_suppliers'], int)
        self.assertIsInstance(response.context['total_categories'], int)
        self.assertIsInstance(response.context['avg_rating'], (int, float))
    
    def test_services_home_view_requires_login(self):
        """اختبار أن الصفحة تتطلب تسجيل الدخول"""
        self.client.logout()
        url = reverse('services:services_home')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_services_home_context_data(self):
        """اختبار بيانات السياق للصفحة الرئيسية"""
        url = reverse('services:services_home')
        response = self.client.get(url)
        
        # التحقق من breadcrumb
        breadcrumb = response.context['breadcrumb_items']
        self.assertIsInstance(breadcrumb, list)
        self.assertGreaterEqual(len(breadcrumb), 2)
        
        # التحقق من العنصر الأول في breadcrumb
        home_item = breadcrumb[0]
        self.assertEqual(home_item['title'], 'الرئيسية')
        self.assertIn('url', home_item)
        self.assertEqual(home_item['icon'], 'fas fa-home')
        
        # التحقق من العنصر الأخير
        services_item = breadcrumb[-1]
        self.assertEqual(services_item['title'], 'الخدمات المتخصصة')
        self.assertTrue(services_item.get('active', False))
    
    def test_services_home_statistics_calculation(self):
        """اختبار حساب الإحصائيات"""
        if not all([SupplierType, SpecializedService, Supplier]):
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:services_home')
        response = self.client.get(url)
        
        # التحقق من أن الإحصائيات تحسب بشكل صحيح
        context = response.context
        
        # يجب أن تكون القيم غير سالبة
        self.assertGreaterEqual(context['total_services'], 0)
        self.assertGreaterEqual(context['total_suppliers'], 0)
        self.assertGreaterEqual(context['total_categories'], 0)
        self.assertGreaterEqual(context['avg_rating'], 0)
        
        # التحقق من أن متوسط التقييم في النطاق المناسب
        self.assertLessEqual(context['avg_rating'], 5.0)


class CategoryDetailViewTest(ServicesViewsTestCase):
    """اختبارات صفحة تفاصيل الفئة"""
    
    def test_category_detail_view_get(self):
        """اختبار عرض تفاصيل الفئة"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.supplier_type.name)
        
        # التحقق من وجود المتغيرات في السياق
        self.assertIn('category', response.context)
        self.assertIn('services', response.context)
        self.assertIn('suppliers', response.context)
        self.assertIn('services_count', response.context)
        self.assertIn('suppliers_count', response.context)
        self.assertIn('avg_price', response.context)
        self.assertIn('avg_rating', response.context)
        self.assertIn('category_service_headers', response.context)
        self.assertIn('category_service_actions', response.context)
        
        # التحقق من أن الفئة صحيحة
        self.assertEqual(response.context['category'], self.supplier_type)
    
    def test_category_detail_view_404_for_inactive_category(self):
        """اختبار عرض 404 للفئة غير النشطة"""
        if not SupplierType:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        # إنشاء فئة غير نشطة
        inactive_category = SupplierType.objects.create(
            name='فئة غير نشطة',
            code='inactive_category',
            slug='inactive-category',
            is_active=False
        )
        
        url = reverse('services:category_detail', kwargs={'slug': inactive_category.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_category_detail_view_404_for_nonexistent_category(self):
        """اختبار عرض 404 للفئة غير الموجودة"""
        url = reverse('services:category_detail', kwargs={'slug': 'nonexistent-category'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_category_detail_view_requires_login(self):
        """اختبار أن الصفحة تتطلب تسجيل الدخول"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        self.client.logout()
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def test_category_detail_filtering_by_supplier(self):
        """اختبار فلترة الخدمات حسب المورد"""
        if not all([self.supplier_type, self.supplier]):
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url, {'supplier': self.supplier.id})
        
        self.assertEqual(response.status_code, 200)
        
        # التحقق من أن الفلترة تعمل
        services = response.context['services']
        for service in services:
            self.assertEqual(service.supplier_id, self.supplier.id)
    
    def test_category_detail_filtering_by_price_range(self):
        """اختبار فلترة الخدمات حسب نطاق السعر"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        
        # اختبار الحد الأدنى للسعر
        response = self.client.get(url, {'min_price': '50'})
        self.assertEqual(response.status_code, 200)
        
        # اختبار الحد الأقصى للسعر
        response = self.client.get(url, {'max_price': '200'})
        self.assertEqual(response.status_code, 200)
        
        # اختبار نطاق السعر
        response = self.client.get(url, {'min_price': '50', 'max_price': '200'})
        self.assertEqual(response.status_code, 200)
    
    def test_category_detail_invalid_price_filters(self):
        """اختبار التعامل مع فلاتر السعر غير الصحيحة"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        
        # اختبار قيم غير صحيحة للسعر
        response = self.client.get(url, {'min_price': 'invalid', 'max_price': 'invalid'})
        self.assertEqual(response.status_code, 200)  # يجب أن تعمل بدون خطأ
    
    def test_category_detail_offset_printing_headers(self):
        """اختبار headers خاصة بطباعة الأوفست"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url)
        
        headers = response.context['category_service_headers']
        self.assertIsInstance(headers, list)
        self.assertGreater(len(headers), 0)
        
        # التحقق من وجود header للماكينة إذا كانت الفئة طباعة أوفست
        if self.supplier_type.code == 'offset_printing':
            header_keys = [h['key'] for h in headers]
            self.assertIn('name', header_keys)
            self.assertIn('supplier.name', header_keys)
            self.assertIn('impression_cost', header_keys)
    
    def test_category_detail_breadcrumb(self):
        """اختبار breadcrumb لصفحة تفاصيل الفئة"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url)
        
        breadcrumb = response.context['breadcrumb_items']
        self.assertIsInstance(breadcrumb, list)
        self.assertEqual(len(breadcrumb), 3)
        
        # التحقق من العناصر
        self.assertEqual(breadcrumb[0]['title'], 'الرئيسية')
        self.assertEqual(breadcrumb[1]['title'], 'الخدمات المتخصصة')
        self.assertEqual(breadcrumb[2]['title'], self.supplier_type.name)
        self.assertTrue(breadcrumb[2].get('active', False))
    
    def test_category_detail_statistics(self):
        """اختبار إحصائيات الفئة"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url)
        
        context = response.context
        
        # التحقق من أن الإحصائيات صحيحة
        self.assertIsInstance(context['services_count'], int)
        self.assertIsInstance(context['suppliers_count'], int)
        self.assertGreaterEqual(context['services_count'], 0)
        self.assertGreaterEqual(context['suppliers_count'], 0)
        self.assertGreaterEqual(context['avg_rating'], 0)
        self.assertLessEqual(context['avg_rating'], 5.0)
    
    def test_category_detail_page_title_and_icon(self):
        """اختبار عنوان الصفحة والأيقونة"""
        if not self.supplier_type:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        response = self.client.get(url)
        
        context = response.context
        
        # التحقق من عنوان الصفحة
        expected_title = f"خدمات {self.supplier_type.name}"
        self.assertEqual(context['page_title'], expected_title)
        
        # التحقق من الأيقونة
        expected_icon = self.supplier_type.icon or "fas fa-cogs"
        self.assertEqual(context['page_icon'], expected_icon)


class ServicesIntegrationTest(ServicesViewsTestCase):
    """اختبارات التكامل للخدمات"""
    
    def test_services_workflow(self):
        """اختبار تدفق العمل الكامل للخدمات"""
        if not all([self.supplier_type, self.service]):
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        # 1. زيارة الصفحة الرئيسية
        home_url = reverse('services:services_home')
        home_response = self.client.get(home_url)
        self.assertEqual(home_response.status_code, 200)
        
        # 2. التحقق من وجود الفئة في الصفحة الرئيسية
        self.assertContains(home_response, self.supplier_type.name)
        
        # 3. زيارة صفحة تفاصيل الفئة
        detail_url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        
        # 4. التحقق من وجود الخدمة في صفحة التفاصيل
        self.assertContains(detail_response, self.service.name)
        
        # 5. اختبار الفلترة
        filtered_response = self.client.get(detail_url, {'supplier': self.supplier.id})
        self.assertEqual(filtered_response.status_code, 200)
    
    def test_services_empty_state(self):
        """اختبار حالة عدم وجود خدمات"""
        if not SupplierType:
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        # إنشاء فئة بدون خدمات
        empty_category = SupplierType.objects.create(
            name='فئة فارغة',
            code='empty_category',
            slug='empty-category',
            is_active=True
        )
        
        url = reverse('services:category_detail', kwargs={'slug': empty_category.slug})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['services_count'], 0)
        self.assertEqual(response.context['suppliers_count'], 0)
    
    def test_services_performance(self):
        """اختبار أداء صفحات الخدمات"""
        if not all([SupplierType, SpecializedService, Supplier]):
            self.skipTest("النماذج المطلوبة غير متاحة")
        
        # إنشاء بيانات إضافية للاختبار
        for i in range(10):
            supplier = Supplier.objects.create(
                name=f'مورد {i}',
                phone=f'0123456789{i}',
                is_active=True
            )
            
            SpecializedService.objects.create(
                name=f'خدمة {i}',
                category=self.supplier_type,
                supplier=supplier,
                setup_cost=Decimal(f'{100 + i}.00'),
                is_active=True
            )
        
        # اختبار الصفحة الرئيسية
        home_url = reverse('services:services_home')
        home_response = self.client.get(home_url)
        self.assertEqual(home_response.status_code, 200)
        
        # اختبار صفحة التفاصيل
        detail_url = reverse('services:category_detail', kwargs={'slug': self.supplier_type.slug})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        
        # التحقق من أن البيانات تظهر بشكل صحيح
        self.assertGreater(detail_response.context['services_count'], 1)
        self.assertGreater(detail_response.context['suppliers_count'], 1)
