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
        ("journal_entry", _("قيد يومي")),
        ("work_order", _("أمر شغل")),
    )

    document_type = models.CharField(
        _("نوع المستند"), max_length=50
    )
    last_number = models.PositiveIntegerField(_("آخر رقم"), default=0)
    prefix = models.CharField(_("بادئة"), max_length=20, blank=True)
    year = models.PositiveIntegerField(_("السنة"), null=True, blank=True)

    class Meta:
        verbose_name = _("رقم تسلسلي")
        verbose_name_plural = _("الأرقام التسلسلية")
        unique_together = ["document_type", "year"]

    @classmethod
    def get_next_sequence(cls, document_type, prefix="", year=None, padding=4):
        """
        الحصول على الرقم التالي في التسلسل بطريقة ذرية موحدة تمنع الـ Race Condition
        وتضمن التوافق التام مع قواعد البيانات المتعددة بدون استعلامات نصية مكررة.
        """
        from django.db import transaction
        if year is None:
            year = timezone.now().year

        with transaction.atomic():
            serial, created = cls.objects.select_for_update().get_or_create(
                document_type=document_type,
                year=year,
                defaults={"prefix": prefix, "last_number": 0}
            )
            serial.last_number += 1
            if prefix and serial.prefix != prefix:
                serial.prefix = prefix
                serial.save(update_fields=["last_number", "prefix"])
            else:
                serial.save(update_fields=["last_number"])

            number_str = str(serial.last_number).zfill(padding)
            return f"{serial.prefix}{number_str}"

    def get_next_number(self):
        """
        للتوافق مع الكود القديم: يستدعي الدالة الذرية الموحدة
        """
        return self.get_next_sequence(self.document_type, prefix=self.prefix, year=self.year)

    def __str__(self):
        return f"{self.document_type} - {self.year} - {self.last_number}"