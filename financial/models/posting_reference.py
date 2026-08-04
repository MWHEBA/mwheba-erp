from django.db import models
from django.utils.translation import gettext_lazy as _


class FinancialPostingReference(models.Model):
    """
    مرجع الترحيل المالي لضمان عدم التكرار (Financial Posting Idempotency Engine - FIN-CORE-013)
    يضمن عدم تكرار ترحيل المعاملات حتى في حالة تعدد القيود الناتجة عن حدث تشغيلي واحد (مثل: Revenue vs COGS).
    """
    source_type = models.CharField(_("نوع المصدر"), max_length=50)  # e.g., SALE_INVOICE, SALE_PAYMENT
    source_id = models.CharField(_("معرف المصدر"), max_length=100)   # e.g., Invoice ID / Order Number
    posting_type = models.CharField(_("نوع الترحيل"), max_length=50, default="MAIN")  # e.g., MAIN, REVENUE, COGS
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.PROTECT,
        related_name='posting_references',
        verbose_name=_("القيد المحاسبي المتربط")
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("مرجع ترحيل مالي")
        verbose_name_plural = _("مراجع الترحيل المالية")
        constraints = [
            models.UniqueConstraint(
                fields=['source_type', 'source_id', 'posting_type'],
                name='unique_posting_reference_per_source_and_type'
            )
        ]

    def __str__(self):
        return f"{self.source_type}:{self.source_id}:{self.posting_type} -> JE#{self.journal_entry_id}"
