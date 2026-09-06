# -*- coding: utf-8 -*-
"""
Management Command: seed_erp_mock_data
Populate comprehensive, enterprise-grade mock data for Printing Suppliers, Services, and Paper.
Fully simulates real user interactions, domain services, signals, and accounting integrations.
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from supplier.models import Supplier, SupplierType, ServiceType, SupplierService
from customer.models import PaymentTerm
from financial.models import Currency, TaxCode
from financial.services.subledger_account_service import SubledgerAccountService
from product.models import Category, Product, Unit, Warehouse
from product.services.inventory_service import InventoryService
from printing_pricing.models import (
    PrintingMachine,
    MachineDimension,
    PaperType,
    PaperSize,
    PaperOrigin,
    PaperWeight,
    CoatingType,
    FinishingType,
    PackagingType,
)


class Command(BaseCommand):
    help = "إضافة بيانات تجريبية متكاملة للموردين والخدمات والورق مع تفعيل كافة الخدمات والإشارات المحاسبية والمخزنية"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== بدء تهيئة البيانات التجريبية للموردين والخدمات والورق ==="))

        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        functional_currency = Currency.objects.filter(is_functional=True).first() or Currency.objects.get_or_create(
            code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
        )[0]
        vat_tax = TaxCode.objects.filter(rate=Decimal("14.00"), is_active=True).first()

        # 1. شروط السداد
        terms = {
            "CASH": PaymentTerm.objects.get_or_create(code="CASH", defaults={"name": "سداد فوري (نقدي)", "days": 0, "is_active": True})[0],
            "NET15": PaymentTerm.objects.get_or_create(code="NET15", defaults={"name": "سداد خلال 15 يوماً", "days": 15, "is_active": True})[0],
            "NET30": PaymentTerm.objects.get_or_create(code="NET30", defaults={"name": "سداد خلال 30 يوماً", "days": 30, "is_active": True})[0],
            "NET60": PaymentTerm.objects.get_or_create(code="NET60", defaults={"name": "سداد خلال 60 يوماً", "days": 60, "is_active": True})[0],
        }

        # 2. وحدات القياس
        unit_service, _ = Unit.objects.get_or_create(name="خدمة", defaults={"name_en": "Service", "symbol": "خدمة", "is_active": True})
        unit_sheet = Unit.objects.filter(name__icontains="فرخ").first() or Unit.objects.get_or_create(
            name="فرخ", defaults={"name_en": "Sheet", "symbol": "فرخ", "is_active": True}
        )[0]
        unit_piece = Unit.objects.filter(name__icontains="قطعة").first() or Unit.objects.get_or_create(
            name="قطعة", defaults={"name_en": "Piece", "symbol": "قطعة", "is_active": True}
        )[0]
        unit_thousand, _ = Unit.objects.get_or_create(name="ألف فرخ / نسخة", defaults={"name_en": "Thousand", "symbol": "ألف", "is_active": True})

        # 3. المخزن الرئيسي
        main_warehouse = Warehouse.objects.filter(is_active=True).first()
        if not main_warehouse:
            main_warehouse = Warehouse.objects.create(
                name="المخزن الرئيسي",
                code="WH0001",
                is_active=True,
                created_by=user
            )

        # 4. تصنيفات المنتجات والخدمات
        cat_paper, _ = Category.objects.get_or_create(
            name="ورق",
            defaults={"name_en": "Paper", "code": "PAP", "description": "خامات وأفرخ الورق والكارتون", "is_active": True}
        )
        cat_services_root, _ = Category.objects.get_or_create(
            name="خدمات طباعة وإنتاج",
            defaults={"name_en": "Printing & Production Services", "code": "SRV", "description": "كافة خدمات الطباعة والتشطيب والتجهيز", "is_active": True}
        )
        cat_services_pre, _ = Category.objects.get_or_create(
            name="خدمات ما قبل الطباعة والتجهيز",
            defaults={"name_en": "Prepress Services", "code": "SRV-PRE", "parent": cat_services_root, "is_active": True}
        )
        cat_services_press, _ = Category.objects.get_or_create(
            name="خدمات الطباعة والتشغيل",
            defaults={"name_en": "Press Services", "code": "SRV-PRS", "parent": cat_services_root, "is_active": True}
        )
        cat_services_post, _ = Category.objects.get_or_create(
            name="خدمات ما بعد الطباعة والتشطيب",
            defaults={"name_en": "Postpress & Finishing Services", "code": "SRV-PST", "parent": cat_services_root, "is_active": True}
        )

        # 5. استرجاع بيانات موديول التسعير المرجعية
        sm74 = PrintingMachine.objects.filter(name__icontains="SM 74").first()
        cd102 = PrintingMachine.objects.filter(name__icontains="CD 102").first()
        xerox = PrintingMachine.objects.filter(name__icontains="زيروكس").first()
        canon = PrintingMachine.objects.filter(name__icontains="كانون").first()

        dim_half = MachineDimension.objects.filter(code="half_sheet").first()
        dim_full = MachineDimension.objects.filter(code="full_sheet").first()
        dim_a3 = MachineDimension.objects.filter(code="digital_a3").first()
        plate_sm74 = MachineDimension.objects.filter(code="plate_sm74").first()
        plate_cd102 = MachineDimension.objects.filter(code="plate_cd102").first()

        paper_type_csh = PaperType.objects.filter(name__icontains="كوشيه").first()
        paper_type_off = PaperType.objects.filter(name__icontains="طبع").first()
        paper_type_brs = PaperType.objects.filter(name__icontains="بريستول").first()
        paper_type_dpl = PaperType.objects.filter(name__icontains="دوبلكس").first()

        paper_size_full = PaperSize.objects.filter(name__icontains="فرخ كامل").first()
        paper_size_jayir = PaperSize.objects.filter(name__icontains="جاير").first()

        origin_id = PaperOrigin.objects.filter(name__icontains="إندونيسي").first() or PaperOrigin.objects.first()
        origin_eg = PaperOrigin.objects.filter(name__icontains="مصري").first() or PaperOrigin.objects.first()

        coat_gloss = CoatingType.objects.filter(name__icontains="لامع").first()
        coat_matt = CoatingType.objects.filter(name__icontains="مط").first()
        coat_uv = CoatingType.objects.filter(name__icontains="ورنيش").first()

        finish_cut = FinishingType.objects.filter(name__icontains="تكسير").first() or FinishingType.objects.first()
        finish_crease = FinishingType.objects.filter(name__icontains="ريجة").first()
        pack_wire = PackagingType.objects.filter(name__icontains="سلك").first()
        pack_staple = PackagingType.objects.filter(name__icontains="تدبيس").first()

        # أنواع الخدمات المتاحة
        st_offset = ServiceType.objects.filter(code="offset_printing").first()
        st_digital = ServiceType.objects.filter(code="digital_printing").first()
        st_ctp = ServiceType.objects.filter(code="ctp_plates").first()
        st_paper = ServiceType.objects.filter(code="paper").first()
        st_finishing = ServiceType.objects.filter(code="finishing").first()
        st_coating = ServiceType.objects.filter(code="coating").first()
        st_packaging = ServiceType.objects.filter(code="packaging").first()

        with transaction.atomic():
            # =========================================================================
            # المرحلة الأولى: إنشاء الموردين وربط الحسابات المحاسبية والخدمات المعتمدة
            # =========================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n1. جاري إنشاء وتحديث الموردين المعتمدين..."))

            suppliers_manifest = [
                {
                    "code": "SUP010",
                    "name": "مطبعة الأهرام التجارية للأوفست",
                    "entity_type": "company",
                    "primary_type_code": "offset_press",
                    "tax_number": "301-452-987",
                    "commercial_registry": "104520",
                    "phone": "01012345678",
                    "email": "ahram.press@example.com",
                    "city": "6 أكتوبر",
                    "address": "المنطقة الصناعية الرابعة، 6 أكتوبر، الجيزة",
                    "contact_person": "م/ عصام عبد الشافي",
                    "credit_limit": Decimal("100000.00"),
                    "default_payment_term": terms["NET30"],
                    "grace_period_days": 5,
                    "is_pricing_supplier": True,
                    "is_preferred": True,
                    "provided_services": [st_offset, st_ctp],
                    "supplier_services": [
                        {
                            "name": "هايدلبرج Speedmaster SM 74 — 4 لون (50×70)",
                            "service_type": st_offset,
                            "machine": sm74,
                            "dimension": dim_half,
                            "pricing_formula": "PER_THOUSAND",
                            "base_price": Decimal("45.00"),
                            "setup_cost": Decimal("100.00"),
                            "minimum_charge": Decimal("200.00"),
                        },
                        {
                            "name": "هايدلبرج Speedmaster CD 102 — 4 لون (70×100)",
                            "service_type": st_offset,
                            "machine": cd102,
                            "dimension": dim_full,
                            "pricing_formula": "PER_THOUSAND",
                            "base_price": Decimal("75.00"),
                            "setup_cost": Decimal("150.00"),
                            "minimum_charge": Decimal("300.00"),
                        },
                        {
                            "name": "زنكات CTP نصف فرخ (50×70) حراري",
                            "service_type": st_ctp,
                            "plate_size": plate_sm74,
                            "pricing_formula": "PER_PIECE",
                            "base_price": Decimal("40.00"),
                            "set_price": Decimal("160.00"),
                        },
                        {
                            "name": "زنكات CTP فرخ كامل (70×100) حراري",
                            "service_type": st_ctp,
                            "plate_size": plate_cd102,
                            "pricing_formula": "PER_PIECE",
                            "base_price": Decimal("70.00"),
                            "set_price": Decimal("280.00"),
                        },
                    ]
                },
                {
                    "code": "SUP011",
                    "name": "مركز ألفا للطباعة الرقمية (ديجيتال)",
                    "entity_type": "company",
                    "primary_type_code": "digital_center",
                    "tax_number": "215-632-114",
                    "commercial_registry": "88412",
                    "phone": "01223456789",
                    "email": "alpha.digital@example.com",
                    "city": "القاهرة",
                    "address": "شارع الفلكي، باب اللوق، وسط البلد، القاهرة",
                    "contact_person": "أ/ كريم منصور",
                    "credit_limit": Decimal("25000.00"),
                    "default_payment_term": terms["CASH"],
                    "grace_period_days": 0,
                    "is_pricing_supplier": True,
                    "is_preferred": True,
                    "provided_services": [st_digital],
                    "supplier_services": [
                        {
                            "name": "طباعة ديجيتال ليزر A3 ملون (Xerox Versant)",
                            "service_type": st_digital,
                            "machine": xerox,
                            "dimension": dim_a3,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("3.50"),
                            "price_per_click_color": Decimal("3.500"),
                            "minimum_charge": Decimal("50.00"),
                        },
                        {
                            "name": "طباعة ديجيتال ليزر A3 أبيض وأسود (Canon)",
                            "service_type": st_digital,
                            "machine": canon,
                            "dimension": dim_a3,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("1.00"),
                            "price_per_click_bw": Decimal("1.000"),
                            "minimum_charge": Decimal("30.00"),
                        },
                    ]
                },
                {
                    "code": "SUP012",
                    "name": "مخازن الهدى لتجارة واستيراد الورق",
                    "entity_type": "company",
                    "primary_type_code": "paper_supplier",
                    "tax_number": "412-856-321",
                    "commercial_registry": "95412",
                    "phone": "01134567890",
                    "email": "elhoda.paper@example.com",
                    "city": "القاهرة",
                    "address": "شارع الجيش، العتبة، القاهرة",
                    "contact_person": "الحاج رجب الهدى",
                    "credit_limit": Decimal("250000.00"),
                    "default_payment_term": terms["NET15"],
                    "grace_period_days": 3,
                    "is_pricing_supplier": True,
                    "is_preferred": True,
                    "provided_services": [st_paper],
                    "supplier_services": [
                        {
                            "name": "ورق كوشيه إندونيسي 150 جم (70×100)",
                            "service_type": st_paper,
                            "paper_type_ref": paper_type_csh,
                            "paper_size": paper_size_full,
                            "paper_origin": origin_id,
                            "gsm": 150,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("2.80"),
                            "price_per_ton": Decimal("55000.00"),
                        },
                        {
                            "name": "ورق كوشيه إندونيسي 300 جم (70×100)",
                            "service_type": st_paper,
                            "paper_type_ref": paper_type_csh,
                            "paper_size": paper_size_full,
                            "paper_origin": origin_id,
                            "gsm": 300,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("5.50"),
                            "price_per_ton": Decimal("55000.00"),
                        },
                        {
                            "name": "ورق طبع أبيض مصري 70 جم (70×100)",
                            "service_type": st_paper,
                            "paper_type_ref": paper_type_off,
                            "paper_size": paper_size_full,
                            "paper_origin": origin_eg,
                            "gsm": 70,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("1.40"),
                            "price_per_ton": Decimal("42000.00"),
                        },
                        {
                            "name": "ورق طبع أبيض مصري 80 جم (70×100)",
                            "service_type": st_paper,
                            "paper_type_ref": paper_type_off,
                            "paper_size": paper_size_full,
                            "paper_origin": origin_eg,
                            "gsm": 80,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("1.60"),
                            "price_per_ton": Decimal("42000.00"),
                        },
                        {
                            "name": "ورق بريستول كرتون 300 جم (70×100)",
                            "service_type": st_paper,
                            "paper_type_ref": paper_type_brs,
                            "paper_size": paper_size_full,
                            "paper_origin": origin_eg,
                            "gsm": 300,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("6.00"),
                            "price_per_ton": Decimal("60000.00"),
                        },
                        {
                            "name": "ورق دوبلكس ظهر رمادي 300 جم (70×100)",
                            "service_type": st_paper,
                            "paper_type_ref": paper_type_dpl,
                            "paper_size": paper_size_full,
                            "paper_origin": origin_eg,
                            "gsm": 300,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("4.80"),
                            "price_per_ton": Decimal("48000.00"),
                        },
                    ]
                },
                {
                    "code": "SUP013",
                    "name": "ورشة الإتقان للتشطيب والتجليد والسلوفان",
                    "entity_type": "company",
                    "primary_type_code": "finishing_workshop",
                    "tax_number": "189-543-712",
                    "commercial_registry": "67321",
                    "phone": "01543210987",
                    "email": "etqan.finishing@example.com",
                    "city": "القاهرة",
                    "address": "شارع محمد علي، القلعة، القاهرة",
                    "contact_person": "الأسطى حسن الجلاد",
                    "credit_limit": Decimal("50000.00"),
                    "default_payment_term": terms["NET15"],
                    "grace_period_days": 3,
                    "is_pricing_supplier": True,
                    "is_preferred": True,
                    "provided_services": [st_finishing, st_coating, st_packaging],
                    "supplier_services": [
                        {
                            "name": "سلوفان حراري لامع وجه واحد",
                            "service_type": st_coating,
                            "coating_type": coat_gloss,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("0.45"),
                            "minimum_charge": Decimal("100.00"),
                        },
                        {
                            "name": "سلوفان حراري مط وجه واحد",
                            "service_type": st_coating,
                            "coating_type": coat_matt,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("0.55"),
                            "minimum_charge": Decimal("120.00"),
                        },
                        {
                            "name": "ورنيش UV سبوت موضعي",
                            "service_type": st_coating,
                            "coating_type": coat_uv,
                            "pricing_formula": "PER_SHEET",
                            "base_price": Decimal("1.20"),
                            "minimum_charge": Decimal("250.00"),
                        },
                        {
                            "name": "فورمة تكسير وريجة داي كت للعلب",
                            "service_type": st_finishing,
                            "finishing_type": finish_cut,
                            "pricing_formula": "PER_THOUSAND",
                            "base_price": Decimal("25.00"),
                            "tooling_cost": Decimal("150.00"),
                            "minimum_charge": Decimal("150.00"),
                        },
                        {
                            "name": "تجليد سلك معدني Wire-O للدفاتر",
                            "service_type": st_packaging,
                            "packaging_type": pack_wire,
                            "pricing_formula": "PER_PIECE",
                            "base_price": Decimal("2.50"),
                            "minimum_charge": Decimal("100.00"),
                        },
                        {
                            "name": "تدبيس حصان للمجلات والبروشورات",
                            "service_type": st_packaging,
                            "packaging_type": pack_staple,
                            "pricing_formula": "PER_PIECE",
                            "base_price": Decimal("0.15"),
                            "minimum_charge": Decimal("50.00"),
                        },
                    ]
                },
                {
                    "code": "SUP014",
                    "name": "مكتب النيل لفصل الألوان وزنكات CTP",
                    "entity_type": "company",
                    "primary_type_code": "ctp_center",
                    "tax_number": "654-321-987",
                    "commercial_registry": "78912",
                    "phone": "01278901234",
                    "email": "nile.ctp@example.com",
                    "city": "القاهرة",
                    "address": "ميدان العباسية، القاهرة",
                    "contact_person": "م/ طارق فهمي",
                    "credit_limit": Decimal("30000.00"),
                    "default_payment_term": terms["CASH"],
                    "grace_period_days": 0,
                    "is_pricing_supplier": True,
                    "is_preferred": True,
                    "provided_services": [st_ctp],
                    "supplier_services": [
                        {
                            "name": "إخراج زنكات CTP مقاس 50×70 (SM 74)",
                            "service_type": st_ctp,
                            "plate_size": plate_sm74,
                            "pricing_formula": "PER_PIECE",
                            "base_price": Decimal("35.00"),
                            "set_price": Decimal("140.00"),
                        },
                        {
                            "name": "إخراج زنكات CTP مقاس 70×100 (CD 102)",
                            "service_type": st_ctp,
                            "plate_size": plate_cd102,
                            "pricing_formula": "PER_PIECE",
                            "base_price": Decimal("65.00"),
                            "set_price": Decimal("260.00"),
                        },
                    ]
                },
                {
                    "code": "SUP015",
                    "name": "مروان الدسوقي للخدمات اللوجستية والنقل",
                    "entity_type": "individual",
                    "primary_type_code": "service_provider",
                    "national_id": "29005150101234",  # 14 digits valid Egyptian National ID
                    "phone": "01065432198",
                    "email": "marwan.delivery@example.com",
                    "city": "القليوبية",
                    "address": "طريق مصر إسكندرية الزراعي، قليوب",
                    "contact_person": "مروان الدسوقي",
                    "credit_limit": Decimal("15000.00"),
                    "default_payment_term": terms["CASH"],
                    "grace_period_days": 0,
                    "is_pricing_supplier": False,
                    "provided_services": [],
                    "supplier_services": []
                }
            ]

            saved_suppliers = {}
            for s_data in suppliers_manifest:
                primary_type = SupplierType.objects.filter(code=s_data["primary_type_code"]).first()
                if not primary_type:
                    primary_type, _ = SupplierType.objects.get_or_create(
                        code=s_data["primary_type_code"],
                        defaults={"name": s_data["primary_type_code"], "is_active": True}
                    )

                supplier, created = Supplier.objects.update_or_create(
                    code=s_data["code"],
                    defaults={
                        "name": s_data["name"],
                        "entity_type": s_data["entity_type"],
                        "primary_type": primary_type,
                        "tax_number": s_data.get("tax_number"),
                        "commercial_registry": s_data.get("commercial_registry"),
                        "national_id": s_data.get("national_id"),
                        "phone": s_data["phone"],
                        "email": s_data.get("email"),
                        "country": "مصر",
                        "city": s_data["city"],
                        "address": s_data["address"],
                        "contact_person": s_data.get("contact_person"),
                        "credit_limit": s_data["credit_limit"],
                        "default_payment_term": s_data["default_payment_term"],
                        "payment_terms": s_data["default_payment_term"].name if s_data["default_payment_term"] else "",
                        "grace_period_days": s_data["grace_period_days"],
                        "default_currency": functional_currency,
                        "is_pricing_supplier": s_data["is_pricing_supplier"],
                        "is_active": True,
                        "created_by": user,
                    }
                )

                # ربط الحساب المالي للمورد إذا لم ينشأ تلقائياً بالسيجنال
                if not supplier.financial_account:
                    account = SubledgerAccountService.create_supplier_account(supplier=supplier, user=user)
                    if account:
                        Supplier.objects.filter(pk=supplier.pk).update(financial_account=account)
                        supplier.financial_account = account
                else:
                    supplier.financial_account.name = f"{supplier.name} - {supplier.code}"
                    supplier.financial_account.save(update_fields=["name"])

                # ربط الخدمات المعتمدة
                valid_services = [s for s in s_data.get("provided_services", []) if s is not None]
                if valid_services:
                    supplier.provided_services.set(valid_services)

                # إنشاء خدمات المورد في موديول التسعير
                for s_svc in s_data.get("supplier_services", []):
                    if not s_svc.get("service_type"):
                        continue
                    SupplierService.objects.update_or_create(
                        supplier=supplier,
                        name=s_svc["name"],
                        defaults={
                            "service_type": s_svc["service_type"],
                            "machine": s_svc.get("machine"),
                            "dimension": s_svc.get("dimension"),
                            "plate_size": s_svc.get("plate_size"),
                            "paper_type_ref": s_svc.get("paper_type_ref"),
                            "paper_size": s_svc.get("paper_size"),
                            "paper_origin": s_svc.get("paper_origin"),
                            "gsm": s_svc.get("gsm"),
                            "coating_type": s_svc.get("coating_type"),
                            "finishing_type": s_svc.get("finishing_type"),
                            "packaging_type": s_svc.get("packaging_type"),
                            "pricing_formula": s_svc.get("pricing_formula", "PER_PIECE"),
                            "base_price": s_svc.get("base_price", Decimal("0.00")),
                            "setup_cost": s_svc.get("setup_cost", Decimal("0.00")),
                            "tooling_cost": s_svc.get("tooling_cost", Decimal("0.00")),
                            "set_price": s_svc.get("set_price"),
                            "minimum_charge": s_svc.get("minimum_charge", Decimal("0.00")),
                            "price_per_ton": s_svc.get("price_per_ton"),
                            "price_per_click_color": s_svc.get("price_per_click_color"),
                            "price_per_click_bw": s_svc.get("price_per_click_bw"),
                            "currency": functional_currency,
                            "is_active": True,
                        }
                    )

                saved_suppliers[supplier.code] = supplier
                acc_code = supplier.financial_account.code if supplier.financial_account else "غير مربوط"
                self.stdout.write(self.style.SUCCESS(f"  ✓ تم حفظ المورد: {supplier.name} ({supplier.code}) | الحساب المحاسبي: {acc_code}"))

            # =========================================================================
            # المرحلة الثانية: إضافة الخدمات القياسية بالنظام (is_service=True)
            # =========================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n2. جاري إضافة خدمات الطباعة والتجهيز القياسية بالنظام..."))

            services_manifest = [
                {
                    "sku": "SRV-OFF-5070",
                    "name": "خدمة طباعة أوفست 4 لون (50×70)",
                    "name_en": "Offset Printing 4 Colors 50x70",
                    "category": cat_services_press,
                    "unit": unit_service,
                    "cost_price": Decimal("45.00"),
                    "selling_price": Decimal("65.00"),
                    "default_supplier": saved_suppliers.get("SUP010"),
                    "description": "طباعة أوفست 4 ألوان على ماكينة نصف فرخ هايدلبرج SM 74",
                },
                {
                    "sku": "SRV-OFF-70100",
                    "name": "خدمة طباعة أوفست 4 لون (70×100)",
                    "name_en": "Offset Printing 4 Colors 70x100",
                    "category": cat_services_press,
                    "unit": unit_service,
                    "cost_price": Decimal("75.00"),
                    "selling_price": Decimal("110.00"),
                    "default_supplier": saved_suppliers.get("SUP010"),
                    "description": "طباعة أوفست 4 ألوان على ماكينة فرخ كامل هايدلبرج CD 102",
                },
                {
                    "sku": "SRV-DIG-A3C",
                    "name": "خدمة طباعة ديجيتال ليزر A3 ملون",
                    "name_en": "Digital Color Laser Print A3",
                    "category": cat_services_press,
                    "unit": unit_service,
                    "cost_price": Decimal("3.50"),
                    "selling_price": Decimal("6.00"),
                    "default_supplier": saved_suppliers.get("SUP011"),
                    "description": "طباعة رقمية ليزر فائقة الدقة وجه واحد مقاس A3 / A3+",
                },
                {
                    "sku": "SRV-CTP-5070",
                    "name": "خدمة إخراج زنكات CTP نصف فرخ (50×70)",
                    "name_en": "CTP Plates Output 50x70",
                    "category": cat_services_pre,
                    "unit": unit_piece,
                    "cost_price": Decimal("35.00"),
                    "selling_price": Decimal("50.00"),
                    "default_supplier": saved_suppliers.get("SUP014"),
                    "description": "زنكة ألومنيوم حرارية عالية الحساسية مقاس ماكينات نصف فرخ",
                },
                {
                    "sku": "SRV-CTP-70100",
                    "name": "خدمة إخراج زنكات CTP فرخ كامل (70×100)",
                    "name_en": "CTP Plates Output 70x100",
                    "category": cat_services_pre,
                    "unit": unit_piece,
                    "cost_price": Decimal("65.00"),
                    "selling_price": Decimal("90.00"),
                    "default_supplier": saved_suppliers.get("SUP014"),
                    "description": "زنكة ألومنيوم حرارية عالية الحساسية مقاس ماكينات فرخ كامل",
                },
                {
                    "sku": "SRV-LAM-GLOSS",
                    "name": "خدمة سلوفان حراري لامع",
                    "name_en": "Thermal Gloss Lamination",
                    "category": cat_services_post,
                    "unit": unit_sheet,
                    "cost_price": Decimal("0.45"),
                    "selling_price": Decimal("0.75"),
                    "default_supplier": saved_suppliers.get("SUP013"),
                    "description": "تغطية سلوفان حراري براق للمطبوعات وجه واحد",
                },
                {
                    "sku": "SRV-LAM-MATT",
                    "name": "خدمة سلوفان حراري مط",
                    "name_en": "Thermal Matt Lamination",
                    "category": cat_services_post,
                    "unit": unit_sheet,
                    "cost_price": Decimal("0.55"),
                    "selling_price": Decimal("0.90"),
                    "default_supplier": saved_suppliers.get("SUP013"),
                    "description": "تغطية سلوفان حراري مطفي راقي للمطبوعات وجه واحد",
                },
                {
                    "sku": "SRV-UV-SPOT",
                    "name": "خدمة سبوت UV موضعي",
                    "name_en": "Spot UV Varnish",
                    "category": cat_services_post,
                    "unit": unit_sheet,
                    "cost_price": Decimal("1.20"),
                    "selling_price": Decimal("2.00"),
                    "default_supplier": saved_suppliers.get("SUP013"),
                    "description": "ورنيش UV لامع موضعي لإبراز الشعارات والرموز الخاصة",
                },
                {
                    "sku": "SRV-FIN-DIECUT",
                    "name": "خدمة تكسير وريجة داي كت",
                    "name_en": "Die Cutting & Creasing",
                    "category": cat_services_post,
                    "unit": unit_thousand,
                    "cost_price": Decimal("25.00"),
                    "selling_price": Decimal("45.00"),
                    "default_supplier": saved_suppliers.get("SUP013"),
                    "description": "تشغيل تكسير على ماكينات البندر / التكسير بالاستعارة",
                },
                {
                    "sku": "SRV-FIN-WIREO",
                    "name": "خدمة تجليد سلك معدني Wire-O",
                    "name_en": "Wire-O Metal Binding",
                    "category": cat_services_post,
                    "unit": unit_piece,
                    "cost_price": Decimal("2.50"),
                    "selling_price": Decimal("5.00"),
                    "default_supplier": saved_suppliers.get("SUP013"),
                    "description": "تخريم وتجليد سلك لولبي معدني مزدوج للنوت بوك والنتائج",
                },
                {
                    "sku": "SRV-LOG-CAIRO",
                    "name": "خدمة نقل وتوريد مطبوعات بالقاهرة الكبرى",
                    "name_en": "Delivery & Logistics Cairo",
                    "category": cat_services_root,
                    "unit": unit_service,
                    "cost_price": Decimal("250.00"),
                    "selling_price": Decimal("350.00"),
                    "default_supplier": saved_suppliers.get("SUP015"),
                    "description": "نقل سيارة نصف نقل مخصصة لنقل وتفريغ المطبوعات والكراتين",
                },
            ]

            for srv in services_manifest:
                prod, created = Product.objects.update_or_create(
                    sku=srv["sku"],
                    defaults={
                        "name": srv["name"],
                        "name_en": srv["name_en"],
                        "category": srv["category"],
                        "unit": srv["unit"],
                        "cost_price": srv["cost_price"],
                        "selling_price": srv["selling_price"],
                        "tax_rate": Decimal("14.00"),
                        "tax_code": vat_tax,
                        "min_stock": 0,
                        "is_service": True,
                        "is_active": True,
                        "default_supplier": srv.get("default_supplier"),
                        "description": srv["description"],
                        "created_by": user,
                    }
                )
                self.stdout.write(self.style.SUCCESS(f"  ✓ خدمة: {prod.name} ({prod.sku}) | بيع: {prod.selling_price} ج.م"))

            # =========================================================================
            # المرحلة الثالثة: إضافة أصناف الورق الخام وتوليد حركات المخزون الفعلية
            # =========================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n3. جاري إضافة أصناف الورق وتسجيل الأرصدة المخزنية في المخزن الرئيسي..."))

            paper_supplier = saved_suppliers.get("SUP012")

            paper_manifest = [
                {
                    "sku": "PAP-CSH-150-70100",
                    "name": "فرخ كوشيه 150 جم (70×100) إندونيسي",
                    "name_en": "Couche Paper 150gsm 70x100 Indonesian",
                    "unit": unit_sheet,
                    "cost_price": Decimal("2.80"),
                    "selling_price": Decimal("3.50"),
                    "min_stock": 1000,
                    "initial_stock": Decimal("5000.00"),
                    "description": "ورق كوشيه ناصع البياض وجهين مستورد مقاس 70×100 سم",
                },
                {
                    "sku": "PAP-CSH-170-70100",
                    "name": "فرخ كوشيه 170 جم (70×100) إندونيسي",
                    "name_en": "Couche Paper 170gsm 70x100 Indonesian",
                    "unit": unit_sheet,
                    "cost_price": Decimal("3.20"),
                    "selling_price": Decimal("4.00"),
                    "min_stock": 1000,
                    "initial_stock": Decimal("3000.00"),
                    "description": "ورق كوشيه ناصع البياض وجهين للمجلات والبروشورات 70×100 سم",
                },
                {
                    "sku": "PAP-CSH-250-70100",
                    "name": "فرخ كوشيه 250 جم (70×100) فاخر",
                    "name_en": "Couche Paper 250gsm 70x100 Premium",
                    "unit": unit_sheet,
                    "cost_price": Decimal("4.60"),
                    "selling_price": Decimal("5.80"),
                    "min_stock": 500,
                    "initial_stock": Decimal("4000.00"),
                    "description": "كوشيه ثقيل للأغلفة والفولدرات وكروت الشركات",
                },
                {
                    "sku": "PAP-CSH-300-70100",
                    "name": "فرخ كوشيه 300 جم (70×100) فاخر",
                    "name_en": "Couche Paper 300gsm 70x100 Premium",
                    "unit": unit_sheet,
                    "cost_price": Decimal("5.50"),
                    "selling_price": Decimal("7.00"),
                    "min_stock": 1000,
                    "initial_stock": Decimal("6000.00"),
                    "description": "كوشيه عالي الصلابة للأغلفة والعلب الخفيفة والبطاقات",
                },
                {
                    "sku": "PAP-CSH-350-70100",
                    "name": "فرخ كوشيه 350 جم (70×100) ثقيل",
                    "name_en": "Couche Paper 350gsm 70x100 Heavy",
                    "unit": unit_sheet,
                    "cost_price": Decimal("6.50"),
                    "selling_price": Decimal("8.20"),
                    "min_stock": 500,
                    "initial_stock": Decimal("2500.00"),
                    "description": "أعلى جراماج كوشيه لعلب الأدوية ومستحضرات التجميل والأجندات",
                },
                {
                    "sku": "PAP-CSH-150-6688",
                    "name": "فرخ كوشيه 150 جم جاير (66×88)",
                    "name_en": "Couche Paper 150gsm 66x88 Indonesian",
                    "unit": unit_sheet,
                    "cost_price": Decimal("2.30"),
                    "selling_price": Decimal("3.00"),
                    "min_stock": 1000,
                    "initial_stock": Decimal("4000.00"),
                    "description": "مقاس جاير اقتصادي للكتب والملازم والمطبوعات قياس A4",
                },
                {
                    "sku": "PAP-CSH-300-6688",
                    "name": "فرخ كوشيه 300 جم جاير (66×88)",
                    "name_en": "Couche Paper 300gsm 66x88 Indonesian",
                    "unit": unit_sheet,
                    "cost_price": Decimal("4.50"),
                    "selling_price": Decimal("5.80"),
                    "min_stock": 500,
                    "initial_stock": Decimal("3500.00"),
                    "description": "مقاس جاير اقتصادي للعلب وأغلفة الكتب مقاس 66×88 سم",
                },
                {
                    "sku": "PAP-OFF-70-70100",
                    "name": "فرخ طبع أبيض 70 جم (70×100) مصري",
                    "name_en": "Woodfree Offset Paper 70gsm 70x100",
                    "unit": unit_sheet,
                    "cost_price": Decimal("1.40"),
                    "selling_price": Decimal("1.85"),
                    "min_stock": 2000,
                    "initial_stock": Decimal("10000.00"),
                    "description": "ورق طبع أبيض ناعم للكتب والروايات ومطبوعات الشركات الداخلية",
                },
                {
                    "sku": "PAP-OFF-80-70100",
                    "name": "فرخ طبع أبيض 80 جم (70×100) مصري",
                    "name_en": "Woodfree Offset Paper 80gsm 70x100",
                    "unit": unit_sheet,
                    "cost_price": Decimal("1.60"),
                    "selling_price": Decimal("2.10"),
                    "min_stock": 2000,
                    "initial_stock": Decimal("8000.00"),
                    "description": "ورق طبع أبيض 80 جم للأوراق الرسمية ومطبوعات الخطابات",
                },
                {
                    "sku": "PAP-BRS-300-70100",
                    "name": "فرخ بريستول كرتون 300 جم (70×100)",
                    "name_en": "Bristol Board 300gsm 70x100",
                    "unit": unit_sheet,
                    "cost_price": Decimal("6.00"),
                    "selling_price": Decimal("7.80"),
                    "min_stock": 500,
                    "initial_stock": Decimal("2000.00"),
                    "description": "كرتون بريستول ناصع البياض وجهين للعلب والشنط والمنتجات الورقية",
                },
                {
                    "sku": "PAP-DPL-300-70100",
                    "name": "فرخ دوبلكس ظهر رمادي 300 جم (70×100)",
                    "name_en": "Duplex Board Grey Back 300gsm 70x100",
                    "unit": unit_sheet,
                    "cost_price": Decimal("4.80"),
                    "selling_price": Decimal("6.20"),
                    "min_stock": 500,
                    "initial_stock": Decimal("3000.00"),
                    "description": "كرتون دوبلكس ظهر رمادي لتصنيع علب التعبئة والشحن الكرتونية",
                },
                {
                    "sku": "PAP-STK-70100",
                    "name": "فرخ ستيكر لاصق كوشيه (70×100)",
                    "name_en": "Self-Adhesive Gloss Sticker 70x100",
                    "unit": unit_sheet,
                    "cost_price": Decimal("4.20"),
                    "selling_price": Decimal("5.50"),
                    "min_stock": 500,
                    "initial_stock": Decimal("2000.00"),
                    "description": "ورق لاصق عالي الجودة للستيكرات واستيكرات العبوات والزجاجات",
                },
            ]

            for pap in paper_manifest:
                product, created = Product.objects.update_or_create(
                    sku=pap["sku"],
                    defaults={
                        "name": pap["name"],
                        "name_en": pap["name_en"],
                        "category": cat_paper,
                        "unit": pap["unit"],
                        "cost_price": pap["cost_price"],
                        "selling_price": pap["selling_price"],
                        "tax_rate": Decimal("14.00"),
                        "tax_code": vat_tax,
                        "min_stock": pap["min_stock"],
                        "is_service": False,
                        "is_active": True,
                        "default_supplier": paper_supplier,
                        "description": pap["description"],
                        "created_by": user,
                    }
                )

                # التحقق مما إذا كان للصنف رصيد مخزني مسبق؛ إذا لم يكن، نسجل رصيد افتتاحي عبر خدمة المخزون
                current_qty = product.current_stock
                if current_qty == 0 and pap.get("initial_stock", 0) > 0:
                    InventoryService.record_movement(
                        product=product,
                        movement_type="in",
                        quantity=pap["initial_stock"],
                        warehouse=main_warehouse,
                        source="opening",
                        unit_cost=pap["cost_price"],
                        reference_number=f"INIT-{product.sku}",
                        notes="رصيد مخزني افتتاحي معتمد لأصناف الورق",
                        user=user
                    )
                    product.refresh_from_db()

                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ ورق: {product.name} ({product.sku}) | الرصيد المخزني: {product.current_stock} فرخ | المخزن: {main_warehouse.name}"
                ))

        self.stdout.write(self.style.SUCCESS("\n======================================================="))
        self.stdout.write(self.style.SUCCESS("✓ تم ملء كافة البيانات التجريبية بنجاح بنسبة 100%!"))
        self.stdout.write(self.style.SUCCESS("✓ تم تفعيل الحسابات المحاسبية وأدلة الحسابات وحركات المخزون والخدمات بدقة."))
        self.stdout.write(self.style.SUCCESS("======================================================="))
