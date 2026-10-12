# Generated manually for MWHEBA ERP WhatsApp Module Governance

from django.db import migrations


def register_whatsapp_module(apps, schema_editor):
    SystemModule = apps.get_model('core', 'SystemModule')
    SystemSetting = apps.get_model('core', 'SystemSetting')

    # فحص قيمة الإعداد الحالية إن وُجدت
    setting = SystemSetting.objects.filter(key='whatsapp_enabled').first()
    is_enabled_initial = False
    if setting:
        is_enabled_initial = setting.value.strip().lower() in ('true', '1', 'yes', 'on')

    # تسجيل موديول منظومة الواتساب للأعمال
    whatsapp_mod, created = SystemModule.objects.get_or_create(
        code='whatsapp',
        defaults={
            'name_ar': 'منظومة WhatsApp للأعمال',
            'name_en': 'WhatsApp Business System',
            'description': 'منظومة حسابات واتساب للأعمال، الشات الحي لخدمة العملاء، الحملات التسويقية، ومشاركة الفواتير وسندات القبض آلياً.',
            'icon': 'fab fa-whatsapp',
            'module_type': 'optional',
            'is_enabled': is_enabled_initial,
            'order': 70,
            'url_namespace': 'core:whatsapp_settings',
            'menu_id': 'settingsMenu',
        }
    )
    if not created:
        whatsapp_mod.name_ar = 'منظومة WhatsApp للأعمال'
        whatsapp_mod.name_en = 'WhatsApp Business System'
        whatsapp_mod.description = 'منظومة حسابات واتساب للأعمال، الشات الحي لخدمة العملاء، الحملات التسويقية، ومشاركة الفواتير وسندات القبض آلياً.'
        whatsapp_mod.icon = 'fab fa-whatsapp'
        whatsapp_mod.module_type = 'optional'
        whatsapp_mod.url_namespace = 'core:whatsapp_settings'
        whatsapp_mod.order = 70
        whatsapp_mod.save()

    # مزامنة SystemSetting لضمان وجود الإعداد
    if not setting:
        SystemSetting.objects.create(
            key='whatsapp_enabled',
            value='true' if is_enabled_initial else 'false',
            group='whatsapp',
            data_type='boolean',
            description='حالة تفعيل منظومة WhatsApp للأعمال',
            is_active=True
        )


def reverse_whatsapp_module(apps, schema_editor):
    SystemModule = apps.get_model('core', 'SystemModule')
    SystemModule.objects.filter(code='whatsapp').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_whatsapp_campaign_models'),
    ]

    operations = [
        migrations.RunPython(register_whatsapp_module, reverse_whatsapp_module),
    ]
