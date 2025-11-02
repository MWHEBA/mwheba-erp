# Core Fixtures - إعدادات النظام

## الملف الرسمي: `system_settings_final.json`

ملف شامل يحتوي على **101 إعداد** لجميع جوانب النظام:
- ✅ إعدادات الشركة (18 حقل)
- ✅ إعدادات الفواتير والمالية (4 حقول)
- ✅ إعدادات النظام (79 إعداد)

## التحميل

```bash
python manage.py loaddata core/fixtures/system_settings_final.json
```

## الاستخدام في الكود

```python
from core.models import SystemSetting

# الحصول على إعداد
company_name = SystemSetting.get_setting('company_name', 'مؤسسة موهبة')
```

```django
{% load app_tags %}
{{ 'company_name'|get_setting }}
```
