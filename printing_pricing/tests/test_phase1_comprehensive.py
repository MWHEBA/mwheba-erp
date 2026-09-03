import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from customer.models import Customer
from work_order.models import WorkOrder
from printing_pricing.models import (
    PrintingOrder, PaperSpecification,
    OrderMaterial, OrderService, OrderSummary, PricingStatus, CalculationType
)
from printing_pricing.services import PrintingCalculationEngine
from core.templatetags.pricing_filters import status_badge

User = get_user_model()


@pytest.mark.django_db
class TestPhase1Comprehensive:
    """حزمة الاختبارات الشاملة للمرحلة الأولى"""

    def setup_method(self):
        self.user = User.objects.create_user(
            username="test_agency_admin",
            email="admin@agency.com",
            password="StrongPassword123",
            is_staff=True
        )
        self.sales_rep = User.objects.create_user(
            username="test_sales_rep",
            email="sales@agency.com",
            password="SalesRepPassword123"
        )
        self.customer = Customer.objects.create(
            name="شركة الأمل للدعاية",
            customer_type="company",
            phone="01012345678",
            phone_primary="01012345678",
            address="15 شارع مصدق، الدقي، الجيزة",
            credit_limit=Decimal('50000.00'),
            balance=Decimal('12500.00'),
            is_active=True
        )
        self.client_auth = Client()
        self.client_auth.login(username="test_agency_admin", password="StrongPassword123")

    def test_01_canonical_truth_and_pr_numbering(self):
        """التحقق من بادئة PR- واستقلال مسودة التسعير عن صالة الإنتاج وتوليد أمر الشغل عند الاعتماد"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title="حملة مطبوعات الصيف",
            order_type="brochure",
            quantity=5000,
            final_price=Decimal('12000.00'),
            created_by=self.user
        )
        
        # 1. التحقق من بادئة PR عبر SequenceService الموحد
        assert order.order_number.startswith("PR")
        # 2. التحقق من استقلال المسودة (عدم تلويث صالة الإنتاج بأمر شغل تلقائي للمسودة)
        assert order.work_order is None
        # 3. توليد أمر الشغل التنفيذي عند الاعتماد
        work_order = order.create_work_order(user=self.user)
        assert order.work_order is not None
        assert order.work_order.customer == self.customer
        # 4. التحقق من customer_name و customer و final_price
        assert order.customer_name == self.customer.name
        assert order.customer == self.customer
        assert order.final_price == Decimal('12000.00')

    def test_02_multi_part_specifications_foreign_key(self):
        """التحقق من دعم المطبوعات متعددة الأجزاء (غلاف + داخلي) عبر علاقة ForeignKey"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title="كتالوج سنوي 48 صفحة",
            order_type="catalog",
            quantity=1000,
            created_by=self.user
        )
        
        # جزء 1: ورق الغلاف (كوشيه 300 جرام)
        cover_paper = PaperSpecification.objects.create(
            order=order,
            paper_type_name="كوشيه فاخر",
            paper_weight=300,
            paper_size_name="70x100",
            sheet_width=Decimal('70.0'),
            sheet_height=Decimal('100.0'),
            sheets_needed=250,
            montage_count=4,
            sheet_cost=Decimal('4.50'),
            total_paper_cost=Decimal('1125.00')
        )
        
        # جزء 2: ورق الداخلي (كوشيه 135 جرام)
        inner_paper = PaperSpecification.objects.create(
            order=order,
            paper_type_name="كوشيه مط",
            paper_weight=135,
            paper_size_name="70x100",
            sheet_width=Decimal('70.0'),
            sheet_height=Decimal('100.0'),
            sheets_needed=3000,
            montage_count=8,
            sheet_cost=Decimal('2.20'),
            total_paper_cost=Decimal('6600.00')
        )
        
        # التحقق من إمكانية ربط أجزاء متعددة لنفس الطلب
        specs = order.paper_specs.all()
        assert specs.count() == 2
        assert cover_paper in specs
        assert inner_paper in specs

    def test_03_cumulative_chain_waste_calculation(self):
        """التحقق من دقة حساب الأفرخ والهالك بالمحرك الموحد"""
        res = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'width': 21.0,
            'height': 29.7,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'waste_sheets': 50
        })
        assert res['success'] is True
        assert res['paper']['net_press_sheets'] == 250
        assert res['paper']['waste_sheets'] == 50
        assert res['paper']['gross_press_sheets'] == 300
        assert res['paper']['total_cost'] > 0

    def test_04_auto_plate_count_calculation(self):
        """التحقق من الحساب الآلي لعدد الزنكات CTP بالمحرك الموحد"""
        # وجه واحد 4 ألوان -> 4 زنكات
        res_single = PrintingCalculationEngine.calculate({
            'quantity': 1000, 'width': 21, 'height': 29.7,
            'colors_front': 4, 'colors_back': 0, 'print_sides_mode': 'single'
        })
        assert res_single['plates']['total_plates'] == 4
        
        # وجهين 4/4 طبع وقلب (Work & Turn) -> 4 زنكات (توفير 50%)
        res_wt = PrintingCalculationEngine.calculate({
            'quantity': 1000, 'width': 21, 'height': 29.7,
            'colors_front': 4, 'colors_back': 4, 'print_sides_mode': 'work_turn'
        })
        assert res_wt['plates']['total_plates'] == 4
        assert res_wt['plates']['plates_back'] == 0
        assert res_wt['plates']['is_work_turn_savings'] is True
        
        # وجهين 4/4 منفصل (Sheetwise) -> 8 زنكات
        res_sw = PrintingCalculationEngine.calculate({
            'quantity': 1000, 'width': 21, 'height': 29.7,
            'colors_front': 4, 'colors_back': 4, 'print_sides_mode': 'work_sheet'
        })
        assert res_sw['plates']['total_plates'] == 8
        assert res_sw['plates']['plates_back'] == 4
        assert res_sw['plates']['is_work_turn_savings'] is False

    def test_05_customer_info_api_endpoint(self):
        """التحقق من استجابة CustomerInfoAPIView وتصنيف العميل والذاكرة السعرية"""
        # إنشاء أوردر سابق للعميل
        PrintingOrder.objects.create(
            customer=self.customer,
            title="فلاير افتتاح سابق",
            order_type="flyer",
            quantity=2000,
            final_price=Decimal('3000.00'),
            created_by=self.user
        )
        
        url = reverse('printing_pricing:api_customer_info', kwargs={'customer_id': self.customer.id})
        response = self.client_auth.get(url)
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert data['category'] == 'corporate'
        assert data['default_profit_margin'] == 25.0
        assert data['credit_limit'] == 50000.0
        assert len(data['price_memory']) >= 1
        assert data['price_memory'][0]['title'] == "فلاير افتتاح سابق"

    def test_06_sales_commission_on_net_margin_guard(self):
        """التحقق من حساب الأرباح وهوامش البيع بالمحرك الموحد"""
        res_profit = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'width': 21.0,
            'height': 29.7,
            'profit_margin': 20.0
        })
        assert res_profit['success'] is True
        assert res_profit['totals']['profit_amount'] > 0
        assert res_profit['totals']['total_selling_price'] > res_profit['totals']['total_production_cost']

    def test_07_order_cloning_and_duplication(self):
        """التحقق من تكرار الطلب ونسخ أجزاء الورق والطباعة وتوليد كود PR- جديد"""
        original = PrintingOrder.objects.create(
            customer=self.customer,
            title="طلب أصلي للنسخ",
            order_type="box",
            quantity=3000,
            design_service_type="NEW_CONCEPT",
            design_fee=Decimal('800.00'),
            created_by=self.user
        )
        PaperSpecification.objects.create(
            order=original,
            paper_type_name="دوبلكس كرافت",
            paper_weight=350,
            paper_size_name="70x100",
            sheet_width=Decimal('70.0'),
            sheet_height=Decimal('100.0'),
            sheets_needed=750,
            sheet_cost=Decimal('5.00'),
            total_paper_cost=Decimal('3750.00')
        )
        
        url = reverse('printing_pricing:duplicate_order', kwargs={'pk': original.pk})
        response = self.client_auth.post(url)
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        new_order = PrintingOrder.objects.get(pk=data['new_order_id'])
        
        # التحقق من خصائص النسخة الجديدة
        assert new_order.order_number != original.order_number
        assert new_order.order_number.startswith("PR")
        assert new_order.status == PricingStatus.DRAFT
        assert new_order.design_service_type == "NEW_CONCEPT"
        assert new_order.design_fee == Decimal('800.00')
        # التحقق من استنساخ أجزاء الورق
        assert new_order.paper_specs.count() == 1
        assert new_order.paper_specs.first().paper_type_name == "دوبلكس كرافت"

    def test_08_pricing_filters_status_badge(self):
        """التحقق من عرض شارة الحالات approved بالأخضر و rejected بالأحمر بالعربية"""
        html_approved = status_badge('approved')
        assert 'bg-success' in html_approved
        assert 'معتمد' in html_approved
        
        html_rejected = status_badge('rejected')
        assert 'bg-danger' in html_rejected
        assert 'مرفوض' in html_rejected

    def test_09_calculate_order_cost_endpoint(self):
        """التحقق من عمل نقطة نهاية calculate_order_cost بنجاح بعد إصلاح BaseCalculator الميت"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title="طلب حساب تكلفة ذري",
            order_type="flyer",
            quantity=1000,
            width=Decimal('21.00'),
            height=Decimal('29.70'),
            created_by=self.user
        )
        url = reverse('printing_pricing:calculate_cost', kwargs={'pk': order.pk})
        response = self.client_auth.post(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'estimated_cost' in data
        assert 'final_price' in data
        assert data['order_id'] == order.id

    def test_10_manual_customer_and_approved_orders_api(self):
        """التحقق من إنشاء طلب باسم عميل يدوي دون اختيار عميل مسجل وعمل API الطلبات المعتمدة للمبيعات"""
        order_manual = PrintingOrder.objects.create(
            customer=None,
            customer_name="عميل تسعير نقدي سريع بالهاتف",
            title="فلاير تسعير سريع",
            order_type="flyer",
            quantity=2000,
            final_price=Decimal('5000.00'),
            status="approved",
            created_by=self.user
        )
        assert order_manual.customer is None
        assert order_manual.customer_name == "عميل تسعير نقدي سريع بالهاتف"
        assert order_manual.customer_display_name == "عميل تسعير نقدي سريع بالهاتف"

        # اختبار استدعاء API الطلبات المعتمدة
        url = reverse('printing_pricing:api_approved_orders')
        response = self.client_auth.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert any(o['id'] == order_manual.id for o in data['orders'])
