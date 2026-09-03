import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from printing_pricing.models import PaperType, PaperWeight
from printing_pricing.forms.settings_forms import PaperTypeForm, PaperWeightForm


@pytest.mark.django_db
class TestPaperPackCapacities:
    """اختبارات الوحدة والتكامل لسعات رزم الورق المركزية ونظام المصفوفة المزدوجة"""

    def test_paper_weight_pack_capacity_default_and_custom(self):
        """التحقق من سعة الرزمة القياسية في نموذج أوزان الورق"""
        pw_default = PaperWeight.objects.create(name="وزن اختبار 1", gsm=120)
        assert pw_default.sheets_per_pack == 250

        pw_custom = PaperWeight.objects.create(name="وزن اختبار 2", gsm=350, sheets_per_pack=125)
        assert pw_custom.sheets_per_pack == 125

    def test_paper_type_override_pack_capacity(self):
        """التحقق من سعة الرزمة الاستثنائية في نموذج أنواع الورق (مثل الدوبلكس)"""
        pt_couche = PaperType.objects.create(name="كوشيه اختبار")
        assert pt_couche.override_sheets_per_pack is None

        pt_duplex = PaperType.objects.create(name="دوبلكس اختبار", override_sheets_per_pack=100)
        assert pt_duplex.override_sheets_per_pack == 100

    def test_paper_weight_form_validation(self):
        """التحقق من صحة نموذج PaperWeightForm"""
        form_data = {
            'name': 'وزن تجريبي',
            'gsm': 200,
            'sheets_per_pack': 250,
            'is_active': True,
        }
        form = PaperWeightForm(data=form_data)
        assert form.is_valid(), form.errors
        obj = form.save()
        assert obj.sheets_per_pack == 250

    def test_paper_type_form_validation(self):
        """التحقق من صحة نموذج PaperTypeForm"""
        form_data = {
            'name': 'خامة كرتون تجريبية',
            'override_sheets_per_pack': 100,
            'is_active': True,
        }
        form = PaperTypeForm(data=form_data)
        assert form.is_valid(), form.errors
        obj = form.save()
        assert obj.override_sheets_per_pack == 100
