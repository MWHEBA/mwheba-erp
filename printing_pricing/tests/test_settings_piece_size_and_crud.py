import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from printing_pricing.models import PaperSize, PieceSize, OffsetMachineType, OffsetSheetSize, PlateSize
from printing_pricing.forms.settings_forms import PieceSizeForm, PlateSizeForm, OffsetSheetSizeForm

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
