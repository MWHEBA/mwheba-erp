# -*- coding: utf-8 -*-
"""
نماذج الأدوات النظامية
يحتوي على: SerialNumber (مغلف متوافق مع الكود القديم يستدعي SequenceService)
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class SerialNumber(models.Model):
    """
    نموذج لتتبع الأرقام التسلسلية للمستندات (مع المحافظة على التوافق الرجعي)
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
        توجيه الطلبات لمحرك SequenceService الرئيسي الموحد مع التوافق التام
        """
        from core.services.sequence_service import SequenceService
        from core.enums.document_types import DocumentType

        # Map legacy document type strings to DocumentType Enum
        doc_type_map = {
            "sale": DocumentType.SALES_INVOICE,
            "sales_invoice": DocumentType.SALES_INVOICE,
            "sales_order": DocumentType.SALES_ORDER,
            "delivery_note": DocumentType.DELIVERY_NOTE,
            "purchase": DocumentType.PURCHASE_INVOICE,
            "purchase_order": DocumentType.PURCHASE_ORDER,
            "goods_receipt_note": DocumentType.GOODS_RECEIPT_NOTE,
            "journal_entry": DocumentType.JOURNAL_ENTRY,
            "work_order": DocumentType.SALES_ORDER,
            "stock_movement": DocumentType.STOCK_TRANSFER,
        }

        target_doc_type = doc_type_map.get(document_type, document_type)

        # Convert year to date if passed
        target_date = None
        if year:
            target_date = timezone.datetime(year, 1, 1).date()

        return SequenceService.get_next_number(
            document_type=target_doc_type,
            date=target_date,
        )

    def get_next_number(self):
        """
        للتوافق مع الكود القديم: يستدعي الدالة الذرية الموحدة
        """
        return self.get_next_sequence(self.document_type, prefix=self.prefix, year=self.year)

    def __str__(self):
        return f"{self.document_type} - {self.year} - {self.last_number}"