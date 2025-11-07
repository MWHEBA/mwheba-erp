# نظام البصمة - دليل شامل

## نظرة عامة

نظام البصمة المُبسّط يربط أجهزة البصمة بنظام الموارد البشرية بشكل مباشر وفعال.

---

## الفلسفة

### النهج المُبسّط
```
ماكينة البصمة → BiometricLog → التقارير والحسابات مباشرة
```

**المميزات:**
- ✅ بسيط - جدول واحد، لا تعقيد
- ✅ مباشر - البيانات متاحة فوراً
- ✅ موثوق - لا dependencies إضافية
- ✅ واضح - مربوط أو غير مربوط فقط

---

## المكونات الأساسية

### 1. النماذج (Models)
- **BiometricLog** - سجلات البصمة الخام
- **BiometricUserMapping** - ربط معرفات البصمة بالموظفين
- **BiometricDevice** - أجهزة البصمة
- **BiometricSyncLog** - سجلات المزامنة

### 2. الواجهات الرئيسية
```
/hr/biometric/dashboard/              - لوحة التحكم الشاملة
/hr/biometric/mapping/                - إدارة الربط
/hr/biometric-devices/                - إدارة الأجهزة
/hr/biometric-logs/                   - عرض السجلات
```

### 3. Bridge Agent
- **الموقع**: `bridge_agent/agent.py`
- **الوظيفة**: مزامنة البيانات من أجهزة البصمة
- **التشغيل**: `python agent.py`

---

## كيفية الاستخدام

### 1. إعداد الأجهزة
1. أضف جهاز بصمة جديد من `/hr/biometric-devices/`
2. احصل على `device_code` و `agent_secret`
3. أضفهم في `settings.py`:
```python
BRIDGE_AGENTS = {
    'DEVICE001': 'your-secret-key-here'
}
```

### 2. تشغيل Bridge Agent
```bash
cd bridge_agent
python agent.py
```

### 3. ربط الموظفين
- اذهب إلى `/hr/biometric/mapping/`
- أضف ربط جديد: `user_id` من الماكينة → `Employee` في النظام
- الربط التلقائي سيعمل للسجلات الجديدة

### 4. مراقبة السجلات
- **Dashboard**: `/hr/biometric/dashboard/`
- **السجلات**: `/hr/biometric-logs/`
- **الحالة**: مربوط ✅ / غير مربوط ⚠️

---

## حساب الحضور

### مباشرة من BiometricLog
```python
from hr.models import BiometricLog
from datetime import date

# جلب سجلات يوم معين
logs = BiometricLog.objects.filter(
    employee=employee,
    timestamp__date=date.today()
).order_by('timestamp')

# أول بصمة = حضور
check_in = logs.first()

# آخر بصمة = انصراف
check_out = logs.last()

# حساب ساعات العمل
if check_in and check_out:
    work_hours = (check_out.timestamp - check_in.timestamp).total_seconds() / 3600
```

---

## الأمان

### 1. المصادقة
- `@login_required` على جميع الواجهات
- HMAC authentication للـ Bridge Agent
- CSRF protection

### 2. Rate Limiting
- 100 طلب/ساعة للـ APIs العامة
- غير محدود لـ Bridge Agent المُصرح

### 3. التحقق من البيانات
- Django Forms validation
- Model-level validation
- API input validation

---

## الأداء

### 1. استعلامات محسّنة
```python
# استخدام select_related للعلاقات
logs = BiometricLog.objects.select_related('employee', 'device')

# استخدام aggregate للإحصائيات
stats = BiometricLog.objects.aggregate(
    total=Count('id'),
    linked=Count('id', filter=Q(employee__isnull=False))
)
```

### 2. التخزين المؤقت
- إحصائيات Dashboard (5 دقائق)
- قوائم الأجهزة
- اقتراحات الربط

---

## استكشاف الأخطاء

### المشكلة: السجلات لا تظهر
**الحل:**
1. تحقق من تشغيل Bridge Agent
2. تحقق من `device_code` في settings
3. راجع logs في `bridge_agent/logs/`

### المشكلة: السجلات غير مربوطة
**الحل:**
1. أضف mapping في `/hr/biometric/mapping/`
2. تأكد من `user_id` صحيح
3. استخدم اقتراحات الربط الذكية

### المشكلة: بطء في التقارير
**الحل:**
1. استخدم فلاتر التاريخ
2. حدد نطاق زمني أصغر
3. استخدم indexes على الحقول

---

## الملفات المهمة

### الكود الأساسي
```
hr/models/biometric_log.py          - نموذج BiometricLog
hr/models/biometric_mapping.py      - نموذج BiometricUserMapping
hr/models/biometric_device.py       - نموذج BiometricDevice
hr/views.py                          - Views والـ APIs
hr/urls.py                           - مسارات URLs
```

### القوالب
```
templates/hr/biometric/dashboard.html      - لوحة التحكم
templates/hr/biometric/mapping_list.html   - قائمة الربط
templates/hr/biometric/mapping_form.html   - نموذج الربط
```

### Bridge Agent
```
bridge_agent/agent.py               - السكريبت الرئيسي
bridge_agent/config.json            - الإعدادات
bridge_agent/logs/                  - سجلات التشغيل
```

---

## التكامل مع الأنظمة الأخرى

### نظام الحضور
- يقرأ من `BiometricLog` مباشرة
- يحسب ساعات العمل والتأخير
- يدعم الورديات المختلفة

### نظام المرتبات
- يقرأ من `BiometricLog` مباشرة
- يحسب أيام الحضور والغياب
- يحسب الساعات الإضافية

### نظام التقارير
- تقارير يومية/أسبوعية/شهرية
- تقارير التأخير والغياب
- تقارير الحضور حسب القسم

---

## الخلاصة

### النظام يوفر:
- ✅ ربط مباشر مع أجهزة البصمة
- ✅ مزامنة تلقائية للبيانات
- ✅ ربط ذكي للموظفين
- ✅ حسابات دقيقة للحضور
- ✅ تقارير شاملة

### الحالة:
- ✅ مكتمل ومُختبر
- ✅ جاهز للإنتاج
- ✅ موثق بالكامل

---

**آخر تحديث:** 2025-11-05  
**الإصدار:** 2.0.0  
**الحالة:** ✅ مكتمل
