# Generated manually for independent pricing system

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("supplier", "0004_supplier_financial_account"),
        ("client", "0004_customer_financial_account"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pricing", "0003_add_independent_pricing_models"),
    ]

    operations = [
        # إنشاء نموذج OrderSupplier
        migrations.CreateModel(
            name="OrderSupplier",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("primary", "أساسي"),
                            ("secondary", "ثانوي"),
                            ("backup", "احتياطي"),
                            ("specialist", "متخصص"),
                        ],
                        default="secondary",
                        max_length=20,
                        verbose_name="دور المورد",
                    ),
                ),
                (
                    "service_type",
                    models.CharField(
                        choices=[
                            ("printing", "طباعة"),
                            ("paper", "ورق"),
                            ("finishing", "تشطيب"),
                            ("coating", "تغطية"),
                            ("binding", "تجليد"),
                            ("cutting", "قص"),
                            ("other", "أخرى"),
                        ],
                        max_length=20,
                        verbose_name="نوع الخدمة",
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="وصف الخدمة"),
                ),
                (
                    "estimated_cost",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                        verbose_name="التكلفة المقدرة",
                    ),
                ),
                (
                    "quoted_price",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                        verbose_name="السعر المعروض",
                    ),
                ),
                (
                    "contact_person",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="الشخص المسؤول"
                    ),
                ),
                (
                    "phone",
                    models.CharField(blank=True, max_length=20, verbose_name="الهاتف"),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="البريد الإلكتروني"
                    ),
                ),
                (
                    "is_confirmed",
                    models.BooleanField(default=False, verbose_name="مؤكد"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإضافة"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث"),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="order_suppliers",
                        to="pricing.pricingorder",
                        verbose_name="الطلب",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supplier_orders",
                        to="supplier.supplier",
                        verbose_name="المورد",
                    ),
                ),
            ],
            options={
                "verbose_name": "مورد الطلب",
                "verbose_name_plural": "موردي الطلب",
                "ordering": ["role", "service_type", "supplier__name"],
            },
        ),
        # إنشاء نموذج PricingQuotation
        migrations.CreateModel(
            name="PricingQuotation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quotation_number",
                    models.CharField(
                        editable=False,
                        max_length=20,
                        unique=True,
                        verbose_name="رقم العرض",
                    ),
                ),
                ("valid_until", models.DateField(verbose_name="صالح حتى")),
                (
                    "follow_up_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="تاريخ المتابعة"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "مسودة"),
                            ("sent", "مرسل"),
                            ("under_review", "قيد المراجعة"),
                            ("accepted", "مقبول"),
                            ("rejected", "مرفوض"),
                            ("expired", "منتهي الصلاحية"),
                            ("cancelled", "ملغي"),
                        ],
                        default="draft",
                        max_length=20,
                        verbose_name="الحالة",
                    ),
                ),
                ("payment_terms", models.TextField(verbose_name="شروط الدفع")),
                ("delivery_terms", models.TextField(verbose_name="شروط التسليم")),
                (
                    "warranty_terms",
                    models.TextField(blank=True, verbose_name="شروط الضمان"),
                ),
                (
                    "special_conditions",
                    models.TextField(blank=True, verbose_name="شروط خاصة"),
                ),
                (
                    "sent_to_person",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="أرسل إلى"
                    ),
                ),
                (
                    "sent_via",
                    models.CharField(
                        choices=[
                            ("email", "بريد إلكتروني"),
                            ("whatsapp", "واتساب"),
                            ("hand_delivery", "تسليم يد"),
                            ("fax", "فاكس"),
                            ("phone", "هاتف"),
                        ],
                        default="email",
                        max_length=20,
                        verbose_name="طريقة الإرسال",
                    ),
                ),
                (
                    "discount_percentage",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=5,
                        verbose_name="نسبة الخصم %",
                    ),
                ),
                (
                    "client_feedback",
                    models.TextField(blank=True, verbose_name="ملاحظات العميل"),
                ),
                (
                    "internal_notes",
                    models.TextField(blank=True, verbose_name="ملاحظات داخلية"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث"),
                ),
                (
                    "pricing_order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quotation",
                        to="pricing.pricingorder",
                        verbose_name="طلب التسعير",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_quotations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
            ],
            options={
                "verbose_name": "عرض سعر",
                "verbose_name_plural": "عروض الأسعار",
                "ordering": ["-created_at"],
            },
        ),
        # إنشاء نموذج PricingApprovalWorkflow
        migrations.CreateModel(
            name="PricingApprovalWorkflow",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, verbose_name="اسم التدفق")),
                ("description", models.TextField(blank=True, verbose_name="الوصف")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                (
                    "min_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                        verbose_name="الحد الأدنى للمبلغ",
                    ),
                ),
                (
                    "max_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="الحد الأقصى للمبلغ",
                    ),
                ),
                (
                    "email_notifications",
                    models.BooleanField(
                        default=True, verbose_name="إشعارات بريد إلكتروني"
                    ),
                ),
                (
                    "whatsapp_notifications",
                    models.BooleanField(default=False, verbose_name="إشعارات واتساب"),
                ),
                (
                    "auto_approve_below_limit",
                    models.BooleanField(
                        default=False, verbose_name="موافقة تلقائية تحت الحد"
                    ),
                ),
                (
                    "require_both_approvers",
                    models.BooleanField(
                        default=False, verbose_name="يتطلب موافقة الاثنين"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_workflows",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
                (
                    "primary_approver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="primary_workflows",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المعتمد الأساسي",
                    ),
                ),
                (
                    "secondary_approver",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="secondary_workflows",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المعتمد الثانوي",
                    ),
                ),
            ],
            options={
                "verbose_name": "تدفق موافقة التسعير",
                "verbose_name_plural": "تدفقات موافقة التسعير",
                "ordering": ["name"],
            },
        ),
        # إنشاء نموذج PricingApproval
        migrations.CreateModel(
            name="PricingApproval",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "في الانتظار"),
                            ("approved", "موافق عليه"),
                            ("rejected", "مرفوض"),
                            ("cancelled", "ملغي"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="الحالة",
                    ),
                ),
                ("comments", models.TextField(blank=True, verbose_name="التعليقات")),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("low", "منخفضة"),
                            ("medium", "متوسطة"),
                            ("high", "عالية"),
                            ("urgent", "عاجل"),
                        ],
                        default="medium",
                        max_length=20,
                        verbose_name="الأولوية",
                    ),
                ),
                (
                    "approved_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="تاريخ الموافقة"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث"),
                ),
                (
                    "pricing_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="approvals",
                        to="pricing.pricingorder",
                        verbose_name="طلب التسعير",
                    ),
                ),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approvals",
                        to="pricing.pricingapprovalworkflow",
                        verbose_name="تدفق الموافقة",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requested_approvals",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="طلب بواسطة",
                    ),
                ),
                (
                    "approver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="handled_approvals",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المعتمد",
                    ),
                ),
            ],
            options={
                "verbose_name": "موافقة تسعير",
                "verbose_name_plural": "موافقات التسعير",
                "ordering": ["-created_at"],
            },
        ),
        # إنشاء نموذج PricingReport
        migrations.CreateModel(
            name="PricingReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "report_type",
                    models.CharField(
                        choices=[
                            ("orders", "تقرير الطلبات"),
                            ("quotations", "تقرير العروض"),
                            ("approvals", "تقرير الموافقات"),
                            ("suppliers", "تقرير الموردين"),
                            ("clients", "تقرير العملاء"),
                            ("performance", "تقرير الأداء"),
                        ],
                        max_length=20,
                        verbose_name="نوع التقرير",
                    ),
                ),
                (
                    "title",
                    models.CharField(max_length=200, verbose_name="عنوان التقرير"),
                ),
                ("date_from", models.DateField(verbose_name="من تاريخ")),
                ("date_to", models.DateField(verbose_name="إلى تاريخ")),
                (
                    "order_type_filter",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("catalog", "كتالوج"),
                            ("brochure", "بروشور"),
                            ("rollup", "رول أب"),
                            ("flyer", "فلاير"),
                            ("business_card", "كارت شخصي"),
                            ("envelope", "ظرف"),
                            ("letterhead", "ورق مراسلات"),
                            ("poster", "بوستر"),
                            ("sticker", "استيكر"),
                            ("notebook", "نوتة"),
                            ("calendar", "تقويم"),
                            ("invitation", "كارت دعوة"),
                            ("folder", "فولدر"),
                            ("other", "أخرى"),
                        ],
                        max_length=20,
                        verbose_name="فلتر نوع الطلب",
                    ),
                ),
                (
                    "report_data",
                    models.JSONField(default=dict, verbose_name="بيانات التقرير"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "client_filter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reports",
                        to="client.customer",
                        verbose_name="فلتر العميل",
                    ),
                ),
                (
                    "supplier_filter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reports",
                        to="supplier.supplier",
                        verbose_name="فلتر المورد",
                    ),
                ),
                (
                    "generated_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="generated_reports",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
            ],
            options={
                "verbose_name": "تقرير تسعير",
                "verbose_name_plural": "تقارير التسعير",
                "ordering": ["-created_at"],
            },
        ),
        # إنشاء نموذج PricingKPI
        migrations.CreateModel(
            name="PricingKPI",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kpi_type",
                    models.CharField(
                        choices=[
                            ("orders_count", "عدد الطلبات"),
                            ("quotations_count", "عدد العروض"),
                            ("approval_rate", "معدل الموافقة"),
                            ("avg_order_value", "متوسط قيمة الطلب"),
                            ("client_satisfaction", "رضا العملاء"),
                            ("supplier_performance", "أداء الموردين"),
                            ("response_time", "وقت الاستجابة"),
                            ("conversion_rate", "معدل التحويل"),
                        ],
                        max_length=30,
                        verbose_name="نوع المؤشر",
                    ),
                ),
                (
                    "period_type",
                    models.CharField(
                        choices=[
                            ("daily", "يومي"),
                            ("weekly", "أسبوعي"),
                            ("monthly", "شهري"),
                            ("quarterly", "ربع سنوي"),
                            ("yearly", "سنوي"),
                        ],
                        default="monthly",
                        max_length=20,
                        verbose_name="نوع الفترة",
                    ),
                ),
                ("period_start", models.DateField(verbose_name="بداية الفترة")),
                ("period_end", models.DateField(verbose_name="نهاية الفترة")),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2, max_digits=15, verbose_name="القيمة"
                    ),
                ),
                (
                    "target_value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="القيمة المستهدفة",
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث"),
                ),
            ],
            options={
                "verbose_name": "مؤشر أداء التسعير",
                "verbose_name_plural": "مؤشرات أداء التسعير",
                "ordering": ["-period_start", "kpi_type"],
            },
        ),
        # إضافة unique_together constraints
        migrations.AlterUniqueTogether(
            name="ordersupplier",
            unique_together={("order", "supplier", "service_type")},
        ),
        migrations.AlterUniqueTogether(
            name="pricingapproval",
            unique_together={("pricing_order", "workflow", "approver")},
        ),
    ]
