# MWHEBA ERP — نظام إدارة الموارد المؤسسية

<div align="center">

![Django](https://img.shields.io/badge/Django-4.2+-092E20?style=flat-square&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5-7952B3?style=flat-square&logo=bootstrap&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

نظام ERP متكامل مبني بـ Django، مصمم للشركات والمؤسسات العربية

[التثبيت](#-التثبيت) · [الميزات](#-الميزات) · [هيكل المشروع](#-هيكل-المشروع) · [التوثيق](#-التوثيق)

</div>

---

## نظرة عامة

**MWHEBA ERP** نظام إدارة موارد مؤسسية شامل يغطي المحاسبة، المخزون، المبيعات، المشتريات، الموارد البشرية، وتسعير الطباعة — كل ذلك بواجهة عربية كاملة مع دعم RTL.

---

## الميزات

| الوحدة | الوصف |
|--------|-------|
| **المالية والمحاسبة** | دليل حسابات، قيود تلقائية، فترات محاسبية، تقارير مالية |
| **المخزون** | تتبع الحركات، مخازن متعددة، تصنيفات هرمية، تنبيهات |
| **المبيعات** | فواتير، كشوف عملاء، خصومات، تتبع مدفوعات |
| **المشتريات** | أوامر شراء، فواتير موردين، مرتجعات |
| **الموارد البشرية** | موظفون، عقود، حضور، رواتب، إجازات |
| **تسعير الطباعة** | حاسبة أوفست ورقمية، إدارة موردين متخصصين |
| **الأمان** | أدوار وصلاحيات مفصلة، Audit Log، حماية CSRF |

---

## التثبيت

### المتطلبات

- Python 3.8+
- Git

### الإعداد

```bash
# 1. استنساخ المشروع
git clone https://github.com/MWHEBA/mwheba-erp.git
cd mwheba-erp

# 2. إنشاء البيئة الافتراضية
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 3. تثبيت المتطلبات
pip install -r requirements.txt

# 4. إعداد قاعدة البيانات
python manage.py migrate

# 5. إنشاء مستخدم مدير
python manage.py createsuperuser

# 6. تشغيل الخادم
python manage.py runserver
```

ثم افتح المتصفح على `http://127.0.0.1:8000`

---

## هيكل المشروع

```
mwheba-erp/
├── core/                  # النواة والإعدادات المشتركة
├── users/                 # المستخدمين والصلاحيات
├── financial/             # النظام المالي والمحاسبي
├── product/               # المنتجات والمخزون
├── sale/                  # المبيعات والفواتير
├── purchase/              # المشتريات
├── client/                # إدارة العملاء
├── supplier/              # إدارة الموردين
├── hr/                    # الموارد البشرية
├── printing_pricing/      # تسعير الطباعة
├── api/                   # REST API
├── utils/                 # أدوات مساعدة
├── templates/             # قوالب HTML
├── static/                # CSS, JS, الصور
├── corporate_erp/         # إعدادات Django
└── requirements.txt
```

---

## التوثيق

- [معمارية النظام](docs/architecture.md)
- [دليل النشر](DEPLOYMENT_GUIDE.md)
- [توثيق API](docs/api-documentation.md)

---

## المساهمة

1. Fork المشروع
2. أنشئ فرع جديد: `git checkout -b feature/your-feature`
3. Commit: `git commit -m 'إضافة ميزة جديدة'`
4. Push: `git push origin feature/your-feature`
5. افتح Pull Request

---

## الترخيص

مرخص تحت [MIT License](LICENSE).

---

<div align="center">
صُنع بـ ❤️ في مصر
</div>
