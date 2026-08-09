from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .procurement_models import GoodsReceivedNote
from financial.models.journal_entry import JournalEntry


class GRNPostingLog(models.Model):
    """
    سجل تتبع الترحيل المالي والمخزني المزدوج (GRN Posting Control Log)
    يربط بين إذن الاستلام والقيد المحاسبي وحركات المستودع المباشرة
    """
    grn = models.ForeignKey(
        GoodsReceivedNote,
        on_delete=models.CASCADE,
        related_name="posting_logs",
        verbose_name=_("إذن الاستلام")
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد المحاسبي")
    )
    stock_movements_count = models.PositiveIntegerField(_("عدد حركات المخزون"), default=0)
    total_posted_value = models.DecimalField(_("إجمالي قيمة الترحيل"), max_digits=15, decimal_places=2, default=0.00)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("تم الترحيل بواسطة")
    )
    posted_at = models.DateTimeField(_("تاريخ وتوقيت الترحيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل ترحيل إذن استلام")
        verbose_name_plural = _("سجلات ترحيل أذون الاستلام")
        ordering = ["-posted_at", "-id"]

    def __str__(self):
        return f"GRN Posting Log #{self.id} for GRN #{self.grn.grn_number}"
