from django.db import migrations

def seed_standard_product_types(apps, schema_editor):
    ProductType = apps.get_model('printing_pricing', 'ProductType')
    
    standard_types = [
        {
            'name': 'مطبوع مفرود (كروت / فلاير)',
            'base_archetype': 'flyer',
            'sort_order': 10,
            'description': 'كروت شخصية، فلايرات، بروشورات، بوسترات، أظرف، ستيكر',
            'is_active': True,
            'is_default': True,
        },
        {
            'name': 'مطبوع مع داخلي (كتالوج / بلوك نوت)',
            'base_archetype': 'catalog',
            'sort_order': 20,
            'description': 'كتالوجات، كتب، مجلات، مذكرات، بروفايلات شركات، بلوك نوت (داخلي + غلاف)',
            'is_active': True,
            'is_default': False,
        },
        {
            'name': 'مطبوع مع فورمة تكسير',
            'base_archetype': 'folder',
            'sort_order': 30,
            'description': 'فولدرات شركات بجيب، علب كرتون، باكيج وتغليف مع تكسير',
            'is_active': True,
            'is_default': False,
        },
        {
            'name': 'دفاتر مكربن',
            'base_archetype': 'invoice',
            'sort_order': 40,
            'description': 'دفاتر فواتير، إيصالات، عقود مكربنة NCR، أذون مخازن',
            'is_active': True,
            'is_default': False,
        },
        {
            'name': 'هدايا دعائية و UV',
            'base_archetype': 'giveaways',
            'sort_order': 50,
            'description': 'أقلام، مجات، مستلزمات مكتبية، شيتات كريستال UV-DTF',
            'is_active': True,
            'is_default': False,
        },
    ]

    for item in standard_types:
        # التحديث بحسب base_archetype لضمان تعديل الأسماء القائمة بدون تكرار
        ProductType.objects.update_or_create(
            base_archetype=item['base_archetype'],
            defaults={
                'name': item['name'],
                'sort_order': item['sort_order'],
                'description': item['description'],
                'is_active': item['is_active'],
                'is_default': item['is_default'],
            }
        )

def rollback_standard_product_types(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('printing_pricing', '0009_alter_producttype_options_producttype_base_archetype_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_standard_product_types, rollback_standard_product_types),
    ]
