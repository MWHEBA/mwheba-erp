"""
Django Data Migration: 0046_seed_master_chart_of_accounts
يقوم بتهيئة وبذر شجرة الحسابات المعيارية الرباعية النقية (Pure 4-Level Standard COA)
تلقائياً مع كل عملية migrate في أي بيئة جديدة أو قائمة.
"""
from django.db import migrations


def seed_master_chart_of_accounts(apps, schema_editor):
    AccountType = apps.get_model("financial", "AccountType")
    ChartOfAccounts = apps.get_model("financial", "ChartOfAccounts")
    Currency = apps.get_model("financial", "Currency")

    # 1. ضمان وجود العملة الوظيفية
    egp = Currency.objects.filter(code="EGP").first()
    if not egp:
        egp = Currency.objects.filter(is_functional=True).first()

    # 2. إنشاء وتأكيد أنواع الحسابات الخمسة
    types_data = [
        {"code": "ASSET", "name": "أصول", "category": "asset", "nature": "debit", "level": 1},
        {"code": "LIABILITY", "name": "خصوم", "category": "liability", "nature": "credit", "level": 1},
        {"code": "EQUITY", "name": "حقوق الملكية", "category": "equity", "nature": "credit", "level": 1},
        {"code": "REVENUE", "name": "إيرادات", "category": "revenue", "nature": "credit", "level": 1},
        {"code": "EXPENSE", "name": "مصروفات", "category": "expense", "nature": "debit", "level": 1},
    ]
    account_types = {}
    for t in types_data:
        obj, _ = AccountType.objects.get_or_create(
            code=t["code"],
            defaults={
                "name": t["name"],
                "category": t["category"],
                "nature": t["nature"],
                "level": t["level"],
                "is_active": True,
            }
        )
        account_types[t["code"]] = obj

    # 3. بيانات الشجرة المعيارية النقية الرباعية
    MASTER_TREE = [
        # المستوى 1
        ("1", "الأصول", None, "ASSET", 1, False, False, False),
        ("2", "الخصوم", None, "LIABILITY", 1, False, False, False),
        ("3", "حقوق الملكية", None, "EQUITY", 1, False, False, False),
        ("4", "الإيرادات", None, "REVENUE", 1, False, False, False),
        ("5", "المصروفات", None, "EXPENSE", 1, False, False, False),

        # المستوى 2
        ("11", "الأصول المتداولة", "1", "ASSET", 2, False, False, False),
        ("12", "الأصول الثابتة", "1", "ASSET", 2, False, False, False),
        ("21", "الخصوم المتداولة", "2", "LIABILITY", 2, False, False, False),
        ("22", "الخصوم غير المتداولة", "2", "LIABILITY", 2, False, False, False),
        ("31", "رأس المال وحقوق الملكية", "3", "EQUITY", 2, False, False, False),
        ("41", "إيرادات النشاط", "4", "REVENUE", 2, False, False, False),
        ("42", "إيرادات أخرى ومتنوعة", "4", "REVENUE", 2, False, False, False),
        ("43", "أرباح فروق العملة", "4", "REVENUE", 2, False, False, False),
        ("51", "تكلفة المبيعات والنشاط", "5", "EXPENSE", 2, False, False, False),
        ("52", "المصروفات البيعية والتسويقية", "5", "EXPENSE", 2, False, False, False),
        ("53", "المصروفات العمومية والإدارية", "5", "EXPENSE", 2, False, False, False),
        ("54", "المصروفات والأعباء التمويلية والخسائر الأخرى", "5", "EXPENSE", 2, False, False, False),

        # المستوى 3
        ("111", "النقدية وما في حكمها", "11", "ASSET", 3, False, False, False),
        ("112", "المدينون", "11", "ASSET", 3, False, False, False),
        ("113", "المخزون", "11", "ASSET", 3, False, False, False),
        ("11410", "دفعات مقدمة للموردين", "11", "ASSET", 3, True, False, False),
        ("11420", "مصروفات مدفوعة مقدماً", "11", "ASSET", 3, True, False, False),
        ("11430", "إيرادات مستحقة", "11", "ASSET", 3, True, False, False),
        ("11440", "تأمينات مستردة لدى الغير", "11", "ASSET", 3, True, False, False),
        ("11510", "ضريبة القيمة المضافة - مدخلات (مشتريات)", "11", "ASSET", 3, True, False, False),
        ("11520", "ضرائب مخصومة ومحجوزة لدى الغير", "11", "ASSET", 3, True, False, False),
        ("121", "تكلفة الأصول الثابتة", "12", "ASSET", 3, False, False, False),
        ("122", "مجمع إهلاك الأصول الثابتة", "12", "ASSET", 3, False, False, False),
        ("211", "الدائنون", "21", "LIABILITY", 3, False, False, False),
        ("21210", "بضاعة غير مفوترة (GRNI)", "21", "LIABILITY", 3, True, False, False),
        ("21220", "مصروفات مستحقة", "21", "LIABILITY", 3, True, False, False),
        ("21310", "ضريبة القيمة المضافة - مخرجات (مبيعات)", "21", "LIABILITY", 3, True, False, False),
        ("21320", "ضريبة كسب العمل", "21", "LIABILITY", 3, True, False, False),
        ("21330", "ضرائب مخصومة للغير (خصم وإضافة)", "21", "LIABILITY", 3, True, False, False),
        ("21410", "رواتب وأجور مستحقة", "21", "LIABILITY", 3, True, False, False),
        ("21420", "تأمينات اجتماعية مستحقة", "21", "LIABILITY", 3, True, False, False),
        ("21510", "دفعات مقدمة من العملاء", "21", "LIABILITY", 3, True, False, False),
        ("22110", "قروض بنكية طويلة الأجل", "22", "LIABILITY", 3, True, False, False),
        ("22120", "التزامات إيجار تمويلي", "22", "LIABILITY", 3, True, False, False),
        ("22210", "مخصص مكافأة نهاية الخدمة", "22", "LIABILITY", 3, True, False, False),
        ("31110", "رأس المال", "31", "EQUITY", 3, True, False, False),
        ("312", "جاري الشركاء", "31", "EQUITY", 3, False, False, False),
        ("31310", "الاحتياطيات", "31", "EQUITY", 3, True, False, False),
        ("31410", "الأرباح المرحلة", "31", "EQUITY", 3, True, False, False),
        ("31510", "أرباح (خسائر) العام الحالي", "31", "EQUITY", 3, True, False, False),
        ("41100", "المبيعات", "41", "REVENUE", 3, True, False, False),
        ("41200", "إيرادات الخدمات", "41", "REVENUE", 3, True, False, False),
        ("41910", "مردودات ومسموحات المبيعات", "41", "REVENUE", 3, True, False, False),
        ("41930", "الخصم المسموح به", "41", "REVENUE", 3, True, False, False),
        ("42110", "فوائد بنكية واستثمارات", "42", "REVENUE", 3, True, False, False),
        ("43100", "أرباح فروق العملة", "43", "REVENUE", 3, True, False, False),
        ("49110", "أرباح بيع أصول وإيرادات متنوعة", "42", "REVENUE", 3, True, False, False),
        ("51100", "المشتريات / تكلفة البضاعة", "51", "EXPENSE", 3, True, False, False),
        ("51110", "مصاريف نقل وشحن مشتريات", "51", "EXPENSE", 3, True, False, False),
        ("51120", "رسوم جمركية وتخليص", "51", "EXPENSE", 3, True, False, False),
        ("51200", "تكلفة خامات وخدمات", "51", "EXPENSE", 3, True, False, False),
        ("51910", "مردودات ومسموحات المشتريات", "51", "EXPENSE", 3, True, False, False),
        ("51930", "الخصم المكتسب", "51", "EXPENSE", 3, True, False, False),
        ("52100", "الرواتب والأجور", "52", "EXPENSE", 3, True, False, False),
        ("52200", "التأمينات الاجتماعية", "52", "EXPENSE", 3, True, False, False),
        ("52300", "الإيجارات", "52", "EXPENSE", 3, True, False, False),
        ("52400", "كهرباء ومياه واتصالات", "52", "EXPENSE", 3, True, False, False),
        ("52500", "أدوات مكتبية ومطبوعات", "52", "EXPENSE", 3, True, False, False),
        ("52600", "صيانة ونظافة وضيافة", "52", "EXPENSE", 3, True, False, False),
        ("52700", "أتعاب واستشارات مهنية", "52", "EXPENSE", 3, True, False, False),
        ("52800", "إهلاك الأصول الثابتة", "52", "EXPENSE", 3, True, False, False),
        ("52900", "دعاية وإعلان وتسويق", "52", "EXPENSE", 3, True, False, False),
        ("54100", "عمولات ومصاريف بنكية", "54", "EXPENSE", 3, True, False, False),
        ("54200", "ديون معدومة ومخصصات", "54", "EXPENSE", 3, True, False, False),
        ("54300", "خسائر فروق العملة", "54", "EXPENSE", 3, True, False, False),
        ("54400", "فروق تقريب العملات", "54", "EXPENSE", 3, True, False, False),
        ("54900", "خسائر بيع أصول ومصروفات متنوعة", "54", "EXPENSE", 3, True, False, False),

        # المستوى 4 (الحسابات النهائية والحسابات الرقابية)
        ("11110", "الخزينة الرئيسية", "111", "ASSET", 4, True, True, False),
        ("11120", "الخزائن الفرعية ومنافذ البيع", "111", "ASSET", 4, True, True, False),
        ("11130", "العهد النقدية المستديمة والمؤقتة", "111", "ASSET", 4, True, False, False),
        ("11160", "الحسابات الجارية بالبنوك - محلي", "111", "ASSET", 4, True, False, True),
        ("11170", "الحسابات الجارية بالبنوك - أجنبي", "111", "ASSET", 4, True, False, True),
        ("11180", "ودائع نقدية قصيرة الأجل وتحت الطلب", "111", "ASSET", 4, True, False, False),
        ("11190", "نقدية في الطريق وشيكات برسم التحصيل", "111", "ASSET", 4, True, False, False),
        ("11210", "العملاء", "112", "ASSET", 4, False, False, False),
        ("11220", "أوراق القبض (كمبيالات وشيكات آجلة)", "112", "ASSET", 4, True, False, False),
        ("11230", "حسابات وسلف الموظفين والعهد", "112", "ASSET", 4, True, False, False),
        ("11290", "مخصص الخسائر الائتمانية المتوقعة للعملاء", "112", "ASSET", 4, True, False, False),
        ("11310", "مخزون البضائع التامة والمنتجات الجاهزة", "113", "ASSET", 4, True, False, False),
        ("11320", "مخزون الخامات والمواد الأولية", "113", "ASSET", 4, True, False, False),
        ("11330", "مخزون قطع الغيار ومواد الصيانة", "113", "ASSET", 4, True, False, False),
        ("11340", "مخزون التعبئة والتغليف والمهمات", "113", "ASSET", 4, True, False, False),
        ("11350", "بضائع بالطريق واعتمادات مستندية استيرادية", "113", "ASSET", 4, True, False, False),
        ("11390", "مخصص هبوط أسعار المخزون والركود", "113", "ASSET", 4, True, False, False),
        ("12110", "الأراضي", "121", "ASSET", 4, True, False, False),
        ("12120", "المباني والمنشآت", "121", "ASSET", 4, True, False, False),
        ("12130", "الآلات والمعدات", "121", "ASSET", 4, True, False, False),
        ("12140", "السيارات ووسائل النقل", "121", "ASSET", 4, True, False, False),
        ("12150", "الأثاث والمعدات المكتبية", "121", "ASSET", 4, True, False, False),
        ("12160", "أجهزة الحاسب والشبكات", "121", "ASSET", 4, True, False, False),
        ("12220", "مجمع إهلاك المباني", "122", "ASSET", 4, True, False, False),
        ("12230", "مجمع إهلاك الآلات والمعدات", "122", "ASSET", 4, True, False, False),
        ("12240", "مجمع إهلاك السيارات", "122", "ASSET", 4, True, False, False),
        ("12250", "مجمع إهلاك الأثاث والمعدات", "122", "ASSET", 4, True, False, False),
        ("12260", "مجمع إهلاك أجهزة الحاسب", "122", "ASSET", 4, True, False, False),
        ("21110", "الموردون", "211", "LIABILITY", 4, False, False, False),
        ("21120", "أوراق الدفع (شيكات وكمبيالات صادرة)", "211", "LIABILITY", 4, True, False, False),
        ("31210", "جاري الشريك 1", "312", "EQUITY", 4, True, False, False),
        ("31220", "جاري الشريك 2", "312", "EQUITY", 4, True, False, False),
        ("31290", "مسحوبات الشركاء", "312", "EQUITY", 4, True, False, False),
    ]

    account_map = {}
    for code, name, parent_code, type_code, level, is_leaf, is_cash, is_bank in MASTER_TREE:
        parent = account_map.get(parent_code) if parent_code else None
        account_type = account_types[type_code]

        acc, _ = ChartOfAccounts.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "parent": parent,
                "account_type": account_type,
                "level": level,
                "is_leaf": is_leaf,
                "is_cash_account": is_cash,
                "is_bank_account": is_bank,
                "currency": egp,
                "is_active": True,
            }
        )
        # ضمان تحديث الخصائص الهيكلية
        acc.name = name
        acc.parent = parent
        acc.account_type = account_type
        acc.level = level
        acc.is_leaf = is_leaf
        acc.is_cash_account = is_cash
        acc.is_bank_account = is_bank
        acc.save()

        account_map[code] = acc


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("financial", "0045_seed_default_currencies"),
    ]

    operations = [
        migrations.RunPython(seed_master_chart_of_accounts, reverse_code=reverse_seed),
    ]
