# -*- coding: utf-8 -*-
from django.db import models
from django.utils.translation import gettext_lazy as _


class FinancialAccountRole(models.Model):
    """
    سجل أدوار الحسابات المالية بقاعدة البيانات (Priority 1 Dynamic Role Mapping).
    يربط الدور المالي الموحد (مثل bank_charges_expense) بالحساب المحاسبي الفعلي.
    """
    role_name = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name=_("اسم الدور المالي"),
        help_text=_("المعرف الموحد للدور المحاسبي (مثل bank_charges_expense)")
    )
    account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        related_name="assigned_roles",
        verbose_name=_("الحساب المحاسبي المرتبط")
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("وصف الدور المالي")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("نشط")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("تاريخ التحديث"))

    class Meta:
        verbose_name = _("دور محاسبي مالي")
        verbose_name_plural = _("أدوار الحسابات المالية")
        ordering = ["role_name"]

    def __str__(self):
        return f"{self.role_name} -> {self.account.code} ({self.account.name})"

    @property
    def account_code(self) -> str:
        return self.account.code if self.account else ""
