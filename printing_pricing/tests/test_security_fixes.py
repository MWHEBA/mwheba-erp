from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
import json

from printing_pricing.models import PrintingOrder, OrderMaterial, OrderService, OrderSummary, PricingStatus, CalculationType
from printing_pricing.services import OrderValidator
from customer.models import Customer

User = get_user_model()

class PrintingPricingSecurityTests(TestCase):
    """اختبارات الأمان والتحقق لنظام تسعير المطبوعات"""

    def setUp(self):
        # إنشاء مستخدمين
        self.staff_user = User.objects.create_user(
            username="staff_user_test",
            email="staff@test.com",
            password="StaffPassword123",
            is_staff=True
        )
        self.regular_user = User.objects.create_user(
            username="regular_user_test",
            email="user@test.com",
            password="UserPassword123"
        )
        self.other_user = User.objects.create_user(
            username="other_user_test",
            email="other@test.com",
            password="OtherPassword123"
        )

        # إنشاء عميل
        self.customer = Customer.objects.create(
            name="عميل تجريبي",
            is_active=True
        )

        # إنشاء طلبات تسعير للمستخدم العادي
        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            title="طلب عادي",
            order_type="book",
            quantity=1000,
            created_by=self.regular_user
        )
        # إنشاء ملخص الطلب
        self.summary = OrderSummary.objects.create(order=self.order)

        self.client_regular = Client()
        self.client_regular.login(username="regular_user_test", password="UserPassword123")

        self.client_other = Client()
        self.client_other.login(username="other_user_test", password="OtherPassword123")

        self.client_staff = Client()
        self.client_staff.login(username="staff_user_test", password="StaffPassword123")

    def test_get_decimal_helper(self):
        """اختبار دالة _to_decimal المساعدة للتحقق من سلامة التحويل"""
        from printing_pricing.services import PrintingCalculationEngine

        # مدخلات صحيحة
        self.assertEqual(PrintingCalculationEngine._to_decimal(10), Decimal('10'))
        self.assertEqual(PrintingCalculationEngine._to_decimal('5.5'), Decimal('5.5'))

        # مدخلات مفقودة أو غير صالحة
        self.assertEqual(PrintingCalculationEngine._to_decimal(None, Decimal('1.00')), Decimal('1.00'))
        self.assertEqual(PrintingCalculationEngine._to_decimal('abc', Decimal('2.00')), Decimal('2.00'))

    def test_parameter_boundary_validations(self):
        """اختبار صمامات الأمان للأبعاد الصفرية وتجاوز الأبعاد لمنع التلاعب المالي أو كراش النظام"""
        from printing_pricing.services import PrintingCalculationEngine

        # أبعاد تتجاوز الفرخ يجب أن ترجع خطأ
        result = PrintingCalculationEngine.calculate({'width': 120, 'height': 85})
        self.assertFalse(result['success'])
        self.assertEqual(result['error_code'], 'DIMENSIONS_EXCEED_SHEET')

        # كمية سالبة أو صفرية تعالج بأمان
        result = PrintingCalculationEngine.calculate({'quantity': -500})
        self.assertTrue(result['success'])
        self.assertGreater(result['totals']['total_selling_price'], 0)

    def test_idor_on_order_summary_api(self):
        """اختبار منع الوصول لملخص طلب مستخدم آخر (IDOR)"""
        url = reverse('printing_pricing:api_order_summary', kwargs={'order_id': self.order.id})

        # مالك الطلب يجب أن ينجح
        response = self.client_regular.get(url)
        self.assertEqual(response.status_code, 200)

        # مستخدم آخر يجب أن يفشل بـ 403 Forbidden
        response = self.client_other.get(url)
        self.assertEqual(response.status_code, 403)

        # مستخدم موظف/إداري يجب أن ينجح
        response = self.client_staff.get(url)
        self.assertEqual(response.status_code, 200)


    def test_idor_on_order_views_actions(self):
        """AJAX اختبار حماية العمليات السريعة ضد ثغرة الـ"""
        # 1. حساب التكلفة
        url_calc = reverse('printing_pricing:calculate_cost', kwargs={'pk': self.order.id})
        response = self.client_other.post(url_calc)
        self.assertEqual(response.status_code, 403)

        # 2. نسخ الطلب
        url_dup = reverse('printing_pricing:duplicate_order', kwargs={'pk': self.order.id})
        response = self.client_other.post(url_dup)
        self.assertEqual(response.status_code, 403)

        # 3. اعتماد الطلب
        url_app = reverse('printing_pricing:approve_order', kwargs={'pk': self.order.id})
        response = self.client_other.post(url_app)
        self.assertEqual(response.status_code, 403)

    def test_settings_privilege_escalation(self):
        """اختبار منع وصول المستخدمين العاديين لصفحات الإعدادات"""
        url_settings = reverse('printing_pricing:settings_home')
        
        # مستخدم عادي يجب أن يمنع بـ 403 PermissionDenied
        response = self.client_regular.get(url_settings)
        self.assertEqual(response.status_code, 403)

        # مستخدم إداري يجب أن ينجح
        response = self.client_staff.get(url_settings)
        self.assertEqual(response.status_code, 200)

        # اختبار واجهة إعدادات مقاسات الورق
        url_paper_sizes = reverse('printing_pricing:paper_size_list')
        response = self.client_regular.get(url_paper_sizes)
        self.assertEqual(response.status_code, 403)

        response = self.client_staff.get(url_paper_sizes)
        self.assertEqual(response.status_code, 200)

    def test_empty_order_approval_rejection(self):
        """اختبار التحقق من صحة واكتمال الطلب قبل اعتماده"""
        url_app = reverse('printing_pricing:approve_order', kwargs={'pk': self.order.id})
        
        # الطلب خالي من المواد والتكلفة الإجمالية صفر، لذا يجب رفض الاعتماد وإرجاع 400 Bad Request
        response = self.client_regular.post(url_app)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('لا يمكن اعتماد الطلب', data['error'])
