# دليل الاختبارات - Testing Guide

## نظرة عامة

هذا الدليل يوضح كيفية تشغيل الاختبارات في المشروع باستخدام pytest وفقاً لمعايير المشروع.

## تشغيل الاختبارات

### الأوامر الأساسية

```bash
# تشغيل جميع الاختبارات
pytest

# تشغيل اختبارات وحدة معينة
pytest client/tests/
pytest utils/tests/
pytest financial/tests/

# تشغيل ملف اختبار محدد
pytest tests/unit/test_financial_settlement_services.py

# تشغيل اختبار محدد
pytest tests/unit/test_financial_settlement_services.py::TestClientRefundModelBasic::test_create_refund
```

### أوامر متقدمة

```bash
# تشغيل مع تغطية الكود
pytest --cov=. --cov-report=html --cov-report=term-missing

# تشغيل الاختبارات السريعة فقط
pytest -m "not slow"

# تشغيل اختبارات التكامل
pytest -m integration

# تشغيل مع تفاصيل أكثر
pytest -v

# إيقاف عند أول فشل
pytest -x

# تشغيل متوازي (إذا كان pytest-xdist مثبت)
pytest -n auto
```

## بنية الاختبارات

### المجلدات الرئيسية

```
tests/
├── conftest.py                 # إعدادات pytest العامة
├── integrity/                  # اختبارات تكامل النظام
├── unit/                      # اختبارات الوحدة
└── utils/                     # أدوات مساعدة للاختبارات

# اختبارات كل تطبيق في مجلده
client/tests/
utils/tests/
users/tests/
financial/tests/
hr/tests/
```

### أنواع الاختبارات

#### اختبارات الوحدة (Unit Tests)
```python
import pytest
from django.test import TestCase

class TestClientService(TestCase):
    def test_create_client(self):
        # اختبار إنشاء عميل
        pass
```

#### اختبارات التكامل (Integration Tests)
```python
@pytest.mark.integration
@pytest.mark.django_db
def test_client_registration_flow():
    # اختبار تدفق تسجيل العميل الكامل
    pass
```

#### اختبارات الأداء (Performance Tests)
```python
@pytest.mark.slow
def test_bulk_client_creation():
    # اختبار إنشاء عدد كبير من العملاء
    pass
```

## Fixtures المتاحة

### Fixtures أساسية (من conftest.py)

```python
def test_with_user(test_user):
    # استخدام مستخدم تجريبي
    assert test_user.is_active

def test_with_admin(admin_user):
    # استخدام مستخدم إداري
    assert admin_user.is_staff

def test_with_client(client_with_user):
    # استخدام client مع مستخدم مسجل
    response = client_with_user.get('/dashboard/')
    assert response.status_code == 200
```

### Fixtures متخصصة

```python
def test_academic_year(academic_year):
    # استخدام سنة مالية تجريبية
    assert academic_year.is_active

def test_with_client(test_client):
    # استخدام عميل تجريبي
    assert test_client.name
```

## Markers المتاحة

### Markers أساسية

```python
@pytest.mark.slow          # اختبارات بطيئة
@pytest.mark.integration   # اختبارات تكامل
@pytest.mark.unit         # اختبارات وحدة
@pytest.mark.e2e          # اختبارات end-to-end
```

### Markers للتنظيف

```python
@pytest.mark.cleanup_after    # تنظيف بعد الاختبار
@pytest.mark.no_cleanup       # منع التنظيف
@pytest.mark.cleanup_before   # تنظيف قبل الاختبار
@pytest.mark.preserve_data    # الحفاظ على البيانات
```

## إعدادات قاعدة البيانات

### استخدام قاعدة البيانات

```python
# للاختبارات التي تحتاج قاعدة بيانات
@pytest.mark.django_db
def test_database_operation():
    pass

# للاختبارات التي تحتاج معاملات
@pytest.mark.django_db(transaction=True)
def test_transaction_operation():
    pass
```

### إعادة استخدام قاعدة البيانات

```bash
# إعادة استخدام قاعدة البيانات لتسريع الاختبارات
pytest --reuse-db

# إنشاء قاعدة بيانات جديدة
pytest --create-db
```

## أفضل الممارسات

### كتابة الاختبارات

