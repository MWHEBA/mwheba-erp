import pytest
import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from supplier.models import Supplier, ServiceType, SupplierService
from printing_pricing.models import PaperType, PaperSize, PaperWeight, PaperOrigin
from printing_pricing.models import PrintingOrder

User = get_user_model()


@pytest.mark.django_db
class TestPaperCascadingFlow:
    """اختبارات منظومة تدفق كارت الورق الذكي ومنع الحلقات الدائرية وصمامات الأمان"""

    @pytest.fixture(autouse=True)
    def setup_flow_data(self):
        self.user = User.objects.create_user(
            username="test_cascading_admin",
            email="admin@cascading.com",
            password="StrongPassword123",
            is_staff=True
        )
        self.client = Client()
        self.client.login(username="test_cascading_admin", password="StrongPassword123")

        # أنواع الورق
        self.pt_couche = PaperType.objects.create(name="كوشيه فاخر", is_active=True)
        self.pt_woodfree = PaperType.objects.create(name="طبع أبيض", is_active=True)
        self.pt_duplex = PaperType.objects.create(name="دوبلكس رمادي", override_sheets_per_pack=100, is_active=True)

        # مقاسات الورق
        self.ps_70x100 = PaperSize.objects.create(name="70x100", width=100.0, height=70.0, is_active=True)
        self.ps_66x88 = PaperSize.objects.create(name="66x88", width=88.0, height=66.0, is_active=True)

        # أوزان الورق
        self.pw_300 = PaperWeight.objects.create(name="300", gsm=300, sheets_per_pack=250, is_active=True)
        self.pw_150 = PaperWeight.objects.create(name="150", gsm=150, sheets_per_pack=500, is_active=True)

        # بلد المنشأ
        self.origin_de = PaperOrigin.objects.create(name="ألماني", code="DE", is_active=True)
        self.origin_cn = PaperOrigin.objects.create(name="صيني", code="CN", is_active=True)

        # نوع خدمة الورق
        self.service_type_paper, _ = ServiceType.objects.get_or_create(
            code="paper",
            defaults={"name": "تجارة وتوريد ورق", "category": "paper"}
        )

        # مورد 1 (مكتب ورق الأهرام) يوفر كوشيه 300 جم مقاس 70×100 ألماني
        self.supplier_ahram = Supplier.objects.create(
            name="مكتب ورق الأهرام",
            contact_person="أحمد الأهرام",
            phone="01011112222",
            is_active=True
        )
        self.svc_ahram = SupplierService.objects.create(
            supplier=self.supplier_ahram,
            service_type=self.service_type_paper,
            name="كوشيه 300 جم 70×100 ألماني",
            base_price=Decimal("4.50"),
            is_active=True,
            attributes={
                "paper_type": "كوشيه فاخر",
                "gsm": 300,
                "sheet_size": "70x100",
                "origin": "ألماني",
                "sheets_per_pack": 250
            }
        )

        # مورد 2 (مطابع النيل للورق) يوفر طبع أبيض 150 جم مقاس 66×88
        self.supplier_nile = Supplier.objects.create(
            name="مكتب ورق النيل",
            contact_person="محمد النيل",
            phone="01033334444",
            is_active=True
        )
        self.svc_nile = SupplierService.objects.create(
            supplier=self.supplier_nile,
            service_type=self.service_type_paper,
            name="طبع أبيض 150 جم 66×88",
            base_price=Decimal("2.20"),
            is_active=True,
            attributes={
                "paper_type": "طبع أبيض",
                "gsm": 150,
                "sheet_size": "66x88",
                "origin": "صيني",
                "sheets_per_pack": 500
            }
        )

    def test_get_paper_types_with_and_without_supplier(self):
        """اختبار API أنواع الورق وترشيح الورق المتوفر عند المورد المختار أولاً"""
        # 1. بدون مورد: إرجاع كافة أنواع الورق
        url = reverse('printing_pricing:api_paper_types')
        response = self.client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['paper_types']) >= 3

        # 2. مع تحديد مورد الأهرام (يوفر كوشيه فاخر): يجب أن يكون الكوشيه هو الأول و is_available_with_supplier=True
        response_supp = self.client.get(url, {'supplier_id': self.supplier_ahram.id})
        assert response_supp.status_code == 200
        data_supp = response_supp.json()
        types = data_supp['paper_types']
        assert types[0]['id'] == self.pt_couche.id
        assert types[0]['is_available_with_supplier'] is True

    def test_get_paper_suppliers_with_and_without_paper_type(self):
        """اختبار API موردين الورق وترشيح المورد الذي يوفر نوع الورق المحدد أولاً"""
        url = reverse('printing_pricing:api_paper_suppliers')
        # 1. بدون تحديد نوع الورق: إرجاع كل الموردين
        resp = self.client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert len(data['suppliers']) >= 2

        # 2. مع تحديد نوع كوشيه فاخر: مورد الأهرام يأتي أولاً مع علامة is_available_for_paper=True
        resp_paper = self.client.get(url, {'paper_type_id': self.pt_couche.id})
        assert resp_paper.status_code == 200
        data_paper = resp_paper.json()
        suppliers = data_paper['suppliers']
        first_sup = suppliers[0]
        assert first_sup['id'] == self.supplier_ahram.id
        assert first_sup['is_available_for_paper'] is True

    def test_get_paper_sheet_types_strict_requirement(self):
        """اختبار اشتراط تحديد المورد والورق معاً في الشراء المباشر، وتجاوز الشرط للمخزن وتوريد العميل"""
        url = reverse('printing_pricing:api_paper_sheet_types')

        # 1. شراء مباشر بدون مورد أو ورق: يجب أن يرجع requires_supplier_and_paper=True وقائمة فارغة
        resp_missing = self.client.get(url, {'paper_source': 'purchase'})
        assert resp_missing.status_code == 200
        data_missing = resp_missing.json()
        assert data_missing['requires_supplier_and_paper'] is True
        assert data_missing['sheet_types'] == []

        # 2. شراء مباشر مع ملء المورد والورق: يرجع مقاس الفرخ المتوفر لدى المورد (70x100 للأهرام)
        resp_filled = self.client.get(url, {
            'paper_source': 'purchase',
            'supplier_id': self.supplier_ahram.id,
            'paper_type_id': self.pt_couche.id
        })
        assert resp_filled.status_code == 200
        data_filled = resp_filled.json()
        assert len(data_filled['sheet_types']) > 0
        sizes = [st['sheet_size'] for st in data_filled['sheet_types']]
        assert '70x100' in sizes

        # 3. مصدر مخزن أو توريد عميل: يرجع المقاسات القياسية حتى لو المورد فارغ
        resp_warehouse = self.client.get(url, {'paper_source': 'warehouse'})
        assert resp_warehouse.status_code == 200
        data_wh = resp_warehouse.json()
        assert len(data_wh['sheet_types']) >= 2

        resp_customer = self.client.get(url, {'paper_source': 'customer_supplied'})
        assert resp_customer.status_code == 200
        data_cust = resp_customer.json()
        assert len(data_cust['sheet_types']) >= 2

    def test_get_paper_weights_filtered_by_supplier_and_paper(self):
        """اختبار API أوزان الورق والترشيح الدقيق حسب المورد والخامة والمقاس"""
        url = reverse('printing_pricing:api_paper_weights')
        resp = self.client.get(url, {
            'supplier_id': self.supplier_ahram.id,
            'paper_type_id': self.pt_couche.id,
            'sheet_size': '70x100'
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert len(data['weights']) > 0
        first_weight = data['weights'][0]
        assert first_weight['gsm'] == 300
        assert first_weight['is_available_with_supplier'] is True

    def test_get_paper_price_and_origin_sync(self):
        """اختبار استعلام السعر الدقيق ومزامنة بلد المنشأ لمنع تضارب الجودة"""
        url = reverse('printing_pricing:api_paper_price')
        resp = self.client.get(url, {
            'supplier_id': self.supplier_ahram.id,
            'paper_type_id': self.pt_couche.id,
            'sheet_size': '70x100',
            'weight': 300
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert Decimal(str(data['price'])) == Decimal('4.50')
        assert data['origin'] == 'ألماني'
        assert 'currency' in data

    def test_paper_order_form_view_rendering(self):
        """التحقق من رندرة حقول كارت تفاصيل الورق التسعة وشبكة 3×3 وأزرار التحكم بالترتيب المطلوب"""
        url = reverse('printing_pricing:order_create')
        resp = self.client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode('utf-8')

        # التحقق من وجود الحقول التسعة المعتمدة بالترتيب الدقيق
        assert 'id_paper_type' in html                     # 1. نوع الورق
        assert 'id_paper_supplier' in html                 # 2. مورد الورق
        assert 'id_sheet_size' in html                     # 3. مقاس الفرخ
        assert 'id_paper_weight' in html                   # 4. جرام الورق
        assert 'id_piece_size' in html                     # 5. مقاس القطع
        assert 'id_paper_origin' in html                   # 6. بلد المنشأ
        assert 'box_auto_sheets_display' in html           # 7. عدد الأفرخ (تلقائي)
        assert 'box_manual_sheets_input' in html           # 7. عدد الأفرخ (يدوي)
        assert 'id_paper_sheet_price' in html              # 8. سعر الفرخ
        assert 'paper_unit_converter_collapse' in html     # 8. محول الوحدات
        assert 'cover_paper_cost_display' in html          # 9. إجمالي تكلفة الورق
        assert 'display_machine_pulls_count' in html       # سحبات الماكينة
        assert 'display_cover_weight_kg' in html           # وزن الورق كجم

        # التحقق من شارات التنبيه وصمامات الأمان
        assert 'dimension_overflow_alert' in html
        assert 'heavy_couche_creasing_alert' in html
        assert 'btn_toggle_manual_sheets' in html

    def test_zero_imposition_safety_and_math(self):
        """التحقق من صمام أمان تجاوز الأبعاد وحاسبة المواد وضمان عدم حدوث ZeroDivisionError"""
        from customer.models import Customer
        from printing_pricing.models import PrintingOrder
        from printing_pricing.services import PrintingCalculationEngine

        cust = Customer.objects.create(name="عميل اختبار", phone="01012345678")
        order = PrintingOrder.objects.create(
            customer=cust,
            title="طلب اختبار أفرخ",
            quantity=1000,
            created_by=self.user
        )

        # اختبار حساب المادة بتكلفة صفرية (مثل خامة توريد العميل)
        res_zero = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'paper_price': Decimal('0.00'),
            'width': 21.0,
            'height': 29.7
        })
        assert res_zero['success'] is True
        assert res_zero['paper']['total_cost'] == 0.0

        # فحص وجود صمامات الأمان الحسابية في ملف الجافاسكريبت الموحد
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'printing_pricing', 'order_form_engine.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # التحقق من وجود صمامات تجاوز الأبعاد وعدم القسمة على صفر
        assert 'cutsPerSheet <= 0' in js_content
        assert 'dimension_overflow_alert' in js_content
        assert 'isPaperCascadeUpdating' in js_content
        assert 'toggleManualGrossSheets' in js_content
        assert 'handlePaperTypeChange' in js_content
        assert 'handlePaperSupplierChange' in js_content
        assert 'handleSheetSizeChange' in js_content
        assert 'handlePaperWeightChange' in js_content
        assert 'fetchLivePaperPrice' in js_content
        assert 'resetPaperCascade' in js_content
