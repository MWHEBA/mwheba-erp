"""
Django Management Command: setup_accounting_system
يقوم بإنشاء وتهيئة الهيكل المحاسبي والمالي والضريبي المعياري المتكامل (Master Enterprise Accounting Engine)
للأنظمة الجديدة بالكامل وبأعلى معايير الحوكمة المالية الدولية IAS / IFRS.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date
from decimal import Decimal
import logging
import calendar

from financial.models import (
    AccountType,
    ChartOfAccounts,
    FiscalYear,
    AccountingPeriod,
    Currency,
    ExchangeRate,
    TaxJurisdiction,
    TaxCode,
    TaxAccountMapping,
    CostCenter,
    FinancialCategory,
    FinancialSubcategory,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "تهيئة النظام المالي والمحاسبي والضريبي الشامل وإنشاء شجرة الحسابات والتصنيفات والعملات"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="تحديث البيانات حتى لو كانت موجودة مسبقاً",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="السنة المالية لإنشاء الفترات المحاسبية",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        year = options.get("year", timezone.now().year)

        self.stdout.write(self.style.HTTP_INFO("[*] Starting Enterprise Financial & Accounting Provisioning..."))

        try:
            with transaction.atomic():
                # 1. إنشاء العملات وأسعار الصرف التاريخية
                egp, usd, eur, sar = self.setup_currencies()

                # 2. إنشاء أنواع الحسابات الرئيسية الخمسة
                account_types = self.setup_account_types(force)

                # 3. إنشاء شجرة الحسابات المعيارية الرباعية النقية (105 حساباً)
                account_map = self.setup_chart_of_accounts(account_types, egp, force)

                # 4. تهيئة المحرك الضريبي وأكواد الضرائب والربط المحاسبي
                self.setup_tax_engine(account_map, force)

                # 5. تهيئة مركز التكلفة الجذري الافتراضي
                self.setup_cost_centers(force)

                # 6. زراعة التصنيفات المالية الشاملة ومراكز تكلفة الموارد البشرية
                self.setup_financial_categories(account_map, force)

                # 7. إنشاء السنة المالية والفترات المحاسبية الـ 12
                self.setup_fiscal_structure(year)

                self.stdout.write(self.style.SUCCESS("\n[+] Enterprise Accounting & Tax Setup COMPLETED SUCCESSFULLY (100%)!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n[-] Error in setup_accounting_system: {str(e)}"))
            logger.exception("Error in setup_accounting_system")
            raise

    def setup_currencies(self):
        """إنشاء العملات الافتراضية وتسجيل أسعار الصرف الاسترشادية وفق معيار IAS 21"""
        self.stdout.write("[*] Setting up currencies & exchange rates (IAS 21)...")
        egp, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
        )
        usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False}
        )
        eur, _ = Currency.objects.get_or_create(
            code="EUR",
            defaults={"name": "يورو", "symbol": "€", "is_functional": False}
        )
        sar, _ = Currency.objects.get_or_create(
            code="SAR",
            defaults={"name": "ريال سعودي", "symbol": "ر.س", "is_functional": False}
        )

        # تسجيل أسعار صرف استرشادية ابتدائية
        initial_rates = [
            (usd, egp, Decimal("50.000000")),
            (eur, egp, Decimal("53.000000")),
            (sar, egp, Decimal("13.300000")),
        ]
        today = timezone.now().date()
        for from_curr, to_curr, rate_val in initial_rates:
            ExchangeRate.objects.get_or_create(
                from_currency=from_curr,
                to_currency=to_curr,
                effective_date=today,
                defaults={"rate": rate_val, "source": "INITIAL_SEED"}
            )

        self.stdout.write("  [+] Currencies & initial exchange rates verified (Functional: EGP)")
        return egp, usd, eur, sar

    def setup_account_types(self, force=False):
        """إنشاء وتحديث أنواع الحسابات الأساسية الخمسة"""
        self.stdout.write("[*] Setting up account types...")
        types_data = [
            {"code": "ASSET", "name": "أصول", "category": "asset", "nature": "debit", "level": 1},
            {"code": "LIABILITY", "name": "خصوم", "category": "liability", "nature": "credit", "level": 1},
            {"code": "EQUITY", "name": "حقوق الملكية", "category": "equity", "nature": "credit", "level": 1},
            {"code": "REVENUE", "name": "إيرادات", "category": "revenue", "nature": "credit", "level": 1},
            {"code": "EXPENSE", "name": "مصروفات", "category": "expense", "nature": "debit", "level": 1},
        ]
        res = {}
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
            res[t["code"]] = obj
        self.stdout.write("  [+] 5 Main Account Types verified")
        return res

    def setup_chart_of_accounts(self, account_types, egp, force=False):
        """إنشاء شجرة الحسابات المعيارية الرباعية النقية (105 حساباً)"""
        self.stdout.write("[*] Building Pure 4-Level Master COA Tree...")

        # بيانات الشجرة المعيارية النقية
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
            ("52", "المصروفات البيعية والتسويقية والعمومية", "5", "EXPENSE", 2, False, False, False),
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
            ("52700", "أتعاب واستشارات مهنية ورسوم حكومية", "52", "EXPENSE", 3, True, False, False),
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

        # إنشاء الحسابات بترتيب المستويات لضمان وجود الـ parent أولاً
        account_map = {}
        for code, name, parent_code, type_code, level, is_leaf, is_cash, is_bank in MASTER_TREE:
            parent = account_map.get(parent_code) if parent_code else None
            account_type = account_types[type_code]

            acc, created = ChartOfAccounts.objects.get_or_create(
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
            if not created and force:
                acc.name = name
                acc.parent = parent
                acc.account_type = account_type
                acc.level = level
                acc.is_leaf = is_leaf
                acc.is_cash_account = is_cash
                acc.is_bank_account = is_bank
                acc.save()

            account_map[code] = acc

        self.stdout.write(f"  [+] Pure 4-Level Standard COA verified ({len(account_map)} accounts)")
        return account_map

    def setup_tax_engine(self, account_map, force=False):
        """تهيئة المحرك الضريبي، الهيئات وأكواد الضرائب والربط المحاسبي"""
        self.stdout.write("[*] Setting up Enterprise Tax Determination Engine...")

        # 1. الهيئة الضريبية الافتراضية
        jurisdiction, _ = TaxJurisdiction.objects.get_or_create(
            code="EG-ETA",
            defaults={
                "name": "مصلحة الضرائب المصرية",
                "country": "Egypt",
                "tax_authority": "مصلحة الضرائب المصرية",
                "is_active": True,
            }
        )

        # 2. أكواد الضرائب المعيارية عبر محرك الضرائب الموحد
        from financial.services.tax_service import TaxDeterminationService
        TaxDeterminationService.seed_egyptian_tax_presets()

        vat14 = TaxCode.objects.filter(code="VAT14").first()
        vat14_in = TaxCode.objects.filter(code="VAT14_IN").first()
        wht_codes = TaxCode.objects.filter(code__in=["WHT_01", "WHT_03", "WHT_05"])

        # 3. خرائط ربط الحسابات للضرائب (Tax Account Mapping)
        if vat14:
            # ربط ضريبة مخرجات المبيعات (21310)
            if "21310" in account_map:
                TaxAccountMapping.objects.get_or_create(
                    tax_code=vat14,
                    currency="EGP",
                    tax_nature="OUTPUT",
                    defaults={
                        "output_tax_account": account_map["21310"],
                        "credit_account": account_map["21310"],
                    }
                )
            # ربط ضريبة مدخلات المشتريات (11510)
            if "11510" in account_map:
                TaxAccountMapping.objects.get_or_create(
                    tax_code=vat14,
                    currency="EGP",
                    tax_nature="INPUT",
                    defaults={
                        "input_tax_account": account_map["11510"],
                        "debit_account": account_map["11510"],
                    }
                )

        if vat14_in and "11510" in account_map:
            TaxAccountMapping.objects.get_or_create(
                tax_code=vat14_in,
                currency="EGP",
                tax_nature="INPUT",
                defaults={
                    "input_tax_account": account_map["11510"],
                    "debit_account": account_map["11510"],
                }
            )

        for wht_code in wht_codes:
            # ربط ضريبة الخصم والإضافة (21330)
            if "21330" in account_map:
                TaxAccountMapping.objects.get_or_create(
                    tax_code=wht_code,
                    currency="EGP",
                    tax_nature="WITHHOLDING",
                    defaults={
                        "withholding_tax_account": account_map["21330"],
                        "credit_account": account_map["21330"],
                    }
                )

        # 4. قواعد احتساب الضرائب الافتراضية (Default Tax Rules)
        from financial.models import TaxRule
        if vat14:
            TaxRule.objects.get_or_create(
                code="RUL-VAT-SALE",
                defaults={
                    "name": "قاعدة ضريبة القيمة المضافة العامة على المبيعات 14%",
                    "priority": 10,
                    "rule_scope": "TRANSACTION_TYPE",
                    "scope_value": "SALE",
                    "tax_code": vat14,
                    "jurisdiction": jurisdiction,
                    "is_active": True,
                }
            )
        if vat14_in:
            TaxRule.objects.get_or_create(
                code="RUL-VAT-PURCHASE",
                defaults={
                    "name": "قاعدة ضريبة المدخلات على المشتريات 14%",
                    "priority": 10,
                    "rule_scope": "TRANSACTION_TYPE",
                    "scope_value": "PURCHASE",
                    "tax_code": vat14_in,
                    "jurisdiction": jurisdiction,
                    "is_active": True,
                }
            )

        self.stdout.write("  [+] Standard Egyptian Tax Codes, Rules & Account Mappings verified")

    def setup_cost_centers(self, force=False):
        """إنشاء مركز التكلفة الجذري الافتراضي"""
        self.stdout.write("[*] Setting up Root Cost Center...")
        CostCenter.objects.get_or_create(
            code="CC01",
            defaults={
                "name": "المركز الرئيسي / الإدارة العامة",
                "cost_center_policy": "OPTIONAL",
                "tree_path": "/1/",
                "is_system": True,
                "is_active": True,
            }
        )
        self.stdout.write("  [+] Default Root Cost Center verified (CC01)")

    def setup_financial_categories(self, account_map, force=False):
        """زراعة الـ 8 تصنيفات مالية الشاملة وتصنيفاتها الفرعية ومراكز تكلفة الموارد البشرية"""
        self.stdout.write("[*] Setting up 8 Master Financial Categories & Cost Centers...")

        categories_data = [
            {
                "code": "products",
                "name": "منتجات وبضائع تجارية",
                "description": "إيرادات وتكاليف المنتجات والبضائع والخامات التجارية",
                "revenue_code": "41100",
                "expense_code": "51100",
                "display_order": 1,
                "subcategories": [
                    {"code": "goods", "name": "بضائع تامة الصنع", "order": 1},
                    {"code": "raw_materials", "name": "خامات ومواد أولية", "order": 2},
                    {"code": "spare_parts", "name": "قطع غيار ومستلزمات تشغيل", "order": 3},
                ],
            },
            {
                "code": "services",
                "name": "خدمات وأعمال تشغيلية",
                "description": "إيرادات وتكاليف تقديم الخدمات والتشغيل للغير والاستشارات",
                "revenue_code": "41200",
                "expense_code": "51200",
                "display_order": 2,
                "subcategories": [
                    {"code": "operational_services", "name": "خدمات تشغيلية وتنفيذية", "order": 1},
                    {"code": "maintenance_support", "name": "خدمات صيانة ودعم فني", "order": 2},
                    {"code": "consulting", "name": "استشارات وخدمات مهنية", "order": 3},
                ],
            },
            {
                "code": "refunds",
                "name": "مردودات ومسموحات وخصومات",
                "description": "مردودات ومسموحات المبيعات والخصومات الممنوحة للعملاء",
                "revenue_code": "41910",
                "expense_code": None,
                "display_order": 3,
                "subcategories": [
                    {"code": "sales_returns", "name": "مردودات مبيعات", "order": 1},
                    {"code": "sales_allowances", "name": "مسموحات وخصومات مبيعات", "order": 2},
                ],
            },
            {
                "code": "other_revenue",
                "name": "إيرادات متنوعة وأخرى",
                "description": "إيرادات تشغيلية وأرباح بيع أصول ومخلفات وإيرادات متنوعة",
                "revenue_code": "49110",
                "expense_code": None,
                "display_order": 4,
                "subcategories": [
                    {"code": "scrap_sales", "name": "مبيعات عوادم ومخلفات", "order": 1},
                    {"code": "misc_revenue", "name": "إيرادات متنوعة وأخرى", "order": 2},
                ],
            },
            {
                "code": "payroll_hr",
                "name": "رواتب وأجور ومستحقات العاملين",
                "description": "الرواتب والأجور والبدلات والتأمينات ومراكز تكلفة أقسام الموارد البشرية",
                "revenue_code": None,
                "expense_code": "52100",
                "display_order": 5,
                "subcategories": [
                    {"code": "hr_management", "name": "رواتب الإدارة العامة", "order": 1},
                    {"code": "hr_sales", "name": "رواتب المبيعات والتسويق", "order": 2},
                    {"code": "hr_operations", "name": "رواتب التشغيل والإنتاج", "order": 3},
                    {"code": "hr_finance", "name": "رواتب الإدارة المالية والمخازن", "order": 4},
                    {"code": "hr_insurance", "name": "تأمينات اجتماعية - حصة المنشأة", "order": 5},
                ],
            },
            {
                "code": "taxes_government",
                "name": "ضرائب ورسوم وتراخيص حكومية",
                "description": "المصروفات والرسوم الحكومية والتراخيص والضرائب المستحقة",
                "revenue_code": None,
                "expense_code": "52700",
                "display_order": 6,
                "subcategories": [
                    {"code": "vat_settlement", "name": "تسويات ضريبة القيمة المضافة", "order": 1},
                    {"code": "payroll_tax", "name": "ضريبة كسب العمل والرواتب", "order": 2},
                    {"code": "withholding_tax", "name": "ضرائب خصم وتحصيل", "order": 3},
                    {"code": "govt_fees", "name": "رسوم وتراخيص واشتراكات حكومية", "order": 4},
                ],
            },
            {
                "code": "selling_expenses",
                "name": "مصروفات بيعية وتسويقية",
                "description": "تكاليف الحملات الإعلانية والتسويق وعمولات البيع وشحن وتوزيع البضائع",
                "revenue_code": None,
                "expense_code": "52900",
                "display_order": 7,
                "subcategories": [
                    {"code": "marketing_advertising", "name": "دعاية وإعلان وترويج", "order": 1},
                    {"code": "shipping_delivery", "name": "شحن ونقل وتوزيع للعملاء", "order": 2},
                ],
            },
            {
                "code": "admin_expenses",
                "name": "مصروفات عمومية وإدارية",
                "description": "الإيجارات والمرافق والأدوات المكتبية والضيافة والصيانة العامة",
                "revenue_code": None,
                "expense_code": "52300",
                "display_order": 8,
                "subcategories": [
                    {"code": "rent_utilities", "name": "إيجارات ومرافق وخدمات", "order": 1},
                    {"code": "office_supplies", "name": "أدوات ومستلزمات مكتبية", "order": 2},
                    {"code": "hospitality", "name": "ضيافة ونظافة وصيانة عامة", "order": 3},
                ],
            },
        ]

        for cat_data in categories_data:
            rev_acc = account_map.get(cat_data["revenue_code"]) if cat_data["revenue_code"] else None
            exp_acc = account_map.get(cat_data["expense_code"]) if cat_data["expense_code"] else None

            cat_obj, created = FinancialCategory.objects.get_or_create(
                code=cat_data["code"],
                defaults={
                    "name": cat_data["name"],
                    "description": cat_data["description"],
                    "default_revenue_account": rev_acc,
                    "default_expense_account": exp_acc,
                    "display_order": cat_data["display_order"],
                    "is_active": True,
                }
            )
            if not created and force:
                cat_obj.name = cat_data["name"]
                cat_obj.description = cat_data["description"]
                cat_obj.default_revenue_account = rev_acc
                cat_obj.default_expense_account = exp_acc
                cat_obj.display_order = cat_data["display_order"]
                cat_obj.save()

            # زراعة التصنيفات الفرعية
            for sub in cat_data.get("subcategories", []):
                FinancialSubcategory.objects.get_or_create(
                    parent_category=cat_obj,
                    code=sub["code"],
                    defaults={
                        "name": sub["name"],
                        "display_order": sub["order"],
                        "is_active": True,
                    }
                )

        self.stdout.write(f"  [+] 8 Master Financial Categories & HR Cost Centers verified")

    def setup_fiscal_structure(self, year):
        """إنشاء السنة المالية والفترات المحاسبية الـ 12"""
        self.stdout.write(f"[*] Setting up Fiscal Year and 12 Periods for {year}...")
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        fy, created = FiscalYear.objects.get_or_create(
            year_code=f"FY{year}",
            defaults={
                "name": f"السنة المالية {year}",
                "start_date": start_date,
                "end_date": end_date,
                "status": "open",
            }
        )

        # إنشاء فترات الشهور الـ 12
        for month in range(1, 13):
            m_start = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            m_end = date(year, month, last_day)

            AccountingPeriod.objects.get_or_create(
                fiscal_year=fy,
                period_number=month,
                defaults={
                    "name": f"فترة {month:02d}/{year}",
                    "start_date": m_start,
                    "end_date": m_end,
                    "status": "open",
                }
            )

        self.stdout.write(f"  [+] Fiscal Year FY{year} and 12 Monthly Periods verified (Status: OPEN)")
