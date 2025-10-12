# 🤝 دليل المساهمة في MWHEBA ERP

مرحباً بك في مجتمع **MWHEBA ERP**! نحن سعداء لاهتمامك بالمساهمة في هذا المشروع. هذا الدليل سيساعدك على البدء والمساهمة بفعالية.

## 📋 جدول المحتويات

- [🎯 كيف يمكنك المساهمة](#-كيف-يمكنك-المساهمة)
- [🚀 البدء السريع](#-البدء-السريع)
- [💻 إعداد بيئة التطوير](#-إعداد-بيئة-التطوير)
- [🔄 سير العمل](#-سير-العمل)
- [📝 معايير الكود](#-معايير-الكود)
- [🧪 الاختبارات](#-الاختبارات)
- [📚 التوثيق](#-التوثيق)
- [🐛 الإبلاغ عن الأخطاء](#-الإبلاغ-عن-الأخطاء)
- [💡 اقتراح الميزات](#-اقتراح-الميزات)

## 🎯 كيف يمكنك المساهمة

### 👨‍💻 المساهمة في الكود
- إصلاح الأخطاء (Bugs)
- تطوير ميزات جديدة
- تحسين الأداء
- تحسين الأمان

### 📚 المساهمة في التوثيق
- تحسين التوثيق الموجود
- إضافة أمثلة وشروحات
- ترجمة التوثيق
- إنشاء فيديوهات تعليمية

### 🧪 المساهمة في الاختبار
- كتابة اختبارات جديدة
- تحسين التغطية
- اختبار الميزات الجديدة
- الإبلاغ عن الأخطاء

### 🎨 المساهمة في التصميم
- تحسين واجهة المستخدم
- تصميم أيقونات جديدة
- تحسين تجربة المستخدم
- تصميم مواد تسويقية

## 🚀 البدء السريع

### 1. Fork المشروع
```bash
# انقر على زر Fork في GitHub
# ثم استنسخ المشروع محلياً
git clone https://github.com/YOUR_USERNAME/mwheba_erp.git
cd mwheba_erp
```

### 2. إعداد البيئة
```bash
# إنشاء بيئة افتراضية
python -m venv venv
source venv/bin/activate  # Linux/Mac
# أو
venv\Scripts\activate  # Windows

# تثبيت المتطلبات
pip install -r requirements.txt
```

### 3. إعداد قاعدة البيانات
```bash
# تشغيل المهاجرات
python manage.py migrate

# تحميل البيانات التجريبية
python setup_development.py
```

### 4. تشغيل الخادم
```bash
python manage.py runserver
```

## 💻 إعداد بيئة التطوير

### 🔧 الأدوات المطلوبة
- **Python 3.8+**
- **Django 4.2+**
- **Redis** (للكاش)
- **Git**
- **محرر نصوص** (VS Code موصى به)

### 📦 المكتبات الإضافية للتطوير
```bash
pip install black flake8 isort mypy pytest-django coverage
```

### ⚙️ إعداد VS Code
أضف هذه الإعدادات في `.vscode/settings.json`:
```json
{
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "editor.formatOnSave": true,
    "python.sortImports.args": ["--profile", "black"]
}
```

## 🔄 سير العمل

### 1. إنشاء فرع جديد
```bash
# إنشاء فرع للميزة الجديدة
git checkout -b feature/new-feature-name

# أو للإصلاح
git checkout -b fix/bug-description
```

### 2. تطوير التغييرات
- اكتب الكود باتباع المعايير
- أضف اختبارات للكود الجديد
- تأكد من نجاح جميع الاختبارات
- حدث التوثيق إذا لزم الأمر

### 3. فحص الجودة
```bash
# فحص التنسيق
black .
isort .
flake8 .

# تشغيل الاختبارات
python manage.py test
```

### 4. إرسال التغييرات
```bash
git add .
git commit -m "feat: add new feature description"
git push origin feature/new-feature-name
```

### 5. إنشاء Pull Request
- اذهب إلى GitHub وأنشئ Pull Request
- اكتب وصفاً واضحاً للتغييرات
- اربط الـ PR بالـ Issue المناسب
- انتظر المراجعة والتعليقات

## 📝 معايير الكود

### 🎨 تنسيق الكود
- استخدم **Black** لتنسيق Python
- استخدم **isort** لترتيب الاستيرادات
- اتبع **PEP 8** للكود Python
- استخدم **Prettier** لـ JavaScript/CSS

### 📛 تسمية المتغيرات
```python
# ✅ جيد
user_name = "أحمد"
total_amount = 1500.50
is_active = True

# ❌ سيء
un = "أحمد"
amt = 1500.50
flag = True
```

### 💬 التعليقات والتوثيق
```python
def calculate_total_price(items, tax_rate=0.15):
    """
    حساب السعر الإجمالي للعناصر مع الضريبة.
    
    Args:
        items (list): قائمة العناصر
        tax_rate (float): معدل الضريبة (افتراضي 15%)
    
    Returns:
        float: السعر الإجمالي شامل الضريبة
    """
    subtotal = sum(item.price for item in items)
    tax_amount = subtotal * tax_rate
    return subtotal + tax_amount
```

### 🏗️ هيكل الكود
```python
# ترتيب الاستيرادات
# 1. مكتبات Python الأساسية
import os
import json
from datetime import datetime

# 2. مكتبات خارجية
from django.db import models
from django.contrib.auth.models import User

# 3. مكتبات المشروع
from core.models import BaseModel
from utils.helpers import format_currency
```

## 🧪 الاختبارات

### ✅ كتابة الاختبارات
```python
from django.test import TestCase
from django.contrib.auth.models import User
from financial.models import ChartOfAccounts

class ChartOfAccountsTestCase(TestCase):
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
    def test_create_account(self):
        """اختبار إنشاء حساب جديد"""
        account = ChartOfAccounts.objects.create(
            code='1001',
            name='الخزينة',
            account_type='CASH'
        )
        self.assertEqual(account.code, '1001')
        self.assertEqual(account.name, 'الخزينة')
```

### 🏃‍♂️ تشغيل الاختبارات
```bash
# تشغيل جميع الاختبارات
python manage.py test

# تشغيل اختبارات تطبيق معين
python manage.py test financial

# تشغيل اختبار محدد
python manage.py test financial.tests.test_models.ChartOfAccountsTestCase

# مع تقرير التغطية
coverage run --source='.' manage.py test
coverage report
coverage html
```

## 📚 التوثيق

### 📖 أنواع التوثيق
1. **Docstrings** - في الكود
2. **README** - نظرة عامة
3. **Wiki** - دليل مفصل
4. **API Docs** - توثيق API

### ✍️ كتابة التوثيق
```markdown
## 🔧 تثبيت النظام

### المتطلبات
- Python 3.8+
- Django 4.2+
- Redis

### خطوات التثبيت
1. استنسخ المشروع
2. ثبت المتطلبات
3. شغل المهاجرات
```

## 🐛 الإبلاغ عن الأخطاء

### 📋 معلومات مطلوبة
- **وصف الخطأ** - ماذا حدث؟
- **خطوات الإعادة** - كيف نكرر الخطأ؟
- **السلوك المتوقع** - ماذا كان يجب أن يحدث؟
- **البيئة** - نظام التشغيل، إصدار Python، إلخ
- **لقطات شاشة** - إذا كان مناسباً

### 🏷️ تصنيف الأخطاء
- `critical` - يوقف النظام
- `high` - يؤثر على وظائف مهمة
- `medium` - مشكلة ملحوظة
- `low` - مشكلة تجميلية

## 💡 اقتراح الميزات

### 🎯 معايير الميزة الجيدة
- **مفيدة** - تحل مشكلة حقيقية
- **واضحة** - سهلة الفهم والاستخدام
- **متسقة** - تتماشى مع فلسفة النظام
- **قابلة للتطوير** - لا تعقد الكود

### 📝 نموذج اقتراح الميزة
```markdown
## 🎯 المشكلة
وصف المشكلة التي تحلها الميزة

## 💡 الحل المقترح
وصف الميزة المقترحة

## 🎨 التصميم
كيف ستبدو الميزة؟

## 🔧 التنفيذ
أفكار حول كيفية التنفيذ
```

## 🏆 مستويات المساهمة

### 🥉 مساهم جديد
- إصلاح أخطاء بسيطة
- تحسين التوثيق
- إضافة اختبارات

### 🥈 مساهم نشط
- تطوير ميزات صغيرة
- مراجعة Pull Requests
- مساعدة المستخدمين الجدد

### 🥇 مساهم أساسي
- تطوير ميزات كبيرة
- اتخاذ قرارات تقنية
- إرشاد المساهمين الجدد

### 💎 صاحب المشروع
- رؤية المشروع
- إدارة الإصدارات
- التخطيط الاستراتيجي

## 📞 التواصل

### 💬 قنوات التواصل
- **GitHub Issues** - للأخطاء والميزات
- **GitHub Discussions** - للنقاشات العامة
- **Discord** - للدردشة المباشرة
- **Email** - للأمور الخاصة

### 🤝 آداب التواصل
- كن محترماً ومهذباً
- استخدم لغة واضحة ومفهومة
- ساعد الآخرين واطلب المساعدة
- احتفل بإنجازات الفريق

## 🎉 شكر وتقدير

**شكراً لك على اهتمامك بالمساهمة في MWHEBA ERP!**

كل مساهمة، مهما كانت صغيرة، تساعد في جعل النظام أفضل للجميع. نحن نقدر وقتك وجهدك، ونتطلع للعمل معك!

---

**🚀 معاً نبني أفضل نظام ERP عربي مفتوح المصدر!**

*آخر تحديث: أكتوبر 2024*
