"""
مصنع البيانات للاختبارات - إنشاء بيانات واقعية للتسعير
Test Data Factory - Create Realistic Data for Pricing Tests
"""
import random
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()
from django.utils import timezone

from pricing.models import (
    PricingOrder,
    PaperType,
    PaperSize,
    CoatingType,
    FinishingType,
    PlateSize,
    VATSetting,
    PricingSupplierSelection,
)
from supplier.models import (
    Supplier,
    SupplierType,
    SupplierServiceTag,
    SpecializedService,
    PaperServiceDetails,
    DigitalPrintingDetails,
    PlateServiceDetails,
    ServicePriceTier,
)
from client.models import Customer


class PricingTestDataFactory:
    """مصنع إنشاء بيانات الاختبار للتسعير"""

    @staticmethod
    def create_users(count=5):
        """إنشاء مستخدمين للاختبار"""
        users = []
        for i in range(count):
            user = User.objects.create_user(
                username=f"test_user_{i+1}",
                email=f"user{i+1}@test.com",
                password="testpass123",
                first_name=f"مستخدم {i+1}",
                last_name="الاختبار",
            )
            users.append(user)
        return users

    @staticmethod
    def create_customers(count=10):
        """إنشاء عملاء للاختبار"""
        customers = []
        company_types = ["شركة", "مؤسسة", "مكتب", "معهد", "مركز"]
        business_areas = ["التسويق", "التصميم", "التعليم", "الطباعة", "الإعلان"]

        for i in range(count):
            company_type = random.choice(company_types)
            business_area = random.choice(business_areas)

            customer = Customer.objects.create(
                name=f"{company_type} {business_area} رقم {i+1}",
                code=f"CUST{i+1:03d}",
                company_name=f"{company_type} {business_area} المحدودة",
                phone=f"0{random.randint(500000000, 599999999)}",
                phone_primary=f"0{random.randint(500000000, 599999999)}",
                email=f"customer{i+1}@company{i+1}.com",
                city=random.choice(["الرياض", "جدة", "الدمام", "مكة", "المدينة"]),
                address=f"حي النموذجي، شارع {i+1}، مبنى رقم {random.randint(1, 100)}",
            )
            customers.append(customer)

        return customers

    @staticmethod
    def create_supplier_types():
        """إنشاء أنواع الموردين"""
        supplier_types_data = [
            ("paper", "موردي الورق", "موردي الورق والخامات الأساسية"),
            ("printing", "موردي الطباعة", "موردي خدمات الطباعة الرقمية والأوفست"),
            ("finishing", "موردي التشطيب", "موردي خدمات ما بعد الطباعة والتشطيب"),
            ("binding", "موردي التجليد", "موردي خدمات التجليد والتغطية"),
            ("design", "موردي التصميم", "موردي خدمات التصميم والإخراج"),
        ]

        supplier_types = []
        for code, name, description in supplier_types_data:
            supplier_type, created = SupplierType.objects.get_or_create(
                code=code, defaults={"name": name, "description": description}
            )
            supplier_types.append(supplier_type)

        return supplier_types

    @staticmethod
    def create_service_tags():
        """إنشاء خدمات الموردين"""
        service_tags_data = [
            ("paper_normal", "ورق عادي", "ورق أبيض عادي للطباعة"),
            ("paper_glossy", "ورق لامع", "ورق لامع عالي الجودة"),
            ("paper_matte", "ورق مطفي", "ورق مطفي للطباعة الفاخرة"),
            ("digital_color", "طباعة رقمية ملونة", "طباعة رقمية بالألوان الكاملة"),
            ("digital_bw", "طباعة رقمية أبيض وأسود", "طباعة رقمية بالأبيض والأسود"),
            ("offset_color", "طباعة أوفست ملونة", "طباعة أوفست بالألوان"),
            ("coating_gloss", "تغطية لامع", "تغطية بطبقة لامعة"),
            ("coating_matte", "تغطية مطفي", "تغطية بطبقة مطفية"),
            ("binding_saddle", "تجليد وسط", "تجليد بالتدبيس الوسطي"),
            ("binding_perfect", "تجليد مثالي", "تجليد مثالي بالغراء"),
        ]

        service_tags = []
        for code, name, description in service_tags_data:
            service_tag, created = SupplierServiceTag.objects.get_or_create(
                code=code, defaults={"name": name, "description": description}
            )
            service_tags.append(service_tag)

        return service_tags

    @staticmethod
    def create_suppliers(supplier_types, service_tags, count=15):
        """إنشاء موردين للاختبار"""
        suppliers = []
        supplier_names = [
            "مطبعة النجاح",
            "شركة الإبداع للطباعة",
            "مؤسسة التميز",
            "مطبعة الجودة العالية",
            "شركة الفن الحديث",
            "مكتب التصميم المتقدم",
            "مطبعة السرعة",
            "شركة الدقة للطباعة",
            "مؤسسة الاحتراف",
            "مطبعة التقنية الحديثة",
            "شركة الإنتاج المتميز",
            "مكتب الخدمات الشاملة",
            "مطبعة الجودة الفائقة",
            "شركة الحلول المتكاملة",
            "مؤسسة الخبرة",
        ]

        for i in range(min(count, len(supplier_names))):
            supplier_type = random.choice(supplier_types)

            supplier = Supplier.objects.create(
                name=supplier_names[i],
                code=f"SUP{i+1:03d}",
                primary_type=supplier_type,
                phone=f"0{random.randint(100000000, 199999999)}",
                phone_secondary=f"0{random.randint(100000000, 199999999)}",
                email=f"supplier{i+1}@company{i+1}.com",
                website=f"www.supplier{i+1}.com",
                city=random.choice(["الرياض", "جدة", "الدمام", "مكة", "المدينة"]),
                address=f"المنطقة الصناعية، شارع {i+1}، مبنى رقم {random.randint(1, 50)}",
                contact_person=f"أحمد محمد {i+1}",
                is_active=True,
            )

            # إضافة خدمات عشوائية للمورد
            random_tags = random.sample(service_tags, random.randint(2, 5))
            supplier.service_tags.set(random_tags)

            suppliers.append(supplier)

        return suppliers

    @staticmethod
    def create_paper_types_and_sizes():
        """إنشاء أنواع الورق والمقاسات"""
        # أنواع الورق
        paper_types_data = [
            ("WHITE_NORMAL", "ورق أبيض عادي", "ورق أبيض عادي للطباعة العامة"),
            ("WHITE_PREMIUM", "ورق أبيض فاخر", "ورق أبيض عالي الجودة"),
            ("GLOSSY", "ورق لامع", "ورق لامع للطباعة الفاخرة"),
            ("MATTE", "ورق مطفي", "ورق مطفي للطباعة الراقية"),
            ("CARDBOARD", "كرتون", "كرتون للطباعة والتغطية"),
        ]

        paper_types = []
        for code, name, description in paper_types_data:
            paper_type, created = PaperType.objects.get_or_create(
                code=code, defaults={"name": name, "description": description}
            )
            paper_types.append(paper_type)

        # مقاسات الورق
        paper_sizes_data = [
            ("A4", 210, 297, "mm"),
            ("A3", 297, 420, "mm"),
            ("A5", 148, 210, "mm"),
            ("LETTER", 216, 279, "mm"),
            ("LEGAL", 216, 356, "mm"),
            ("BUSINESS_CARD", 90, 50, "mm"),
        ]

        paper_sizes = []
        for name, width, height, unit in paper_sizes_data:
            paper_size, created = PaperSize.objects.get_or_create(
                name=name, defaults={"width": width, "height": height, "unit": unit}
            )
            paper_sizes.append(paper_size)

        return paper_types, paper_sizes

    @staticmethod
    def create_paper_services(suppliers, paper_types, paper_sizes):
        """إنشاء خدمات الورق"""
        paper_services = []
        gsm_options = [80, 90, 120, 150, 200, 250, 300]

        for supplier in suppliers:
            # كل مورد يقدم خدمات لعدة أنواع ورق
            for paper_type in random.sample(paper_types, random.randint(2, 4)):
                for paper_size in random.sample(paper_sizes, random.randint(2, 4)):
                    gsm = random.choice(gsm_options)

                    # حساب أسعار واقعية
                    base_price = Decimal(str(random.uniform(0.10, 3.00)))
                    kg_price = Decimal(str(random.uniform(10.00, 50.00)))

                    paper_service = PaperServiceDetails.objects.create(
                        supplier=supplier,
                        paper_type=paper_type,
                        paper_size=paper_size,
                        gsm=gsm,
                        price_per_sheet=base_price,
                        price_per_kg=kg_price,
                        minimum_quantity=random.randint(100, 1000),
                        is_active=True,
                    )
                    paper_services.append(paper_service)

        return paper_services

    @staticmethod
    def create_digital_printing_services(suppliers, paper_sizes):
        """إنشاء خدمات الطباعة الرقمية"""
        digital_services = []
        color_types = ["color", "bw"]

        for supplier in suppliers:
            for paper_size in random.sample(paper_sizes, random.randint(2, 4)):
                for color_type in color_types:
                    # أسعار واقعية للطباعة الرقمية
                    if color_type == "color":
                        price = Decimal(str(random.uniform(1.00, 5.00)))
                    else:
                        price = Decimal(str(random.uniform(0.20, 1.50)))

                    digital_service = DigitalPrintingDetails.objects.create(
                        supplier=supplier,
                        paper_size=paper_size,
                        color_type=color_type,
                        price_per_copy=price,
                        minimum_quantity=random.randint(1, 100),
                        maximum_quantity=random.randint(5000, 50000),
                        is_active=True,
                    )
                    digital_services.append(digital_service)

        return digital_services

    @staticmethod
    def create_specialized_services(suppliers, supplier_types):
        """إنشاء خدمات متخصصة"""
        specialized_services = []
        service_names = [
            "تغطية لامع",
            "تغطية مطفي",
            "قص بالليزر",
            "تجليد حلزوني",
            "تجليد مثالي",
            "طباعة أوفست",
            "طباعة رقمية",
            "تصميم إبداعي",
        ]

        for supplier in suppliers:
            # كل مورد يقدم 2-4 خدمات متخصصة
            for i in range(random.randint(2, 4)):
                service_name = random.choice(service_names)

                specialized_service = SpecializedService.objects.create(
                    supplier=supplier,
                    category=supplier.primary_type,
                    name=f"{service_name} - {supplier.name}",
                    description=f"خدمة {service_name} عالية الجودة",
                    base_price=Decimal(str(random.uniform(50.00, 500.00))),
                    setup_cost=Decimal(str(random.uniform(0.00, 200.00))),
                    min_quantity=random.randint(1, 500),
                    is_active=True,
                )
                specialized_services.append(specialized_service)

                # إضافة شرائح سعرية
                PricingTestDataFactory.create_price_tiers(specialized_service)

        return specialized_services

    @staticmethod
    def create_price_tiers(service):
        """إنشاء شرائح سعرية للخدمة"""
        tiers_data = [
            (1, 500, service.base_price, Decimal("0.00")),
            (501, 1000, service.base_price * Decimal("0.95"), Decimal("5.00")),
            (1001, 5000, service.base_price * Decimal("0.90"), Decimal("10.00")),
            (5001, None, service.base_price * Decimal("0.85"), Decimal("15.00")),
        ]

        for min_qty, max_qty, unit_price, discount in tiers_data:
            ServicePriceTier.objects.create(
                service=service,
                min_quantity=min_qty,
                max_quantity=max_qty,
                unit_price=unit_price,
                discount_percentage=discount,
            )

    @staticmethod
    def create_pricing_orders(
        customers, suppliers, paper_types, paper_sizes, users, count=20
    ):
        """إنشاء طلبات تسعير للاختبار"""
        orders = []
        order_types = ["digital", "offset"]

        for i in range(count):
            order = PricingOrder.objects.create(
                customer=random.choice(customers),
                order_type=random.choice(order_types),
                paper_type=random.choice(paper_types),
                paper_size=random.choice(paper_sizes),
                quantity=random.randint(100, 10000),
                description=f'طلب تسعير رقم {i+1} - {random.choice(["كروت شخصية", "كتالوج", "بروشور", "فلاير", "ملصقات"])}',
                supplier=random.choice(suppliers),
                created_by=random.choice(users),
            )
            orders.append(order)

        return orders

    @staticmethod
    def create_vat_setting():
        """إنشاء إعدادات الضريبة"""
        vat_setting, created = VATSetting.objects.get_or_create(
            defaults={
                "rate": Decimal("15.00"),
                "is_active": True,
                "description": "ضريبة القيمة المضافة السعودية",
            }
        )
        return vat_setting

    @staticmethod
    def create_complete_test_environment():
        """إنشاء بيئة اختبار كاملة"""
        print("إنشاء بيئة اختبار كاملة للتسعير...")

        # إنشاء المستخدمين
        users = PricingTestDataFactory.create_users(5)
        print(f"تم إنشاء {len(users)} مستخدم")

        # إنشاء العملاء
        customers = PricingTestDataFactory.create_customers(10)
        print(f"تم إنشاء {len(customers)} عميل")

        # إنشاء أنواع الموردين وخدماتهم
        supplier_types = PricingTestDataFactory.create_supplier_types()
        service_tags = PricingTestDataFactory.create_service_tags()
        print(f"تم إنشاء {len(supplier_types)} نوع مورد و {len(service_tags)} خدمة")

        # إنشاء الموردين
        suppliers = PricingTestDataFactory.create_suppliers(
            supplier_types, service_tags, 15
        )
        print(f"تم إنشاء {len(suppliers)} مورد")

        # إنشاء أنواع الورق والمقاسات
        paper_types, paper_sizes = PricingTestDataFactory.create_paper_types_and_sizes()
        print(f"تم إنشاء {len(paper_types)} نوع ورق و {len(paper_sizes)} مقاس")

        # إنشاء خدمات الورق
        paper_services = PricingTestDataFactory.create_paper_services(
            suppliers, paper_types, paper_sizes
        )
        print(f"تم إنشاء {len(paper_services)} خدمة ورق")

        # إنشاء خدمات الطباعة الرقمية
        digital_services = PricingTestDataFactory.create_digital_printing_services(
            suppliers, paper_sizes
        )
        print(f"تم إنشاء {len(digital_services)} خدمة طباعة رقمية")

        # إنشاء خدمات متخصصة
        specialized_services = PricingTestDataFactory.create_specialized_services(
            suppliers, supplier_types
        )
        print(f"تم إنشاء {len(specialized_services)} خدمة متخصصة")

        # إنشاء طلبات تسعير
        orders = PricingTestDataFactory.create_pricing_orders(
            customers, suppliers, paper_types, paper_sizes, users, 20
        )
        print(f"تم إنشاء {len(orders)} طلب تسعير")

        # إنشاء إعدادات الضريبة
        vat_setting = PricingTestDataFactory.create_vat_setting()
        print(f"تم إنشاء إعدادات الضريبة: {vat_setting.rate}%")

        print("\nتم إنشاء بيئة اختبار كاملة بنجاح!")

        return {
            "users": users,
            "customers": customers,
            "supplier_types": supplier_types,
            "service_tags": service_tags,
            "suppliers": suppliers,
            "paper_types": paper_types,
            "paper_sizes": paper_sizes,
            "paper_services": paper_services,
            "digital_services": digital_services,
            "specialized_services": specialized_services,
            "orders": orders,
            "vat_setting": vat_setting,
        }