1. **استخدم الاختبارات الموجودة**: ابحث عن اختبار مشابه وحدثه بدلاً من إنشاء جديد
2. **اختبر الوظائف الحرجة فقط**: لا تكتب اختبارات لكل شيء
3. **استخدم أسماء واضحة**: `test_create_client_with_valid_data`
4. **اختبار واحد لكل وظيفة**: لا تجمع عدة اختبارات في واحد

### تنظيم الاختبارات

```python
class TestClientService:
    """مجموعة اختبارات خدمة العملاء"""
    
    def setup_method(self):
        """إعداد قبل كل اختبار"""
        self.service = ClientService()
    
    def test_create_client(self):
        """اختبار إنشاء عميل"""
        pass
    
    def test_update_client(self):
        """اختبار تحديث عميل"""
        pass
```

### معالجة الأخطاء

```python
def test_invalid_data_raises_error():
    """اختبار أن البيانات غير الصحيحة تثير خطأ"""
    with pytest.raises(ValidationError):
        create_client_with_invalid_data()
```

## تشغيل اختبارات محددة

### حسب الملف أو المجلد

```bash
# اختبارات العملاء فقط
pytest client/tests/

# اختبارات الخدمات المالية
pytest tests/unit/test_financial_settlement_services.py

# اختبارات التحقق من البيانات
pytest utils/tests/test_validators.py
```

### حسب النمط

```bash
# جميع اختبارات الخدمات
pytest -k "service"

# اختبارات الإنشاء فقط
pytest -k "create"

# استثناء اختبارات معينة
pytest -k "not slow"
```

### حسب Marker

```bash
# الاختبارات السريعة فقط
pytest -m "not slow"

# اختبارات التكامل فقط
pytest -m integration

# اختبارات الوحدة فقط
pytest -m unit
```

## التقارير والتغطية

### تقرير التغطية

```bash
# تشغيل مع تغطية
pytest --cov=client --cov=utils --cov-report=html

# عرض التغطية في الطرفية
pytest --cov=. --cov-report=term-missing

# حفظ تقرير التغطية
pytest --cov=. --cov-report=html:htmlcov/
```

### تقارير مفصلة

```bash
# تقرير مفصل
pytest -v

# تقرير قصير
pytest -q

# عرض أبطأ الاختبارات
pytest --durations=10
```

## استكشاف الأخطاء

### عرض المخرجات

```bash
# عرض print statements
pytest -s

# عرض تفاصيل الأخطاء
pytest --tb=long

# عرض مختصر للأخطاء
pytest --tb=short
```

### تشغيل تفاعلي

```bash
# إيقاف عند الخطأ والدخول في debugger
pytest --pdb

# إيقاف عند أول فشل
pytest -x

# إيقاف بعد عدد معين من الفشل
pytest --maxfail=3
```

## الهجرة من Django Test

### الأوامر القديمة والجديدة

```bash
# القديم (لا تستخدم)
python manage.py test

# الجديد (استخدم هذا)
pytest

# القديم
python manage.py test client.tests.test_models

# الجديد
pytest client/tests/test_models.py
```

### تحديث الاختبارات الموجودة

معظم اختبارات Django TestCase تعمل مع pytest بدون تغيير:

```python
# هذا يعمل مع pytest
from django.test import TestCase

class MyTest(TestCase):
    def test_something(self):
        self.assertEqual(1, 1)
```

## نصائح للأداء

### تسريع الاختبارات

```bash
# استخدام قاعدة بيانات في الذاكرة
pytest --ds=corporate_erp.settings.testing

# إعادة استخدام قاعدة البيانات
pytest --reuse-db

# تشغيل متوازي
pytest -n auto  # يتطلب pytest-xdist
```

### تجنب الاختبارات البطيئة

```bash
# تخطي الاختبارات البطيئة
pytest -m "not slow"

# تشغيل الاختبارات السريعة فقط
pytest -m "unit and not slow"
```

## الخلاصة

- **استخدم pytest** بدلاً من `python manage.py test`
- **حدث الاختبارات الموجودة** بدلاً من إنشاء جديدة
- **اكتب اختبارات للوظائف الحرجة فقط**
- **استخدم Fixtures والـ Markers** المتاحة
- **اتبع أفضل الممارسات** في التنظيم والتسمية

---

*آخر تحديث: يناير 2025*