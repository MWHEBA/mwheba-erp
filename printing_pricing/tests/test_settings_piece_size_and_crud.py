import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from printing_pricing.models import PaperSize, PieceSize, OffsetMachineType, OffsetSheetSize, DigitalSheetSize, PlateSize
from printing_pricing.forms.settings_forms import PieceSizeForm, PlateSizeForm, OffsetSheetSizeForm, DigitalSheetSizeForm

User = get_user_model()

@pytest.fixture
def staff_client(client, db):
    user = User.objects.create_user(
        username='staff_user',
        password='password123',
        is_staff=True,
        is_superuser=True
    )
    client.login(username='staff_user', password='password123')
    return client

@pytest.mark.django_db
class TestSettingsPieceSizeAndCRUD:
    """اختبارات منظومة إعدادات مقاسات القطع والمكونات المشتركة"""

    def test_paper_size_select_widget_attributes(self, db):
        """التحقق من أن الـ Widget يمرر أبعاد data-width و data-height صريحة"""
        paper_size = PaperSize.objects.create(
            name='فرخ كامل 70x100',
            width=Decimal('70.00'),
            height=Decimal('100.00'),
            is_active=True
        )
        form = PieceSizeForm()
        rendered_html = form['paper_type'].as_widget()
        assert f'data-width="70.00"' in rendered_html
        assert f'data-height="100.00"' in rendered_html

    def test_piece_size_mathematical_calculation(self, db):
        """التحقق من صحة دالة حساب عدد القطع في الموديل"""
        sheet = PaperSize.objects.create(
            name='فرخ 70x100',
            width=Decimal('70.00'),
            height=Decimal('100.00'),
            is_active=True
        )
        # قطعة A4: 21x29.7
        piece = PieceSize.objects.create(
            name='A4',
            paper_type=sheet,
            width=Decimal('21.00'),
            height=Decimal('29.70')
        )
        calculated = piece.calculate_pieces_per_sheet()
        # 70//21=3, 100//29.7=3 -> 9. Rotated: 70//29.7=2, 100//21=4 -> 8. Max=9
        assert calculated == 9

    def test_piece_size_list_view_staff(self, staff_client, db):
        """التحقق من تحميل شاشة قائمة مقاسات القطع بنجاح"""
        url = reverse('printing_pricing:piece_size_list')
        response = staff_client.get(url)
        assert response.status_code == 200
        assert 'settings_crud.js' in response.content.decode('utf-8')
        assert 'SettingsCRUD.openCreateModal' in response.content.decode('utf-8')

    def test_settings_home_structure(self, staff_client, db):
        """التحقق من تحميل الصفحة الرئيسية للإعدادات بالـ 4 بطاقات"""
        url = reverse('printing_pricing:settings_home')
        response = staff_client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'الخامات والورق الخام' in content
        assert 'الماكينات ومقاسات التشغيل' in content
        assert 'كتالوج المنتجات والمقاسات' in content
        assert 'قواميس المواصفات الفنية' in content
        # التأكد من إزالة التكرار
        assert content.count('piece-sizes/') == 1

    def test_plate_size_form_optional_machine(self, db):
        """التحقق من مرونة ربط الماكينة بالزنكة كحقل اختياري"""
        form_data = {
            'name': 'زنك قياسي 60x74',
            'width': '60.5',
            'height': '74.5',
            'is_active': True
        }
        form = PlateSizeForm(data=form_data)
        assert form.is_valid(), form.errors
        plate = form.save()
        assert plate.machine is None
        assert plate.dimension_type == 'plate'

    def test_offset_and_digital_sheet_sizes_isolation(self, db):
        """التحقق من العزل التام بين شيتات الأوفست والديجيتال في الاستعلامات"""
        offset_sheet = OffsetSheetSize.objects.create(
            name='ربع فرخ اختباري',
            code='test_quarter',
            width=Decimal('35.00'),
            height=Decimal('50.00'),
            dimension_type='offset_sheet',
            is_active=True
        )
        digital_sheet = DigitalSheetSize.objects.create(
            name='A3 ديجيتال اختباري',
            code='test_digital_a3',
            width=Decimal('29.70'),
            height=Decimal('42.00'),
            dimension_type='digital_sheet',
            is_active=True
        )

        # التحقق من أن كل مدير استعلام لا يرى سوى نوعه
        assert offset_sheet in OffsetSheetSize.objects.all()
        assert digital_sheet not in OffsetSheetSize.objects.all()

        assert digital_sheet in DigitalSheetSize.objects.all()
        assert offset_sheet not in DigitalSheetSize.objects.all()

    def test_offset_and_digital_sheet_size_list_views(self, staff_client, db):
        """التحقق من أن شاشات العرض تعرض فقط المقاسات الخاصة بكل تقنية"""
        OffsetSheetSize.objects.create(
            name='نصف فرخ أوفست',
            code='offset_50x70',
            width=Decimal('50.00'),
            height=Decimal('70.00'),
            dimension_type='offset_sheet'
        )
        DigitalSheetSize.objects.create(
            name='سوبر A3 ديجيتال',
            code='digital_33x48',
            width=Decimal('33.00'),
            height=Decimal('48.80'),
            dimension_type='digital_sheet'
        )

        # 1. شاشة الأوفست
        offset_resp = staff_client.get(reverse('printing_pricing:offset_sheet_size_list'))
        assert offset_resp.status_code == 200
        offset_items = list(offset_resp.context['sheet_sizes'])
        assert any(s.code == 'offset_50x70' for s in offset_items)
        assert not any(s.code == 'digital_33x48' for s in offset_items)

        # 2. شاشة الديجيتال
        digital_resp = staff_client.get(reverse('printing_pricing:digital_sheet_size_list'))
        assert digital_resp.status_code == 200
        digital_items = list(digital_resp.context['sheet_sizes'])
        assert any(s.code == 'digital_33x48' for s in digital_items)
        assert not any(s.code == 'offset_50x70' for s in digital_items)

    def test_sheet_size_forms_dimension_type_assignment(self, db):
        """التحقق من أن فورمات الإدخال تعين نوع المقاس dimension_type الصحيح تلقائياً"""
        # فورم الأوفست
        offset_form = OffsetSheetSizeForm(data={
            'name': 'شيت أوفست جديد',
            'width': '35.0',
            'height': '50.0',
            'is_active': True
        })
        assert offset_form.is_valid(), offset_form.errors
        offset_saved = offset_form.save()
        assert offset_saved.dimension_type == 'offset_sheet'

        # فورم الديجيتال
        digital_form = DigitalSheetSizeForm(data={
            'name': 'شيت ديجيتال جديد',
            'width': '32.9',
            'height': '48.3',
            'is_active': True
        })
        assert digital_form.is_valid(), digital_form.errors
        digital_saved = digital_form.save()
        assert digital_saved.dimension_type == 'digital_sheet'

