"""أمر بذر البيانات الافتراضية لإعدادات العملاء والشرائح وشروط السداد"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from customer.models import CustomerTier, PaymentTerm, CustomerGeneralSettings


class Command(BaseCommand):
    help = "بذر الشرائح التجارية وشروط السداد والإعدادات الافتراضية للعملاء"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("بدء بذر بيانات إعدادات العملاء..."))

        # 1. بذر إعدادات العملاء العامة
        settings = CustomerGeneralSettings.get_settings()
        settings.code_prefix = "CUST-"
        settings.code_digits = 4
        settings.default_credit_limit = Decimal("0.00")
        settings.default_grace_period_days = 0
        settings.credit_limit_enforcement = "WARN"
        settings.save()
        self.stdout.write(self.style.SUCCESS("[OK] تم تحديث إعدادات العملاء العامة والترقيم التلقائي."))

        # 2. بذر شروط السداد (Payment Terms)
        terms_data = [
            {
                "name": "سداد فوري (نقداً)",
                "code": "CASH",
                "days": 0,
                "discount_percentage": Decimal("0.00"),
                "discount_days": 0,
                "is_default": True,
                "is_active": True,
            },
            {
                "name": "آجل 15 يوماً",
                "code": "NET15",
                "days": 15,
                "discount_percentage": Decimal("0.00"),
                "discount_days": 0,
                "is_default": False,
                "is_active": True,
            },
            {
                "name": "آجل 30 يوماً",
                "code": "NET30",
                "days": 30,
                "discount_percentage": Decimal("0.00"),
                "discount_days": 0,
                "is_default": False,
                "is_active": True,
            },
            {
                "name": "آجل 60 يوماً",
                "code": "NET60",
                "days": 60,
                "discount_percentage": Decimal("0.00"),
                "discount_days": 0,
                "is_default": False,
                "is_active": True,
            },
            {
                "name": "دفعة مقدمة 50% والباقي عند التسليم",
                "code": "ADV50_DEL",
                "days": 0,
                "discount_percentage": Decimal("0.00"),
                "discount_days": 0,
                "is_default": False,
                "is_active": True,
            },
            {
                "name": "آجل 30 يوم (خصم 2% سداد خلال 10 أيام)",
                "code": "EARLY2_10",
                "days": 30,
                "discount_percentage": Decimal("2.00"),
                "discount_days": 10,
                "is_default": False,
                "is_active": True,
            },
        ]

        payment_terms_map = {}
        for t_data in terms_data:
            term, created = PaymentTerm.objects.update_or_create(
                name=t_data["name"],
                defaults=t_data,
            )
            payment_terms_map[t_data["name"]] = term
            action_text = "تم إنشاء" if created else "تم تحديث"
            self.stdout.write(f"  {action_text} شرط السداد: {term.name}")

        # 3. بذر الشرائح التجارية (Customer Tiers)
        tiers_data = [
            {
                "name": "شركات ومؤسسات كبرى",
                "code": "B2B_CORP",
                "description": "الشركات الكبرى والمصانع ذات التعاقدات السنوية وحجم السحب المرتفع.",
                "icon": "fas fa-building",
                "color": "primary",
                "display_order": 1,
                "default_payment_term": payment_terms_map.get("آجل 30 يوماً"),
                "default_credit_limit": Decimal("100000.00"),
                "default_risk_category": "low",
                "discount_percentage": Decimal("0.00"),
                "is_active": True,
                "is_system": True,
            },
            {
                "name": "وكالات الدعاية والإعلان",
                "code": "AGENCY",
                "description": "الوكالات الإعلانية ومصممو الجرافيك ومكاتب التسويق.",
                "icon": "fas fa-ad",
                "color": "info",
                "display_order": 2,
                "default_payment_term": payment_terms_map.get("دفعة مقدمة 50% والباقي عند التسليم"),
                "default_credit_limit": Decimal("50000.00"),
                "default_risk_category": "medium",
                "discount_percentage": Decimal("10.00"),
                "is_active": True,
                "is_system": True,
            },
            {
                "name": "مطابع ومكاتب شريكة",
                "code": "PRINT_PARTNER",
                "description": "المطابع الزميلة وورش خدمات الطباعة وما بعد الطباعة (B2B Trade).",
                "icon": "fas fa-print",
                "color": "warning",
                "display_order": 3,
                "default_payment_term": payment_terms_map.get("آجل 15 يوماً"),
                "default_credit_limit": Decimal("30000.00"),
                "default_risk_category": "medium",
                "discount_percentage": Decimal("15.00"),
                "is_active": True,
                "is_system": True,
            },
            {
                "name": "عملاء التجزئة والأفراد",
                "code": "B2C_RETAIL",
                "description": "العملاء المباشرون والطلبات النقدية الفردية السريعة.",
                "icon": "fas fa-user-tag",
                "color": "secondary",
                "display_order": 4,
                "default_payment_term": payment_terms_map.get("سداد فوري (نقداً)"),
                "default_credit_limit": Decimal("0.00"),
                "default_risk_category": "low",
                "discount_percentage": Decimal("0.00"),
                "is_active": True,
                "is_system": True,
            },
            {
                "name": "كبار العملاء (VIP)",
                "code": "VIP_CLIENTS",
                "description": "العملاء الاستراتيجيون ذوو الأولوية القصوى والتسهيلات الائتمانية الخاصة.",
                "icon": "fas fa-crown",
                "color": "danger",
                "display_order": 5,
                "default_payment_term": payment_terms_map.get("آجل 60 يوماً"),
                "default_credit_limit": Decimal("200000.00"),
                "default_risk_category": "low",
                "discount_percentage": Decimal("5.00"),
                "is_active": True,
                "is_system": True,
            },
        ]

        for tier_data in tiers_data:
            tier, created = CustomerTier.objects.update_or_create(
                code=tier_data["code"],
                defaults=tier_data,
            )
            action_text = "تم إنشاء" if created else "تم تحديث"
            self.stdout.write(f"  {action_text} الشريحة: {tier.name} ({tier.code})")

        self.stdout.write(self.style.SUCCESS("[OK] اكتمل بذر إعدادات العملاء والشرائح وشروط السداد بنجاح!"))
