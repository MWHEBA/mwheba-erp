# -*- coding: utf-8 -*-
"""
نماذج الأدوات النظامية
يحتوي على: SerialNumber
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class SerialNumber(models.Model):
    """
    نموذج لتتبع الأرقام التسلسلية للمستندات
    """

    DOCUMENT_TYPES = (
        ("sale", _("فاتورة مبيعات")),
        ("purchase", _("فاتورة مشتريات")),
        ("stock_movement", _("حركة مخزون")),
    )

    document_type = models.CharField(
        _("نوع المستند"), max_length=20, choices=DOCUMENT_TYPES
    )
    last_number = models.PositiveIntegerField(_("آخر رقم"), default=0)
    prefix = models.CharField(_("بادئة"), max_length=10, blank=True)
    year = models.PositiveIntegerField(_("السنة"), null=True, blank=True)

    class Meta:
        verbose_name = _("رقم تسلسلي")
        verbose_name_plural = _("الأرقام التسلسلية")
        unique_together = ["document_type", "year"]

    def get_next_number(self):
        """
        الحصول على الرقم التالي في التسلسل
        """
        # البحث عن آخر رقم مستخدم في هذا النوع من المستندات
        from django.db.models import Max
        from django.apps import apps

        # تحديد النموذج المناسب حسب نوع المستند
        if self.document_type == "sale":
            model = apps.get_model("sale", "Sale")
        elif self.document_type == "purchase":
            model = apps.get_model("purchase", "Purchase")
        else:
            model = apps.get_model("product", "StockMovement")

        # استخراج الرقم من آخر مستند
        last_doc = (
            model.objects.filter(number__startswith=self.prefix)
            .order_by("-number")
            .first()
        )

        if last_doc:
            # استخراج الرقم من آخر مستند
            try:
                last_number = int(last_doc.number.replace(self.prefix, ""))
                self.last_number = max(self.last_number, last_number)
            except ValueError:
                pass

        # زيادة الرقم
        self.last_number += 1
        self.save()
        return self.last_number

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.year} - {self.last_number}"