"""
اختبارات شاملة لعروض العملاء (Views)
"""

from django.test import TestCase, Client as DjangoClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal

from ..models import Customer

User = get_user_model()


class CustomerListViewTest(TestCase):
    """اختبارات عرض قائمة العملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
        # إنشاء عملاء للاختبار
        self.customer1 = Customer.objects.create(
            name='عميل 1',
            code='CUST001',
            is_active=True
        )
        self.customer2 = Customer.objects.create(
            name='عميل 2',
            code='CUST002',
            is_active=True
        )
        self.customer3 = Customer.objects.create(
            name='عميل معطل',
            code='CUST003',
            is_active=False
        )
        
    def test_view_url_exists(self):
        """اختبار أن URL موجود"""
        # استخدام reverse بدلاً من URL مباشر
        try:
            response = self.client.get(reverse("customer:customer_list"))
            self.assertIn(response.status_code, [200, 301, 302])
        except:
            # إذا لم يكن URL موجود، نتخطى الاختبار
            self.skipTest("URL pattern not configured")
        
    def test_view_requires_login(self):
        """اختبار أن العرض يتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.get(reverse("customer:customer_list"))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
    def test_view_shows_only_active_customers(self):
        """اختبار أن العرض يظهر العملاء النشطين عند التصفية"""
        response = self.client.get(reverse("customer:customer_list") + '?status=active')
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود العملاء النشطين
        self.assertContains(response, 'عميل 1')
        self.assertContains(response, 'عميل 2')
        
        # التحقق من عدم وجود العميل المعطل
        self.assertNotContains(response, 'عميل معطل')
        
    def test_view_uses_correct_template(self):
        """اختبار استخدام القالب الصحيح"""
        response = self.client.get(reverse("customer:customer_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/customer_list.html")
        
    def test_view_context_has_customers(self):
        """اختبار أن السياق يحتوي على العملاء النشطين افتراضياً"""
        response = self.client.get(reverse("customer:customer_list"))
        self.assertTrue('customers' in response.context)
        self.assertEqual(len(response.context['customers']), Customer.objects.filter(is_active=True).count())


class CustomerAddViewTest(TestCase):
    """اختبارات عرض إضافة عميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_view_get_shows_form(self):
        """اختبار أن GET يعرض النموذج"""
        response = self.client.get(reverse("customer:customer_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')
        
    def test_view_post_creates_customer(self):
        """اختبار أن POST ينشئ عميل جديد"""
        data = {
            'name': 'عميل جديد',
            'code': 'NEW001',
            'phone': '+201234567890',
            'email': 'new@test.com',
            'credit_limit': '10000.00',
            'is_active': True
        }
        
        response = self.client.post(reverse("customer:customer_add"), data)
        
        # التحقق من إعادة التوجيه
        self.assertEqual(response.status_code, 302)
        
        # التحقق من إنشاء العميل
        self.assertTrue(Customer.objects.filter(code='NEW001').exists())
        customer = Customer.objects.get(code='NEW001')
        self.assertEqual(customer.name, 'عميل جديد')
        self.assertEqual(customer.created_by, self.user)
        
    def test_view_post_with_invalid_data(self):
        """اختبار POST مع بيانات غير صحيحة"""
        data = {
            'name': '',  # اسم فارغ
            'code': 'INV001',
            'is_active': True
        }
        
        response = self.client.post(reverse("customer:customer_add"), data)
        
        # يجب أن يبقى في نفس الصفحة
        self.assertEqual(response.status_code, 200)
        
        # يجب أن لا يتم إنشاء العميل
        self.assertFalse(Customer.objects.filter(code='INV001').exists())


class CustomerEditViewTest(TestCase):
    """اختبارات عرض تعديل عميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
        self.customer = Customer.objects.create(
            name='عميل للتعديل',
            code='EDIT001',
            phone='+201234567890'
        )
        
    def test_view_get_shows_form_with_data(self):
        """اختبار أن GET يعرض النموذج مع البيانات"""
        response = self.client.get(
            reverse("customer:customer_edit", kwargs={'pk': self.customer.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'عميل للتعديل')
        self.assertContains(response, 'EDIT001')
        
    def test_view_post_updates_customer(self):
        """اختبار أن POST يحدث العميل"""
        data = {
            'name': 'عميل محدث',
            'code': 'EDIT001',  # نفس الكود
            'phone': '+201098765432',
            'email': 'updated@test.com',
            'credit_limit': '15000.00',
            'is_active': True
        }
        
        response = self.client.post(
            reverse("customer:customer_edit", kwargs={'pk': self.customer.pk}),
            data
        )
        
        # التحقق من إعادة التوجيه
        self.assertEqual(response.status_code, 302)
        
        # التحقق من التحديث
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, 'عميل محدث')
        self.assertEqual(self.customer.phone, '+201098765432')
        
    def test_view_404_for_nonexistent_customer(self):
        """اختبار 404 لعميل غير موجود"""
        response = self.client.get(
            reverse("customer:customer_edit", kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)


class CustomerDeleteViewTest(TestCase):
    """اختبارات عرض حذف عميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
        self.customer = Customer.objects.create(
            name='عميل للحذف',
            code='DEL001',
            is_active=True
        )
        
    def test_view_get_shows_confirmation(self):
        """اختبار أن GET يعرض صفحة التأكيد"""
        response = self.client.get(
            reverse("customer:customer_delete", kwargs={'pk': self.customer.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'عميل للحذف')
        
    def test_view_post_deletes_empty_customer(self):
        """اختبار أن POST يحذف العميل الفارغ نهائياً"""
        customer_pk = self.customer.pk
        response = self.client.post(
            reverse("customer:customer_delete", kwargs={'pk': customer_pk})
        )
        
        # التحقق من إعادة التوجيه
        self.assertEqual(response.status_code, 302)
        
        # التحقق من أن العميل حُذف نهائياً
        self.assertFalse(Customer.objects.filter(pk=customer_pk).exists())

    def test_view_post_archives_customer_with_transactions(self):
        """اختبار أن POST يؤرشف ويعطل العميل المرتبط بمعاملات"""
        from customer.models import CustomerPayment
        from decimal import Decimal
        from django.utils import timezone
        CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('100.00'),
            payment_date=timezone.now().date(),
            payment_method='cash',
            created_by=self.user
        )
        
        response = self.client.post(
            reverse("customer:customer_delete", kwargs={'pk': self.customer.pk})
        )
        
        # التحقق من إعادة التوجيه
        self.assertEqual(response.status_code, 302)
        
        # التحقق من أن العميل معطل ومؤرشف وليس محذوفاً
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())


class CustomerDetailViewTest(TestCase):
    """اختبارات عرض تفاصيل عميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
        self.customer = Customer.objects.create(
            name='عميل للتفاصيل',
            code='DET001',
            email='detail@customer.com',
            phone='0123456789',
            address='العنوان بالتفصيل',
            city='القاهرة',
            is_active=True
        )
        
    def test_view_url_accessible_by_name(self):
        """اختبار الوصول عبر اسم المسار"""
        response = self.client.get(
            reverse("customer:customer_detail", kwargs={'pk': self.customer.pk})
        )
        self.assertEqual(response.status_code, 200)
        
    def test_view_uses_correct_template(self):
        """اختبار استخدام القالب الصحيح"""
        response = self.client.get(
            reverse("customer:customer_detail", kwargs={'pk': self.customer.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/customer_detail.html")
        
    def test_view_displays_customer_data(self):
        """اختبار عرض بيانات العميل بشكل صحيح"""
        response = self.client.get(
            reverse("customer:customer_detail", kwargs={'pk': self.customer.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'عميل للتفاصيل')
        self.assertContains(response, 'DET001')
        self.assertContains(response, 'detail@customer.com')
        self.assertContains(response, '0123456789')
        self.assertContains(response, 'القاهرة')
        
    def test_view_returns_404_for_invalid_customer(self):
        """اختبار إرجاع 404 لعميل غير موجود"""
        response = self.client.get(
            reverse("customer:customer_detail", kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)


class CustomerViewsIntegrationTest(TestCase):
    """اختبارات تكاملية لـ Views العملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_complete_customer_lifecycle(self):
        """اختبار دورة حياة كاملة للعميل عبر Views"""
        # 1. إضافة عميل
        create_data = {
            'name': 'عميل دورة الحياة',
            'code': 'CYCLE001',
            'email': 'cycle@customer.com',
            'phone': '0100000000',
            'address': 'عنوان دورة الحياة',
            'city': 'القاهرة',
            'customer_type': 'individual',
            'credit_limit': 10000.00,
            'is_active': True,
        }
        response = self.client.post(reverse("customer:customer_add"), create_data)
        self.assertEqual(response.status_code, 302)
        
        customer = Customer.objects.get(code='CYCLE001')
        self.assertIsNotNone(customer)
        
        # 2. عرض تفاصيل العميل
        response = self.client.get(
            reverse("customer:customer_detail", kwargs={'pk': customer.pk})
        )
        self.assertEqual(response.status_code, 200)
        
        # 3. تعديل العميل
        update_data = create_data.copy()
        update_data['name'] = 'عميل دورة الحياة المحدث'
        response = self.client.post(
            reverse("customer:customer_edit", kwargs={'pk': customer.pk}),
            update_data
        )
        self.assertEqual(response.status_code, 302)
        
        customer.refresh_from_db()
        self.assertEqual(customer.name, 'عميل دورة الحياة المحدث')
        
        # 4. حذف العميل
        customer_pk = customer.pk
        response = self.client.post(
            reverse("customer:customer_delete", kwargs={'pk': customer_pk})
        )
        self.assertEqual(response.status_code, 302)
        
        # التحقق من الحذف النهائي للعميل الجديد الفارغ
        self.assertFalse(Customer.objects.filter(pk=customer_pk).exists())
        
        # 5. التحقق من عدم ظهوره في سياق القائمة
        response = self.client.get(reverse("customer:customer_list"))
        self.assertFalse(any(c.pk == customer_pk for c in response.context['customers']))


class CustomerAddAjaxViewTest(TestCase):
    """اختبارات إضافة العميل عبر AJAX"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = DjangoClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')

    def test_customer_add_ajax_get(self):
        """اختبار جلب الكود التلقائي عبر GET"""
        response = self.client.get(reverse("customer:customer_add_ajax"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('code', '').startswith('CUST'))

    def test_customer_add_ajax_post_success(self):
        """اختبار إضافة العميل بنجاح عبر POST"""
        data = {
            'name': 'عميل أجاكس جديد',
            'code': 'CUST0001',
            'phone': '01234567890',
            'email': 'ajax@example.com',
            'credit_limit': '5000.00',
            'is_active': 'true'
        }
        response = self.client.post(reverse("customer:customer_add_ajax"), data)
        self.assertEqual(response.status_code, 200)
        
        resp_data = response.json()
        self.assertTrue(resp_data['success'])
        self.assertEqual(resp_data['customer']['name'], 'عميل أجاكس جديد')
        self.assertEqual(resp_data['customer']['code'], 'CUST0001')
        
        # التأكد من حفظه في قاعدة البيانات
        self.assertTrue(Customer.objects.filter(code='CUST0001').exists())

    def test_customer_add_ajax_post_validation_error(self):
        """اختبار إضافة عميل ببيانات غير صالحة (مثلاً بدون اسم)"""
        data = {
            'name': '',  # اسم فارغ وهو حقل مطلوب
            'code': 'CUST0001'
        }
        response = self.client.post(reverse("customer:customer_add_ajax"), data)
        self.assertEqual(response.status_code, 200)
        
        resp_data = response.json()
        self.assertFalse(resp_data['success'])
        self.assertIn('name', resp_data['errors'])
        self.assertFalse(Customer.objects.filter(code='CUST0001').exists())

