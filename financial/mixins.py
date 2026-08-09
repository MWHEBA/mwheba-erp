from django.utils import timezone
from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class MonetaryTransactionMixin(models.Model):
    """
    Mixin معاري قياسي لتوحيد حقول العملات والمبالغ المستندية والوظيفية
    """
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        verbose_name=_("العملة"),
        null=True,
        blank=True,
    )
    transaction_amount = models.DecimalField(
        _("مبلغ المعاملة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    exchange_rate_snapshot = models.DecimalField(
        _("لقطة سعر الصرف"),
        max_digits=12,
        decimal_places=6,
        default=Decimal("1.000000"),
    )
    base_amount = models.DecimalField(
        _("المبلغ بالعملة الأساسية (EGP)"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        abstract = True

    def populate_monetary_fields(self):
        """تعبئة تلقائية لمعادلات مبالغ العملات المستندية والأساسية"""
        if not self.currency_id:
            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                func_curr = ExchangeRateService.get_functional_currency()
                if func_curr:
                    self.currency = func_curr
            except Exception:
                pass

        if hasattr(self, 'amount') and (not self.transaction_amount or self.transaction_amount == Decimal("0.00")):
            if self.amount:
                self.transaction_amount = Decimal(str(self.amount))

        if not self.exchange_rate_snapshot or self.exchange_rate_snapshot == Decimal("0.00"):
            if self.currency and not getattr(self.currency, 'is_functional', False):
                try:
                    from financial.services.exchange_rate_service import ExchangeRateService
                    rate = ExchangeRateService.get_rate(self.currency)
                    if rate:
                        self.exchange_rate_snapshot = rate
                    else:
                        self.exchange_rate_snapshot = Decimal("1.000000")
                except Exception:
                    self.exchange_rate_snapshot = Decimal("1.000000")
            else:
                self.exchange_rate_snapshot = Decimal("1.000000")

        if self.transaction_amount:
            self.base_amount = (Decimal(str(self.transaction_amount)) * Decimal(str(self.exchange_rate_snapshot))).quantize(Decimal("0.01"))
            if hasattr(self, 'amount'):
                self.amount = Decimal(str(self.transaction_amount))



class PaymentAuditMixin:
    """
    Mixin for adding audit functionality to payment models
    Uses governance.models.AuditTrail for logging
    """

    def log_payment_action(
        self,
        action: str,
        user,
        description: str,
        reason: str = "",
        request=None,
        **kwargs,
    ):
        """Log payment operation using governance audit trail"""
        from governance.models import AuditTrail
        
        # Determine entity type
        if hasattr(self, "sale"):
            entity_type = "sale_payment"
            entity_name = f"دفعة مبيعات - فاتورة {self.sale.number}"
        elif hasattr(self, "purchase"):
            entity_type = "purchase_payment"
            entity_name = f"دفعة مشتريات - فاتورة {self.purchase.number}"
        else:
            entity_type = "payment"
            entity_name = f"دفعة #{self.id}"

        # Additional metadata
        metadata = {
            "payment_id": self.id,
            "amount": float(self.amount),
            "payment_method": self.payment_method,
            "financial_status": getattr(self, 'financial_status', None),
            "status": getattr(self, 'status', None),
            **kwargs,
        }

        # Map action to governance operation
        operation_map = {
            'create': 'CREATE',
            'update': 'UPDATE',
            'delete': 'DELETE',
            'post': 'UPDATE',
            'unpost': 'UPDATE',
            'sync': 'UPDATE',
            'unsync': 'UPDATE',
            'approve': 'UPDATE',
            'reject': 'UPDATE',
            'cancel': 'UPDATE',
        }
        
        operation = operation_map.get(action, 'UPDATE')

        return AuditTrail.log_operation(
            model_name=entity_type,
            object_id=self.id,
            operation=operation,
            user=user,
            source_service='FinancialService',
            after_data=metadata,
            request=request,
            action_type=action,
            description=description,
            reason=reason,
        )

    def get_audit_history(self):
        """Get audit history for this payment"""
        from governance.models import AuditTrail
        
        entity_type = "sale_payment" if hasattr(self, "sale") else "purchase_payment"
        return AuditTrail.objects.filter(
            model_name=entity_type,
            object_id=self.id
        ).order_by('-timestamp')
