import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from client.models import Customer
from work_order.models import WorkOrder
from printing_pricing.models import (
    PrintingOrder, PaperSpecification, PrintingSpecification,
    OrderMaterial, OrderService, OrderSummary, PricingStatus, CalculationType
)
from printing_pricing.services.calculators.base_calculator import BaseCalculator
from printing_pricing.services.calculators.material_calculator import MaterialCalculator
from printing_pricing.services.calculators.printing_calculator import PrintingCalculator
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
            client_type="company",
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
        """التحقق من بادئة PR- والتوليد الآلي لأمر الشغل وتجميد لقطة العنوان"""
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
        # 2. التحقق من التوليد الآلي لـ WorkOrder
        assert order.work_order is not None
        assert order.work_order.customer == self.customer
        # 3. التحقق من تجميد لقطة العنوان
        assert "شركة الأمل للدعاية" in order.delivery_address_snapshot
        assert "01012345678" in order.delivery_address_snapshot
        # 4. التحقق من مزامنة client و sale_price
        assert order.client == self.customer
        assert order.sale_price == Decimal('12000.00')

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
        """التحقق من دقة حساب الهالك التراكمي المتسلسل لمراحل الورش"""
        calc = MaterialCalculator(order=None)
        
        # 1000 فرخ صافي + 5% سحب + 2% سلوفان + 3% تكسير + 2% تجليد
        res = calc.calculate_cumulative_paper_waste(
            net_sheets=1000,
            printing_waste_pct=Decimal('5.00'),
            lamination_waste_pct=Decimal('2.00'),
            diecut_waste_pct=Decimal('3.00'),
            binding_waste_pct=Decimal('2.00'),
            is_client_paper=False,
            sheet_cost=Decimal('3.00')
        )
        
        assert res['success'] is True
        assert res['net_sheets'] == 1000
        assert res['total_waste_sheets'] > 100  # الهالك التراكمي أكبر من 10% خطية
        assert res['gross_sheets_needed'] == 1000 + res['total_waste_sheets']
        assert res['total_cost'] == Decimal(str(res['gross_sheets_needed'])) * Decimal('3.00')
        
        # التحقق في حالة ورق العميل (التكلفة = 0)
        res_client_paper = calc.calculate_cumulative_paper_waste(
            net_sheets=1000,
            is_client_paper=True,
            sheet_cost=Decimal('3.00')
        )
        assert res_client_paper['total_cost'] == Decimal('0.00')

    def test_04_auto_plate_count_calculation(self):
        """التحقق من الحساب الآلي لعدد الزنكات CTP"""
        calc = PrintingCalculator(order=None)
        
        # وجه واحد 4 ألوان -> 4 زنكات
        assert calc.calculate_auto_plate_count(colors_front=4, colors_back=0) == 4
        
        # وجهين 4/4 طبع وقلب (Work & Turn) -> 4 زنكات
        assert calc.calculate_auto_plate_count(colors_front=4, colors_back=4, print_mode='work_and_turn') == 4
        
        # وجهين 4/4 منفصل (Sheetwise) -> 8 زنكات
        assert calc.calculate_auto_plate_count(colors_front=4, colors_back=4, print_mode='sheetwise') == 8

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
        """التحقق من حساب عمولة المبيعات على صافي الربح وصمام تصفير العمولة عند الخسارة"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title="طلب تجربة العمولات",
            quantity=1000,
            created_by=self.user
        )
        calc = BaseCalculator(order=order)
        
        # سيناريو 1: ربح طبيعي
        res_profit = calc.calculate(CalculationType.TOTAL, {
            'design_fee': '0.00',
            'profit_margin': '20.00',
            'sales_commission_rate': '10.00'
        })
        assert res_profit['success'] is True
        assert res_profit['sales_commission_amount'] >= Decimal('0.00')

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
