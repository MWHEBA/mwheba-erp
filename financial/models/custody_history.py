"""
نموذج السجل التاريخي لإسناد ومسؤولية صناديق وبطاقات العهد
Custody Assignment History & Audit Continuity
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustodyAssignmentHistory(models.Model):
    """
    سجل تاريخي يوثق فترات تولي كل موظف لصندوق العهدة أو البطاقة البنكية
    لضمان نسبة الحركات التاريخية للمسؤول القانوني عنها بالدقيقة
    """

    account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.CASCADE,
        related_name="assignment_history",
        verbose_name=_("حساب العهدة"),
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="custody_assignment_history",
        verbose_name=_("الموظف المسؤول"),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_assignments_created",
        verbose_name=_("تم الإسناد بواسطة"),
    )
    start_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ استلام العهدة / بدء المسؤولية"),
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ تسليم العهدة / انتهاء المسؤولية"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("المسؤول الحالي النشط"),
    )
    opening_balance_on_handover = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0.00,
        verbose_name=_("الرصيد الفعلي المسلم عند الاستلام"),
    )
    signed_handover_file = models.FileField(
        upload_to="custody/handovers/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("محضر تسليم واستلام العهدة الموقع"),
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات التسليم والتسلم"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ التسجيل بالسيستم"),
    )

    class Meta:
        verbose_name = _("سجل تاريخي لإسناد عهدة")
        verbose_name_plural = _("سجلات إسناد العهد التاريخية")
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["account", "is_active"]),
            models.Index(fields=["employee", "is_active"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.account.name} -> {self.employee} ({self.start_date} إلى {self.end_date or 'الآن'})"
