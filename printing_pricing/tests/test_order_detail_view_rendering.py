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
        assert 'card_detail_design_studio' in content
        assert 'خدمات التصميم والتجهيز الفني والمونتاج' in content
        assert 'البيانات الأساسية وتفاصيل العميل والطلب' in content
        assert 'الأوجه:' in content
        assert 'نوع الطباعة:' in content
        assert 'خامات الطباعة' in content
        assert 'خدمات الورش والمطابع' in content
        assert 'تحليل التكاليف وهامش الربحية' in content

        # 4. التحقق من ظهور بيانات العميل والمواد والخدمات
        assert 'مؤسسة الأهرام للطباعة' in content
        assert 'كوشيه 300 جرام' in content
        assert 'طباعة أوفست 4 ألوان' in content
        assert 'تكلفة الوحدة' in content
        assert 'إجمالي التكلفة' in content

        # 5. التحقق من وجود أزرار التحكم القياسية ودوال الجافاسكريبت
        assert 'recalculateOrderCost' in content
        assert 'approveOrder' in content
        assert 'btn_convert_work_order' in content

        # 6. التحقق من شارات الهيدر ورابط العميل الموحد
        header_badges = response.context['header_badges']
        assert any(b.get('text') == 'PR-2026-0002' and b.get('class') == 'bg-primary' and b.get('icon') == 'fas fa-hashtag' for b in header_badges)
        assert any(b.get('text') == 'مسودة' and b.get('icon') == 'fas fa-pencil-alt' for b in header_badges)
        cust_url = reverse('customer:customer_detail', kwargs={'pk': self.customer.pk})
        assert cust_url in content
        assert response.context['customer_url'] == cust_url

        # 7. التحقق من ظهور نسبة الهالك وعدد أفرخ الهالك المحسوبة
        assert '5%' in content
        assert f"12 {self.paper_mat.clean_unit_name}" in content

    def test_services_clean_naming_and_concise_technical_description(self, client):
        """التحقق من صياغة أسماء الخدمات وفقاً للمصطلحات المصرية وتجنب تكرار اسم المورد في الوصف"""
        # إضافة خدمات أوفست وزنكات بأوصاف مسجلة
        OrderService.objects.create(
            order=self.order,
            service_category='printing',
            service_name='[غلاف أوفست] تجهيز زنكات CTP جديدة (50x70) (عدد 4 زنكة)',
            quantity=Decimal('4.00'),
            unit='plate',
            unit_price=Decimal('50.00'),
            total_cost=Decimal('200.00'),
            supplier_info={
                'bed_size': '50x70',
                'is_archived': False,
                'supplier_name': 'زنكات داخلية / سعر معياري'
            }
        )
        OrderService.objects.create(
            order=self.order,
            service_category='printing',
            service_name='[غلاف أوفست] سحبات ماكينة أوفست بالتراج (1132 سحبة - 2 تراج)',
            quantity=Decimal('2.00'),
            unit='tirage',
            unit_price=Decimal('45.00'),
            total_cost=Decimal('90.00'),
            supplier_info={
                'bed_size': '50x70',
                'machine': 'هايدلبرج Speedmaster SM 74 – 4 لون (50×70)',
                'pulls_count': 1132,
                'supplier_name': 'مطبعة الأهرام'
            }
        )

        client.force_login(self.user)
        url = reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk})
        response = client.get(url)
        assert response.status_code == 200

        services = response.context['services']
        ctp_svc = next(s for s in services if 'CTP' in s.clean_service_name)
        offset_svc = next(s for s in services if 'طباعة أوفست (ماكينة نص)' in s.clean_service_name)

        # 1. التحقق من الأسماء المهنية النظيفة
        assert ctp_svc.clean_service_name == 'زنكات CTP (مقاس نص)'
        assert offset_svc.clean_service_name == 'طباعة أوفست (ماكينة نص)'

        # 2. التحقق من الوصف الفني بدون تكرار كلمة المورد أو المطبعة
        assert 'المورد:' not in ctp_svc.clean_description
        assert 'المطبعة:' not in offset_svc.clean_description
        assert 'زنكات جديدة • أبعاد 50×70 سم' in ctp_svc.clean_description
        assert '1,132 سحبة فعلية' in offset_svc.clean_description
        assert 'Speedmaster SM 74' in offset_svc.clean_description

        # 3. التحقق من تنظيف اسم المورد الفعلي
        assert ctp_svc.effective_supplier_name == 'زنكات داخلية'
        assert offset_svc.effective_supplier_name == 'مطبعة الأهرام'

        # 4. التحقق من فئة الخدمة المخصصة والأيقونة
        assert str(ctp_svc.category_display) == 'فصل زنكات'
        assert ctp_svc.category_icon == 'fas fa-layer-group'
        assert str(offset_svc.category_display) == 'طباعة أوفست'
        assert offset_svc.category_icon == 'fas fa-print'
        content = response.content.decode('utf-8')
        assert 'fa-layer-group' in content
        assert 'فصل زنكات' in content
        assert 'fa-print' in content

    def test_print_sides_and_colors_standardized_formatting(self, client):
        """التحقق من صياغة الأوجه ونمط الألوان وفقاً للمصطلحات القياسية للمطابع"""
        client.force_login(self.user)

        # 1. حالة وجه واحد عادي (4 لون) ومطبوع مفرد (إخفاء حالة الطي)
        self.order.print_sides_mode = 'single'
        self.order.spot_colors_front = 0
        self.order.spot_colors_back = 0
        self.order.is_closed_size = False
        self.order.save()
        res = client.get(reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk}))
        assert res.context['order'].clean_sides_and_colors == 'وجه واحد (4 لون)'
        assert res.context['order'].is_single_sheet is True
        assert 'حالة الطي:' not in res.content.decode('utf-8')

        # 2. حالة وجه واحد مع ألوان مخصوصة (4 لون + 2 لون مخصوص)
        self.order.spot_colors_front = 2
        self.order.save()
        res = client.get(reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk}))
        assert res.context['order'].clean_sides_and_colors == 'وجه واحد (4 لون + 2 لون مخصوص)'

        # 3. حالة متقدمة: وجهين مع اختلاف الألوان ومخصوص بالظهر (الوجه: 4 لون - الظهر: 1 لون مخصوص)
        self.order.print_sides_mode = 'work_sheet'
        self.order.spot_colors_front = 0
        self.order.spot_colors_back = 1
        self.order.save()
        # إضافة زنكة بالمعلومات الفنية
        OrderService.objects.create(
            order=self.order,
            service_category='printing',
            service_name='زنك أوفست',
            quantity=Decimal('5.00'),
            unit_price=Decimal('50.00'),
            total_cost=Decimal('250.00'),
            supplier_info={'front_plates': 4, 'back_plates': 1}
        )
        res = client.get(reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk}))
        assert res.context['order'].clean_sides_and_colors == 'وجهين (الوجه: 4 لون - الظهر: 1 لون مخصوص)'

        # 4. حالة وجهين متماثلين بدون مخصوص (4/4 لون)
        self.order.spot_colors_front = 0
        self.order.spot_colors_back = 0
        self.order.save()
        self.order.services.filter(service_name='زنك أوفست').update(
            supplier_info={'front_plates': 4, 'back_plates': 4}
        )
        res = client.get(reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk}))
        assert res.context['order'].clean_sides_and_colors == 'وجهين (4/4 لون)'

        # 5. حالة طبع وقلب بدون مخصوص (4/4 لون)
        self.order.print_sides_mode = 'work_turn'
        self.order.save()
        res = client.get(reverse('printing_pricing:order_detail', kwargs={'pk': self.order.pk}))
        assert res.context['order'].clean_sides_and_colors == 'طبع وقلب (4/4 لون)'



