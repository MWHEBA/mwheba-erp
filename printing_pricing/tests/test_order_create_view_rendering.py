"""
اختبارات التحقق من رندرة قالب order_form.html وشاشات الإنشاء والتعديل بدون أخطاء
Order Form Template Rendering & Syntax Tests
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from customer.models import Customer
from printing_pricing.models import PrintingOrder

User = get_user_model()


@pytest.mark.django_db
class TestOrderFormRendering:
    """اختبارات رندرة شاشة تسعير المطبوعات"""

    def setup_method(self):
        self.user = User.objects.create_superuser(
            username='admin_user',
            email='admin@mwheba.com',
            password='password123'
        )
        self.customer = Customer.objects.create(
            name='شركة النجاح',
            phone='01012345678'
        )

    def test_order_create_view_renders_successfully(self, client):
        """التحقق من فتح شاشة إنشاء طلب تسعير جديد بدون أي خطأ في القوالب وبوجود عناصر البوابات"""
        client.force_login(self.user)
        url = reverse('printing_pricing:order_create')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'card_step1_scope' in content
        assert 'id_design_service_type' in content
        assert 'montage_waiting_overlay' in content
        assert 'card_step2_cover' in content
        assert 'card_step3_inner' in content
        assert 'summary_main_card' in content
        # التحقق من عناصر معمارية البوابة المزدوجة
        assert 'step1_status_badge' in content
        assert 'btn_quick_quote_fill' in content
        assert 'btn_proceed_to_step2' in content
        assert 'step2_technical_gate_notice' in content
        assert 'sidebar_commit_gate_alert' in content

    def test_order_update_view_renders_successfully(self, client):
        """التحقق من فتح شاشة تعديل طلب تسعير قائم بدون أي خطأ في القوالب"""
        client.force_login(self.user)
        order = PrintingOrder.objects.create(
            order_number='ORD-TEST-999',
            customer=self.customer,
            title='طباعة بروشور دعائي',
            order_type='flyer',
            quantity=1000,
            created_by=self.user
        )
        url = reverse('printing_pricing:order_update', kwargs={'pk': order.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert 'ORD-TEST-999' in response.content.decode('utf-8')

    def test_order_update_view_with_paper_specs_and_services(self, client):
        """التحقق من فتح شاشة التعديل لطلب لديه مواصفات ورق وبنود خامات وخدمات دون أي AttributeError"""
        from printing_pricing.models import PaperSpecification, OrderMaterial, OrderService, PaperType
        client.force_login(self.user)
        pt = PaperType.objects.create(name='كوشيه فاخر')
        order = PrintingOrder.objects.create(
            order_number='ORD-TEST-SPECS-1',
            customer=self.customer,
            title='طباعة كتالوج 32 صفحة',
            order_type='catalog',
            quantity=500,
            created_by=self.user
        )
        PaperSpecification.objects.create(
            order=order,
            paper_type_name='كوشيه فاخر',
            paper_weight=150,
            paper_size_name='70x100',
            sheet_width=Decimal('70.0'),
            sheet_height=Decimal('100.0'),
            sheets_needed=200,
            sheet_cost=Decimal('4.00'),
            total_paper_cost=Decimal('800.00')
        )
        OrderMaterial.objects.create(
            order=order,
            material_type='paper',
            material_name='كوشيه فاخر',
            quantity=Decimal('200.00'),
            unit='sheet',
            unit_cost=Decimal('4.00'),
            total_cost=Decimal('800.00'),
            supplier_info={'supplier_id': 1, 'paper_type_id': pt.id}
        )
        OrderService.objects.create(
            order=order,
            service_category='coating',
            service_name='سلوفان مط وجهين',
            quantity=Decimal('500.00'),
            unit='sheet',
            unit_price=Decimal('1.20'),
            total_cost=Decimal('600.00')
        )
        url = reverse('printing_pricing:order_update', kwargs={'pk': order.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'ORD-TEST-SPECS-1' in content

    def test_order_update_restores_all_saved_data_and_prices(self, client):
        """التحقق من استرجاع 100% من المواصفات والأسعار والتكاليف المحفوظة في شاشة التعديل"""
        from printing_pricing.models import PaperSpecification, OrderMaterial, OrderService, PaperType, PaperSize, PieceSize
        from supplier.models import Supplier

        client.force_login(self.user)
        pt = PaperType.objects.create(name='كوشيه فاخر')
        sheet_size = PaperSize.objects.create(name='فرخ كامل 70×100', width=Decimal('70.0'), height=Decimal('100.0'))
        piece_size = PieceSize.objects.create(name='نصف فرخ', paper_type=sheet_size, pieces_per_sheet=2, width=Decimal('50.0'), height=Decimal('70.0'))
        ctp_supp = Supplier.objects.create(name='مكتب فصل الإيمان')
        offset_supp = Supplier.objects.create(name='مطبعة الأهرام')

        order = PrintingOrder.objects.create(
            order_number='ORD-EDIT-100',
            customer=self.customer,
            title='فلاير دعائي مقاس A4',
            order_type='flyer',
            quantity=10000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            profit_margin=Decimal('30.0'),
            final_price=Decimal('12474.00'),
            created_by=self.user
        )

        PaperSpecification.objects.create(
            order=order,
            paper_type_name='كوشيه فاخر',
            paper_weight=300,
            paper_size_name='فرخ كامل 70×100',
            sheet_width=Decimal('70.0'),
            sheet_height=Decimal('100.0'),
            piece_size=piece_size,
            montage_count=4,
            sheets_needed=2520,
            sheet_cost=Decimal('3.50'),
            total_paper_cost=Decimal('8820.00')
        )

        OrderMaterial.objects.create(
            order=order,
            material_type='paper',
            material_name='كوشيه فاخر',
            quantity=Decimal('2520.00'),
            unit='sheet',
            unit_cost=Decimal('3.50'),
            total_cost=Decimal('8820.00'),
            supplier_info={'waste_sheets': 20, 'paper_type_id': pt.id}
        )

        OrderService.objects.create(
            order=order,
            service_category='finishing',
            service_name='زنكات CTP أوفست 4 لون',
            quantity=Decimal('4.00'),
            unit='plate',
            unit_price=Decimal('160.00'),
            total_cost=Decimal('640.00'),
            supplier_info={'supplier_id': ctp_supp.id, 'press_bed_size': '70x100', 'plate_price': '160.00'}
        )

        OrderService.objects.create(
            order=order,
            service_category='printing',
            service_name='طباعة أوفست 4 لون وجه واحد',
            quantity=Decimal('5000.00'),
            unit='thousand_pulls',
            unit_price=Decimal('45.00'),
            total_cost=Decimal('775.00'),
            supplier_info={'supplier_id': offset_supp.id, 'press_rate': '45.00', 'machine_name': 'هايدلبرج سبيد ماستر 70×100'}
        )

        from printing_pricing.models import OrderSummary
        OrderSummary.objects.create(
            order=order,
            material_cost=Decimal('8820.00'),
            printing_cost=Decimal('775.00'),
            finishing_cost=Decimal('0.00'),
            total_cost=Decimal('9595.00'),
            final_price=Decimal('12474.00'),
            profit_amount=Decimal('2879.00')
        )

        url = reverse('printing_pricing:order_update', kwargs={'pk': order.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')

        # 1. التحقق من استرجاع أسعار الخدمات والأوراق في حقول الإدخال
        assert 'value="45.00"' in content or 'value="45"' in content  # press_rate
        assert 'value="160.00"' in content or 'value="160"' in content  # plate_price
        assert 'value="3.50"' in content or 'value="3.5"' in content  # paper_sheet_price

        # 2. التحقق من مقاس الفرخ ومقاس القطع والمونتاج والهالك
        assert f'value="{sheet_size.name}"' in content
        assert f'value="{piece_size.id}"' in content
        assert 'value="4"' in content  # montage_count
        assert 'value="20"' in content  # waste_sheets

        # 3. التحقق من تفاصيل التكاليف والأرقام في ملخص الحسبة
        assert '8820' in content  # material_cost
        assert '775' in content   # printing_cost
        assert '9595' in content or '9,595' in content  # total_cost
        assert '12474' in content or '12,474' in content  # final_total_display



    def test_plate_size_list_view_renders_successfully(self, client):
        """التحقق من فتح شاشة مقاسات زنكات CTP بدون أي خطأ في القوالب"""
        client.force_login(self.user)
        url = reverse('printing_pricing:plate_size_list')
        response = client.get(url)
        assert response.status_code == 200
        assert 'مقاسات زنكات CTP' in response.content.decode('utf-8')

    def test_pricing_order_form_requires_customer_and_title(self):
        """التحقق من رفض النموذج عند غياب العميل أو وصف الطلب"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'quantity': 1000,
            'order_type': 'flyer',
            'width': 21.0,
            'height': 29.7,
        })
        assert not form.is_valid()
        assert 'customer_name' in form.errors
        assert 'title' in form.errors

    def test_pricing_order_form_valid_with_cash_customer_and_title(self):
        """التحقق من خلو أخطاء العميل والوصف عند ملء العميل النقدي والوصف"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'customer_name': 'عميل استفسار سريع',
            'title': 'طباعة فلاير A4',
            'quantity': 1000,
            'order_type': 'flyer',
            'width': 21.0,
            'height': 29.7,
            'order_date': '2026-09-06',
        })
        form.is_valid()
        assert 'customer_name' not in form.errors
        assert 'customer' not in form.errors
        assert 'title' not in form.errors

    def test_pricing_order_form_binding_types_support_catalog_options(self):
        """التحقق من دعم كافة خيارات التجليد (غراء، سلك، كرتون مقوى) بدون أخطاء اختيار غير متاح"""
        from printing_pricing.forms import PricingOrderForm
        for btype in ['perfect_binding', 'hardcover', 'wire_o', 'pad_glue', 'sewing_binding', 'staple']:
            form = PricingOrderForm(data={
                'customer': self.customer.pk,
                'title': f'طلب تجليد {btype}',
                'quantity': 500,
                'width': 21.0,
                'height': 29.7,
                'order_date': '2026-09-07',
                'binding_type': btype,
            })
            form.is_valid()
            assert 'binding_type' not in form.errors, f"binding_type {btype} failed: {form.errors.get('binding_type')}"

    def test_pricing_order_form_profit_margin_no_5_digits_overflow(self):
        """التحقق من قبول هامش الربح حتى 4 منازل عشرية من JS والتقريب الآمن دون تجاوز السعة الرقمية"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'customer': self.customer.pk,
            'title': 'فحص هامش الربح',
            'quantity': 500,
            'width': 21.0,
            'height': 29.7,
            'order_date': '2026-09-07',
            'profit_margin': '30.0000',
        })
        assert form.is_valid(), f"Form errors: {form.errors}"
        assert form.cleaned_data['profit_margin'] == 30.00

    def test_pricing_order_form_auto_infers_order_type_from_product_type(self):
        """التحقق من الاستنتاج الآلي لنوع الطلب من ProductType عند عدم إرسال order_type"""
        from printing_pricing.forms import PricingOrderForm
        from printing_pricing.models import ProductType
        pt, _ = ProductType.objects.get_or_create(name='كتالوج تجريبي', defaults={'base_archetype': 'catalog'})
        form = PricingOrderForm(data={
            'customer': self.customer.pk,
            'title': 'كتالوج مع داخلي',
            'product_type': pt.pk,
            'quantity': 500,
            'width': 21.0,
            'height': 29.7,
            'order_date': '2026-09-07',
            'binding_type': 'perfect_binding',
        })
        assert form.is_valid(), f"Form errors: {form.errors}"
        assert form.cleaned_data['order_type'] == 'catalog'

    def test_pricing_order_form_accepts_custom_product_size(self):
        """التحقق من قبول المقاس المخصص دون حدوث خطأ Select a valid choice"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'customer': self.customer.pk,
            'title': 'مطبوع مقاس مخصص',
            'product_size': 'custom',
            'quantity': 500,
            'width': 18.5,
            'height': 25.0,
            'order_date': '2026-09-07',
        })
        assert form.is_valid(), f"Form errors: {form.errors}"
        assert form.cleaned_data['product_size'] is None

    def test_pricing_order_form_accepts_digital_banner_printing_type(self):
        """التحقق من قبول نوع الطباعة بنر ديجيتال ومواءمته مع الموديل"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'customer': self.customer.pk,
            'title': 'طباعة بنر ديجيتال',
            'cover_printing_type': 'digital_banner',
            'quantity': 100,
            'width': 100.0,
            'height': 200.0,
            'order_date': '2026-09-07',
        })
        assert form.is_valid(), f"Form errors: {form.errors}"
        assert form.cleaned_data['cover_printing_type'] == 'digital'

    def test_pricing_order_form_accepts_dynamic_paper_fields(self):
        """التحقق من قبول المنشأ والجرام ومقاس الفرخ الديناميكي بدون تقييد اختيارات"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'customer': self.customer.pk,
            'title': 'خامة ديناميكية من المورد',
            'quantity': 500,
            'width': 21.0,
            'height': 29.7,
            'order_date': '2026-09-07',
            'paper_origin': 'منشأ خاص بالتاجر',
            'paper_weight': '350',
            'paper_sheet_type': 'فرخ 70x100 مخصص',
        })
        assert form.is_valid(), f"Form errors: {form.errors}"
        assert form.cleaned_data['paper_origin'] == 'منشأ خاص بالتاجر'
        assert form.cleaned_data['paper_weight'] == '350'

    def test_pricing_order_form_accepts_supplier_and_product_type_without_invalid_choice_error(self):
        """التحقق من قبول مورد الورق ونوع المطبوع دون إطلاق استثناء Select a valid choice"""
        from supplier.models import Supplier
        from printing_pricing.forms import PricingOrderForm
        supplier = Supplier.objects.create(name='مورد ورق الأهرام', is_active=True)
        
        form = PricingOrderForm(data={
            'customer': self.customer.pk,
            'title': 'طلب تسعير كامل مع مورد ونوع مطبوع',
            'quantity': 1000,
            'order_type': 'flyer',
            'product_type': 'flyer',
            'paper_supplier': supplier.pk,
            'order_date': '2026-09-07',
            'width': 21.0,
            'height': 29.7,
            'binding_type': 'perfect_binding',
            'cover_printing_type': 'digital_banner',
        })
        is_valid = form.is_valid()
        assert is_valid, f"Form errors: {form.errors}"
        assert 'paper_supplier' not in form.errors
        assert 'product_type' not in form.errors
        assert 'binding_type' not in form.errors
        assert form.cleaned_data['paper_supplier'] == supplier
        assert form.cleaned_data['cover_printing_type'] == 'digital'
        order = form.save()
        assert order.pk is not None

    def test_date_field_preserved_on_form_rendering_with_errors(self, client):
        """التحقق من عدم مسح حقل التاريخ عند إعادة عرض النموذج بعد فشل التحقق"""
        client.force_login(self.user)
        url = reverse('printing_pricing:order_create')
        response = client.post(url, {
            'order_date': '2026-09-07',
            'quantity': 500,
            'width': 21.0,
            'height': 29.7,
        })
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'value="2026-09-07"' in content

    def test_order_create_view_post_successful(self, client):
        """التحقق من نجاح إرسال نموذج إنشاء الطلب وتحويله بنجاح دون أي AttributeError أو خطأ في الاختيارات"""
        from supplier.models import Supplier
        supplier = Supplier.objects.create(name='مورد معتمد', is_active=True)
        client.force_login(self.user)
        url = reverse('printing_pricing:order_create')
        response = client.post(url, {
            'customer': self.customer.pk,
            'title': 'طلب تجربة كامل',
            'quantity': 1000,
            'order_type': 'flyer',
            'product_type': 'flyer',
            'paper_supplier': supplier.pk,
            'order_date': '2026-09-07',
            'width': 21.0,
            'height': 29.7,
            'profit_margin': '25.00',
        })
        assert response.status_code in [302, 200]
        if response.status_code == 302:
            assert PrintingOrder.objects.filter(title='طلب تجربة كامل').exists()




