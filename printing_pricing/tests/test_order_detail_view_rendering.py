"""
اختبارات التحقق من رندرة قالب order_detail.html ومطابقته لمعايير التصميم الموحد لنظام MWHEBA ERP
Order Detail Template Rendering & Unified Design Standards Tests
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from customer.models import Customer
from printing_pricing.models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary,
    PaperSpecification, ProductType, ProductSize
)

User = get_user_model()


@pytest.mark.django_db
class TestOrderDetailViewRendering:
    """اختبارات مطابقة صفحة تفاصيل الطلب للتصميم الموحد للنظام"""

    def setup_method(self):
        self.user = User.objects.create_superuser(
            username='admin_detail_user',
            email='admin_detail@mwheba.com',
            password='password123'
        )
        self.customer = Customer.objects.create(
            name='مؤسسة الأهرام للطباعة',
            phone='01099887766'
        )
        self.product_type = ProductType.objects.create(
            name='فلاير دعائي',
            base_archetype='flyer'
        )
        self.product_size = ProductSize.objects.create(
            name='A4',
            width=Decimal('21.0'),
            height=Decimal('29.7')
        )
        self.order = PrintingOrder.objects.create(
            order_number='PR-2026-0002',
            customer=self.customer,
            title='طباعة مجلة ربع سنوية',
            order_type='catalog',
            product_type=self.product_type,
            product_size=self.product_size,
            quantity=500,
            pages_count=16,
            copies_count=1,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            cover_printing_type='offset',
            estimated_cost=Decimal('1500.00'),
            final_price=Decimal('2250.00'),
            profit_margin=Decimal('33.33'),
            created_by=self.user
        )
        # إنشاء مواصفة ورق
        PaperSpecification.objects.create(
            order=self.order,
            paper_type_name='كوشيه مطبوع',
            paper_weight=300,
            paper_size_name='70×100',
            sheet_width=Decimal('70.0'),
            sheet_height=Decimal('100.0'),
            sheets_needed=250,
            montage_count=4,
            sheet_cost=Decimal('3.50'),
            total_paper_cost=Decimal('875.00')
        )
        # إنشاء مادة تموينية مع نسبة هالك
        self.paper_mat = OrderMaterial.objects.create(
            order=self.order,
            material_type='paper',
            material_name='كوشيه 300 جرام مقاس 70×100',
            quantity=Decimal('250.00'),
            unit='sheet',
            unit_cost=Decimal('3.50'),
            total_cost=Decimal('875.00'),
            waste_percentage=Decimal('5.00'),
            supplier_info={'waste_sheets': 12}
        )
        # إنشاء خدمة ورشة
        OrderService.objects.create(
            order=self.order,
            service_category='printing',
            service_name='طباعة أوفست 4 ألوان',
            quantity=Decimal('1000.00'),
            unit='click',
            unit_price=Decimal('0.50'),
            setup_cost=Decimal('100.00'),
            total_cost=Decimal('600.00')
        )
        # إنشاء ملخص التكلفة الموحد
        OrderSummary.objects.create(
            order=self.order,
            material_cost=Decimal('875.00'),
            printing_cost=Decimal('600.00'),
            finishing_cost=Decimal('100.00'),
            total_cost=Decimal('1575.00'),
            profit_amount=Decimal('675.00'),
            profit_margin_percentage=Decimal('30.00'),
            subtotal=Decimal('2250.00'),
            final_price=Decimal('2250.00')
        )

    def test_order_detail_view_renders_successfully(self, client):
        """التحقق من فتح صفحة تفاصيل الطلب بنجاح ومطابقتها للمكونات القياسية"""
        client.force_login(self.user)
        url = reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')

        # 1. التحقق من رأس الصفحة الموحد ومسار التنقل
        assert 'page-header' in content
        assert 'breadcrumb' in content
        assert 'PR-2026-0002' in content
        assert 'طباعة مجلة ربع سنوية' in content

        # 2. التحقق من وجود كروت المؤشرات السريعة الموحدة stats-card
        assert 'stats-card' in content
        assert 'stats-card-primary' in content
        assert 'stats-card-danger' in content
        assert 'stats-card-success' in content
        assert 'stats-card-info' in content
        assert 'قيمة البيع للعميل' in content

        # 3. التحقق من الأقسام الموحدة section-container & section-title
        assert 'section-container' in content
        assert 'section-title' in content
        assert 'البيانات الأساسية وتفاصيل العميل والطلب' in content
        assert 'بطاقة المواصفات الفنية والهندسة الهجينة' in content
        assert 'خامات وأوراق الطباعة' in content
        assert 'خدمات وعمليات الورش والمطابع ومقاولي الباطن' in content
        assert 'مركز أرباح الشغلانة والتوزيع المالي' in content

        # 4. التحقق من ظهور بيانات العميل والمواد والخدمات
        assert 'مؤسسة الأهرام للطباعة' in content
        assert 'كوشيه 300 جرام' in content
        assert 'طباعة أوفست 4 ألوان' in content
        assert 'سعر الوحدة' in content

        # 5. التحقق من وجود أزرار التحكم القياسية ودوال الجافاسكريبت
        assert 'recalculateOrderCost' in content
        assert 'approveOrder' in content
        assert 'btn_convert_work_order' in content

        # 6. التحقق من شارات الهيدر (رقم التسعير في تاج كالموردين، وأيقونة المسودة)
        header_badges = response.context['header_badges']
        assert any(b.get('text') == 'PR-2026-0002' and b.get('class') == 'bg-primary' and b.get('icon') == 'fas fa-hashtag' for b in header_badges)
        assert any(b.get('text') == 'مسودة' and b.get('icon') == 'fas fa-pencil-alt' for b in header_badges)

        # 7. التحقق من ظهور نسبة الهالك وعدد أفرخ الهالك المحسوبة
        assert '5%' in content
        assert f"12 {self.paper_mat.clean_unit_name}" in content

