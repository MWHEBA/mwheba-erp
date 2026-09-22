"""
نماذج العهد العينية والأجهزة والمهمات بالموارد البشرية
Employee Asset & Equipment Custody Models
"""

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AssetCustodyStatus(models.TextChoices):
    ACTIVE = "active", _("مسلمة للموظف (جارية)")
    RETURNED = "returned", _("مستردة للمخزن بحالة سليمة")
    DAMAGED = "damaged", _("تالفة / تحتاج إصلاح")
    CONSUMED = "consumed", _("مستهلكة بالكامل (مهمات وقاية PPE)")
    UNDER_INVESTIGATION = "under_investigation", _("تحت التحقيق الإداري (سرقة/فقدان/تلف)")
    IN_REFURBISHMENT = "in_refurbishment", _("قيد الصيانة والتجهيز الفني")
    SCRAPPED = "scrapped", _("مكهنة ومستبعدة دفترياً")


class AssetCondition(models.TextChoices):
    EXCELLENT = "excellent", _("ممتازة / جديد")
    GOOD = "good", _("جيدة جداً")
    FAIR = "fair", _("مقبولة / مستعملة")
    DAMAGED = "damaged", _("تالفة / معطوبة")


class AssetCategory(models.TextChoices):
    LAPTOP_PC = "laptop_pc", _("أجهزة كمبيوتر ولابتوب")
    MOBILE_TABLET = "mobile_tablet", _("هواتف ذكية وأجهزة لوحية")
    MEASURING_TECH = "measuring_tech", _("أجهزة مساحة وقياس هندسية")
    VEHICLE = "vehicle", _("سيارة / وسيلة انتقال للشركة")
    POWER_TOOL = "power_tool", _("معدات وعدد فنية ثقيلة")
    PPE_SAFETY = "ppe_safety", _("مهمات وقاية وأمان شخصي (PPE)")
    OFFICE_FURNITURE = "office_furniture", _("أثاث مكتبي وأجهزة مكتبية")
    OTHER = "other", _("أخرى")


class EmployeeAssetCustody(models.Model):
    """
    نموذج العهدة العينية المسلمة للموظف
    Employee Physical Equipment & Asset Custody
    """

    custody_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("كود العهدة العينية"),
        help_text=_("ترقيم آلي فريد عبر SequenceService"),
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="asset_custodies",
        verbose_name=_("الموظف المسؤول"),
    )
    work_location = models.ForeignKey(
        "hr.WorkLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asset_custodies",
        verbose_name=_("مقر العمل / الموقع"),
    )
    item_name = models.CharField(
        max_length=200,
        verbose_name=_("اسم الصنف / الجهاز المسلم"),
    )
    category = models.CharField(
        max_length=30,
        choices=AssetCategory.choices,
        default=AssetCategory.LAPTOP_PC,
        verbose_name=_("تصنيف العهدة العينية"),
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("الرقم التسلسلي (Serial Number / Asset Tag)"),
    )
    is_consumable = models.BooleanField(
        default=False,
        verbose_name=_("مهمات مستهلكة (PPE / مستهلكات)"),
        help_text=_("المهمات المستهلكة تسقط تلقائياً بانتهاء عمرها الافتراضي ولا تعطل إخلاء الطرف"),
    )
    expected_lifespan_months = models.PositiveIntegerField(
        default=24,
        verbose_name=_("العمر الافتراضي بالأشهر"),
    )
    delivered_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ التسليم الفعلي للموظف"),
    )
    condition_on_delivery = models.CharField(
        max_length=20,
        choices=AssetCondition.choices,
        default=AssetCondition.GOOD,
        verbose_name=_("حالة الأصل عند التسليم"),
    )
    estimated_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("القيمة الدفترية / التقديرية للأصل"),
    )
    signed_receipt_file = models.FileField(
        upload_to="hr/asset_receipts/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("إقرار استلام العهدة العينية الموقع"),
    )
    status = models.CharField(
        max_length=30,
        choices=AssetCustodyStatus.choices,
        default=AssetCustodyStatus.ACTIVE,
        verbose_name=_("حالة العهدة"),
        db_index=True,
    )
    return_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ الاسترداد الفعلي"),
    )
    return_condition = models.CharField(
        max_length=20,
        choices=AssetCondition.choices,
        null=True,
        blank=True,
        verbose_name=_("حالة الأصل عند الاسترداد"),
    )
    repair_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("تكلفة الإصلاح في حالة التلف"),
    )
    repair_charged_to_employee = models.BooleanField(
        default=False,
        verbose_name=_("تحميل تكلفة الإصلاح على الموظف (استقطاع راتب)"),
    )
    signed_return_file = models.FileField(
        upload_to="hr/asset_returns/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("محضر استرداد العهدة الموقع"),
    )
    investigation_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("وقائع وقرار التحقيق الإداري"),
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات إضافية والمواصفات الفنية"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الإنشاء"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاريخ التحديث"),
    )

    class Meta:
        verbose_name = _("عهدة عينية لموظف")
        verbose_name_plural = _("العهد العينية للأجهزة والمهمات")
        ordering = ["-delivered_date", "-id"]
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["serial_number"]),
        ]

    def __str__(self):
        return f"{self.custody_code} - {self.item_name} ({self.employee.get_full_name() if hasattr(self.employee, 'get_full_name') else self.employee})"


class EmployeeAssetTransfer(models.Model):
    """
    محضر مناقلة أصل عيني ميداني مباشر بين موظفين
    Direct Peer-to-Peer Asset Handover
    """

    transfer_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("كود محضر المناقلة"),
    )
    asset_custody = models.ForeignKey(
        EmployeeAssetCustody,
        on_delete=models.CASCADE,
        related_name="transfers",
        verbose_name=_("الأصل العيني المنقول"),
    )
    from_employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="transferred_assets_out",
        verbose_name=_("الموظف المسلّم"),
    )
    to_employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="transferred_assets_in",
        verbose_name=_("الموظف المستلِم"),
    )
    transfer_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ المناقلة الميدانية"),
    )
    condition = models.CharField(
        max_length=20,
        choices=AssetCondition.choices,
        default=AssetCondition.GOOD,
        verbose_name=_("حالة الأصل وقت المناقلة"),
    )
    signed_transfer_file = models.FileField(
        upload_to="hr/asset_transfers/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("محضر المناقلة الميداني الموقع"),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_asset_transfers",
        verbose_name=_("اعتمد بواسطة (مدير الموقع / الـ HR)"),
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("سبب المناقلة الميدانية"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ التسجيل"),
    )

    class Meta:
        verbose_name = _("محضر مناقلة عهدة عينية")
        verbose_name_plural = _("محاضر مناقلة العهد العينية")
        ordering = ["-transfer_date", "-id"]

    def __str__(self):
        return f"{self.transfer_code} - {self.asset_custody.item_name} (من {self.from_employee} إلى {self.to_employee})"
