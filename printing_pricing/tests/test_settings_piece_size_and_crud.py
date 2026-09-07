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

    def test_piece_size_scoped_default_behavior(self, db):
        """التحقق من أن حصرية الافتراضي محصورة فقط داخل نفس مقاس الفرخ الخام ولا تتعداه"""
        paper_70_100 = PaperSize.objects.create(name='70x100', width=Decimal('70'), height=Decimal('100'))
        paper_66_88 = PaperSize.objects.create(name='66x88', width=Decimal('66'), height=Decimal('88'))

        # إنشاء مقاسين لـ 70x100
        p1_half = PieceSize.objects.create(name='نصف فرخ', paper_type=paper_70_100, width=Decimal('50'), height=Decimal('70'), is_default=True)
        p1_quarter = PieceSize.objects.create(name='ربع فرخ', paper_type=paper_70_100, width=Decimal('35'), height=Decimal('50'), is_default=False)

        # إنشاء مقاسين لـ 66x88
        p2_half = PieceSize.objects.create(name='نصف جاير', paper_type=paper_66_88, width=Decimal('44'), height=Decimal('66'), is_default=False)
        p2_quarter = PieceSize.objects.create(name='ربع جاير', paper_type=paper_66_88, width=Decimal('33'), height=Decimal('44'), is_default=True)

        # كلا الفرخين يمتلك مقاساً افتراضياً في نفس الوقت
        p1_half.refresh_from_db()
        p2_quarter.refresh_from_db()
        assert p1_half.is_default is True
        assert p2_quarter.is_default is True

        # تبديل الافتراضي لـ 70x100 ليصبح ربع الفرخ
        p1_quarter.is_default = True
        p1_quarter.save()

        p1_half.refresh_from_db()
        p1_quarter.refresh_from_db()
        p2_quarter.refresh_from_db()

        # ربع الفرخ أصبح افتراضياً ونصف الفرخ تم إلغاؤه، بينما ربع الجاير لا يزال افتراضياً دون تأثر!
        assert p1_quarter.is_default is True
        assert p1_half.is_default is False
        assert p2_quarter.is_default is True

    def test_get_piece_sizes_api_default_ordering(self, staff_client, db):
        """التحقق من أن API مقاسات الشيت يُرجع العنصر الافتراضي في الصدارة مع خلوه من خيار auto"""
        paper = PaperSize.objects.create(name='فرخ كامل', width=Decimal('70'), height=Decimal('100'))
        PieceSize.objects.create(name='نصف فرخ', paper_type=paper, width=Decimal('50'), height=Decimal('70'), pieces_per_sheet=2, is_default=False, sort_order=10)
        PieceSize.objects.create(name='ربع فرخ', paper_type=paper, width=Decimal('35'), height=Decimal('50'), pieces_per_sheet=4, is_default=True, sort_order=20)

        url = reverse('printing_pricing:api_piece_sizes') + f'?sheet_size_id={paper.id}'
        response = staff_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        piece_sizes = data['piece_sizes']
        assert len(piece_sizes) >= 2
        # العنصر الأول يجب أن يكون الافتراضي (ربع فرخ)
        assert piece_sizes[0]['is_default'] is True
        assert piece_sizes[0]['name'] == 'ربع فرخ'
        # التأكد من عدم وجود أي عنصر تلقائي
        assert not any(p['name'] == 'auto' or 'تلقائي' in p['name'] for p in piece_sizes)

