import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class AllocationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('نشط')
    REVERSED = 'REVERSED', _('ملغى / معكوس')


class PaymentAllocation(models.Model):
    """
    موديل التسويات المالية المخصص (FIN-SUB-001 & FIN-SUB-008)
    يدعم التجريد المالي (Decoupled Financial Allocation) دون الارتباط الصلب بموديولات المبيعات أو الموردين
    """
    allocation_number = models.CharField(
        _("رقم عملية التسوية"),
        max_length=64,
        unique=True,
        editable=False,
        default=uuid.uuid4
    )

    # الربط الاختياري بالعميل أو المورد
    customer = models.ForeignKey(
        'client.Customer',
        on_delete=models.PROTECT,
        verbose_name=_("العميل"),
        null=True,
        blank=True,
        related_name='payment_allocations'
    )
    supplier = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.PROTECT,
        verbose_name=_("المورد"),
        null=True,
        blank=True,
        related_name='payment_allocations'
    )

    # مستند الدفع / المصدر (source_document)
    source_document_type = models.CharField(
        _("نوع مستند المصدر"),
        max_length=64,
        default='PAYMENT',
        help_text=_("مثال: PAYMENT, CREDIT_NOTE, ADVANCE, OPENING_BALANCE")
    )
    source_document_id = models.PositiveIntegerField(
        _("معرف مستند المصدر"),
        default=0
    )

    # مستند الفاتورة / الهدف (target_document)
    target_document_type = models.CharField(
        _("نوع المستند المستهدف"),
        max_length=64,
        default='INVOICE',
        help_text=_("مثال: INVOICE, BILL, DEBIT_NOTE, OPENING_BALANCE")
    )
    target_document_id = models.PositiveIntegerField(
        _("معرف مستند الهدف"),
        default=0
    )

    # مبالغ التسوية وأسعار الصرف (FIN-SUB-008 Cross-Currency Triangulation)
    allocated_amount = models.DecimalField(
        _("المبلغ المخصص بعملة المستند"),
        max_digits=15,
        decimal_places=2
    )
    allocation_currency = models.CharField(
        _("عملة التسوية"),
        max_length=10,
        default="EGP"
    )
    source_exchange_rate = models.DecimalField(
        _("سعر صرف المصدر"),
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000')
    )
    target_exchange_rate = models.DecimalField(
        _("سعر صرف الهدف"),
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000')
    )
    functional_amount = models.DecimalField(
        _("المبلغ الوظيفي بالعملة المحلية"),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    realized_fx_difference = models.DecimalField(
        _("فرق العملة المحقق"),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    allocation_status = models.CharField(
        _("حالة التسوية"),
        max_length=20,
        choices=AllocationStatus.choices,
        default=AllocationStatus.ACTIVE
    )
    allocation_date = models.DateField(
        _("تاريخ التسوية")
    )
    created_at = models.DateTimeField(
        _("تاريخ الإنشاء"),
        auto_now_add=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("تم بواسطة"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("تسوية مالية")
        verbose_name_plural = _("التسويات المالية")
        indexes = [
            models.Index(fields=["source_document_type", "source_document_id"]),
            models.Index(fields=["target_document_type", "target_document_id"]),
            models.Index(fields=["allocation_status"]),
        ]

    def __str__(self):
        return f"Allocation {self.allocation_number} ({self.allocated_amount} {self.allocation_currency})"
