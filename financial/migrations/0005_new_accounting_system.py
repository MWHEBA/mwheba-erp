# Generated manually for new accounting system

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("financial", "0003_bankreconciliation"),
    ]

    operations = [
        # إنشاء نموذج AccountType
        migrations.CreateModel(
            name="AccountType",
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
                    "code",
                    models.CharField(
                        max_length=10, unique=True, verbose_name="كود النوع"
                    ),
                ),
                ("name", models.CharField(max_length=100, verbose_name="اسم النوع")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("asset", "أصول"),
                            ("liability", "خصوم"),
                            ("equity", "حقوق الملكية"),
                            ("revenue", "إيرادات"),
                            ("expense", "مصروفات"),
                        ],
                        max_length=20,
                        verbose_name="التصنيف",
                    ),
                ),
                (
                    "nature",
                    models.CharField(
                        choices=[("debit", "مدين"), ("credit", "دائن")],
                        max_length=10,
                        verbose_name="الطبيعة",
                    ),
                ),
                (
                    "level",
                    models.PositiveIntegerField(default=1, verbose_name="المستوى"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
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
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="account_types_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="financial.accounttype",
                        verbose_name="النوع الأب",
                    ),
                ),
            ],
            options={
                "verbose_name": "نوع الحساب",
                "verbose_name_plural": "أنواع الحسابات",
                "ordering": ["code"],
            },
        ),
        # إنشاء نموذج ChartOfAccounts
        migrations.CreateModel(
            name="ChartOfAccounts",
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
                    "code",
                    models.CharField(
                        max_length=8,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="كود الحساب يجب أن يكون من 4 إلى 8 أرقام",
                                regex="^\\d{4,8}$",
                            )
                        ],
                        verbose_name="كود الحساب",
                    ),
                ),
                ("name", models.CharField(max_length=200, verbose_name="اسم الحساب")),
                (
                    "name_en",
                    models.CharField(
                        blank=True,
                        max_length=200,
                        null=True,
                        verbose_name="الاسم بالإنجليزية",
                    ),
                ),
                (
                    "level",
                    models.PositiveIntegerField(default=1, verbose_name="المستوى"),
                ),
                (
                    "is_leaf",
                    models.BooleanField(
                        default=True,
                        help_text="الحسابات النهائية فقط يمكن إدراج قيود عليها",
                        verbose_name="حساب نهائي",
                    ),
                ),
                (
                    "is_bank_account",
                    models.BooleanField(default=False, verbose_name="حساب بنكي"),
                ),
                (
                    "is_cash_account",
                    models.BooleanField(default=False, verbose_name="حساب نقدي"),
                ),
                (
                    "is_reconcilable",
                    models.BooleanField(default=False, verbose_name="يخضع للتسوية"),
                ),
                (
                    "is_control_account",
                    models.BooleanField(default=False, verbose_name="حساب رقابي"),
                ),
                (
                    "description",
                    models.TextField(blank=True, null=True, verbose_name="الوصف"),
                ),
                (
                    "notes",
                    models.TextField(blank=True, null=True, verbose_name="ملاحظات"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                (
                    "is_system_account",
                    models.BooleanField(
                        default=False,
                        help_text="الحسابات النظامية لا يمكن حذفها",
                        verbose_name="حساب نظام",
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
                    "account_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="accounts",
                        to="financial.accounttype",
                        verbose_name="نوع الحساب",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chart_accounts_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="financial.chartofaccounts",
                        verbose_name="الحساب الأب",
                    ),
                ),
            ],
            options={
                "verbose_name": "حساب",
                "verbose_name_plural": "دليل الحسابات",
                "ordering": ["code"],
            },
        ),
        # إنشاء نموذج AccountingPeriod
        migrations.CreateModel(
            name="AccountingPeriod",
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
                ("name", models.CharField(max_length=100, verbose_name="اسم الفترة")),
                ("start_date", models.DateField(verbose_name="تاريخ البداية")),
                ("end_date", models.DateField(verbose_name="تاريخ النهاية")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "مفتوحة"),
                            ("closed", "مغلقة"),
                            ("locked", "مقفلة"),
                        ],
                        default="open",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "closed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="تاريخ الإغلاق"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "closed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="periods_closed",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أغلق بواسطة",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="periods_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
            ],
            options={
                "verbose_name": "فترة محاسبية",
                "verbose_name_plural": "الفترات المحاسبية",
                "ordering": ["-start_date"],
            },
        ),
        # إنشاء نموذج JournalEntry
        migrations.CreateModel(
            name="JournalEntry",
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
                    "number",
                    models.CharField(
                        max_length=20, unique=True, verbose_name="رقم القيد"
                    ),
                ),
                (
                    "date",
                    models.DateField(
                        default=django.utils.timezone.now, verbose_name="التاريخ"
                    ),
                ),
                (
                    "entry_type",
                    models.CharField(
                        choices=[
                            ("manual", "يدوي"),
                            ("automatic", "تلقائي"),
                            ("adjustment", "تسوية"),
                            ("closing", "إقفال"),
                            ("opening", "افتتاحي"),
                        ],
                        default="manual",
                        max_length=20,
                        verbose_name="نوع القيد",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "مسودة"),
                            ("posted", "مرحل"),
                            ("cancelled", "ملغي"),
                        ],
                        default="draft",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                ("description", models.TextField(verbose_name="البيان")),
                (
                    "reference",
                    models.CharField(
                        blank=True, max_length=100, null=True, verbose_name="المرجع"
                    ),
                ),
                (
                    "reference_type",
                    models.CharField(
                        blank=True, max_length=50, null=True, verbose_name="نوع المرجع"
                    ),
                ),
                (
                    "reference_id",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="معرف المرجع"
                    ),
                ),
                (
                    "posted_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="تاريخ الترحيل"
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
                    "accounting_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="journal_entries",
                        to="financial.accountingperiod",
                        verbose_name="الفترة المحاسبية",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="entries_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
                (
                    "posted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="entries_posted",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="رحل بواسطة",
                    ),
                ),
            ],
            options={
                "verbose_name": "قيد يومي",
                "verbose_name_plural": "القيود اليومية",
                "ordering": ["-date", "-number"],
            },
        ),
        # إنشاء نموذج JournalEntryLine
        migrations.CreateModel(
            name="JournalEntryLine",
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
                    "debit",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=15,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0"))
                        ],
                        verbose_name="مدين",
                    ),
                ),
                (
                    "credit",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=15,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0"))
                        ],
                        verbose_name="دائن",
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, null=True, verbose_name="البيان"),
                ),
                (
                    "cost_center",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        null=True,
                        verbose_name="مركز التكلفة",
                    ),
                ),
                (
                    "project",
                    models.CharField(
                        blank=True, max_length=50, null=True, verbose_name="المشروع"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="journal_lines",
                        to="financial.chartofaccounts",
                        verbose_name="الحساب",
                    ),
                ),
                (
                    "journal_entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="financial.journalentry",
                        verbose_name="القيد اليومي",
                    ),
                ),
            ],
            options={
                "verbose_name": "بند قيد",
                "verbose_name_plural": "بنود القيود",
            },
        ),
        # إنشاء نموذج AccountGroup
        migrations.CreateModel(
            name="AccountGroup",
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
                ("name", models.CharField(max_length=100, verbose_name="اسم المجموعة")),
                (
                    "description",
                    models.TextField(blank=True, null=True, verbose_name="الوصف"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "accounts",
                    models.ManyToManyField(
                        blank=True,
                        related_name="groups",
                        to="financial.chartofaccounts",
                        verbose_name="الحسابات",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="account_groups_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
            ],
            options={
                "verbose_name": "مجموعة حسابات",
                "verbose_name_plural": "مجموعات الحسابات",
                "ordering": ["name"],
            },
        ),
        # إضافة الفهارس
        migrations.AddIndex(
            model_name="chartofaccounts",
            index=models.Index(fields=["code"], name="financial_c_code_idx"),
        ),
        migrations.AddIndex(
            model_name="chartofaccounts",
            index=models.Index(
                fields=["account_type", "is_active"],
                name="financial_c_account_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="chartofaccounts",
            index=models.Index(
                fields=["parent", "level"], name="financial_c_parent_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="journalentry",
            index=models.Index(
                fields=["date", "status"], name="financial_j_date_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="journalentry",
            index=models.Index(fields=["number"], name="financial_j_number_idx"),
        ),
        migrations.AddIndex(
            model_name="journalentry",
            index=models.Index(
                fields=["reference_type", "reference_id"],
                name="financial_j_reference_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="journalentryline",
            index=models.Index(
                fields=["account", "journal_entry"],
                name="financial_j_account_entry_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="journalentryline",
            index=models.Index(fields=["journal_entry"], name="financial_j_entry_idx"),
        ),
        # إضافة القيود الفريدة
        migrations.AddConstraint(
            model_name="accountingperiod",
            constraint=models.UniqueConstraint(
                fields=("start_date", "end_date"), name="unique_accounting_period"
            ),
        ),
    ]
