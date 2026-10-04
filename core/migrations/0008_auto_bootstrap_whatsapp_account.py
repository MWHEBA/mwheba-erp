from django.db import migrations


def bootstrap_default_whatsapp_account(apps, schema_editor):
    SystemSetting = apps.get_model('core', 'SystemSetting')
    WhatsAppAccount = apps.get_model('core', 'WhatsAppAccount')
    WhatsAppMessageLog = apps.get_model('core', 'WhatsAppMessageLog')

    # جلب الإعدادات الحالية من SystemSetting
    settings_dict = {}
    for s in SystemSetting.objects.filter(key__startswith='WHATSAPP_'):
        settings_dict[s.key] = s.value

    phone_number_id = settings_dict.get('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    raw_token = settings_dict.get('WHATSAPP_ACCESS_TOKEN', '').strip()
    waba_id = settings_dict.get('WHATSAPP_WABA_ID', '').strip()
    app_id = settings_dict.get('WHATSAPP_APP_ID', '').strip()
    display_phone = settings_dict.get('WHATSAPP_DISPLAY_PHONE', '').strip()
    business_name = settings_dict.get('WHATSAPP_BUSINESS_NAME', '').strip() or "الحساب الافتراضي للنظام"

    if phone_number_id:
        from core.services.whatsapp_crypto import encrypt_token
        encrypted_tok = encrypt_token(raw_token) if raw_token else ""

        account, created = WhatsAppAccount.objects.get_or_create(
            phone_number_id=phone_number_id,
            defaults={
                'name': business_name,
                'company_name': business_name,
                'waba_id': waba_id,
                'display_phone_number': display_phone,
                'verified_name': business_name,
                'encrypted_access_token': encrypted_tok,
                'app_id': app_id,
                'is_coexistence': True,
                'is_default': True,
                'account_status': 'CONNECTED',
                'quality_rating': 'GREEN',
                'daily_limit_tier': 'TIER_250',
                'notes': 'تم الترحيل الآلي من إعدادات النظام القديمة (Auto-Bootstrapped Zero-Downtime Migration)'
            }
        )

        # ربط السجلات القديمة بالحساب الافتراضي بالتجزئة الآمنة (Chunked Update)
        logs_to_update = []
        for log in WhatsAppMessageLog.objects.filter(account__isnull=True).iterator(chunk_size=1000):
            log.account_id = account.id
            logs_to_update.append(log)
            if len(logs_to_update) >= 1000:
                WhatsAppMessageLog.objects.bulk_update(logs_to_update, ['account_id'])
                logs_to_update = []
        if logs_to_update:
            WhatsAppMessageLog.objects.bulk_update(logs_to_update, ['account_id'])


def reverse_bootstrap(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_whatsappmessagelog_document_sha256_and_more'),
    ]

    operations = [
        migrations.RunPython(bootstrap_default_whatsapp_account, reverse_bootstrap),
    ]
