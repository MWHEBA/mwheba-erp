"""
Financial mixins for models
"""
from django.utils import timezone


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
