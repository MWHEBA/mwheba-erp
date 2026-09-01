from decimal import Decimal
from django.db import migrations


def seed_product_sizes(apps, schema_editor):
    ProductSize = apps.get_model('printing_pricing', 'ProductSize')

    standard_sizes = [
        {
            'name': 'A4 معياري',
            'width': Decimal('21.00'),
            'height': Decimal('29.70'),
            'sort_order': 10,
            'is_default': True,
            'is_active': True,
            'description': 'مقاس A4 القياسي (21×29.7 سم) للمستندات والبروشورات والكتالوجات'
        },
        {
            'name': 'A5 كتيب / فلاير',
            'width': Decimal('14.80'),
            'height': Decimal('21.00'),
            'sort_order': 20,
            'is_default': False,
            'is_active': True,
            'description': 'مقاس A5 (14.8×21 سم) للفلايرات والكتيبات الدعائية'
        },
        {
            'name': 'A3 بوستر / فرخ مزدوج',
            'width': Decimal('29.70'),
            'height': Decimal('42.00'),
            'sort_order': 30,
            'is_default': False,
            'is_active': True,
            'description': 'مقاس A3 (29.7×42 سم) للبوسترات ومطويات 3 بوابة الكبيرة'
        },
        {
            'name': 'A6 مذكرات صغيرة',
            'width': Decimal('10.50'),
            'height': Decimal('14.80'),
            'sort_order': 40,
            'is_default': False,
            'is_active': True,
            'description': 'مقاس A6 (10.5×14.8 سم) للبلوك نوت والمذكرات الجيب'
        },
        {
            'name': 'كارت شخصي فاخر',
            'width': Decimal('9.00'),
            'height': Decimal('5.00'),
            'sort_order': 50,
            'is_default': False,
            'is_active': True,
            'description': 'مقاس الكروت الشخصية القياسي (9×5 سم)'
        },
        {
            'name': 'فولدر شركات مع جيب',
            'width': Decimal('22.00'),
            'height': Decimal('31.00'),
            'sort_order': 60,
            'is_default': False,
            'is_active': True,
            'description': 'مقاس الفولدر المقفول مع جيب (22×31 سم) ليسع مستندات A4'
        },
        {
            'name': 'بروشور 3 بوابة',
            'width': Decimal('21.00'),
            'height': Decimal('29.70'),
            'sort_order': 70,
            'is_default': False,
            'is_active': True,
            'description': 'بروشور A4 يطوى إلى 3 أجزاء (9.9×21 سم لكل بوابة)'
        },
        {
            'name': 'B5 كتب ومذكرات',
            'width': Decimal('17.60'),
            'height': Decimal('25.00'),
            'sort_order': 80,
            'is_default': False,
            'is_active': True,
            'description': 'مقاس B5 المعتمد للكتب المدرسية والمذكرات الجامعية'
        }
    ]

    for item in standard_sizes:
        ProductSize.objects.update_or_create(
            name=item['name'],
            defaults=item
        )


def reverse_seed_product_sizes(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('printing_pricing', '0011_alter_productsize_options_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_product_sizes, reverse_seed_product_sizes),
    ]
