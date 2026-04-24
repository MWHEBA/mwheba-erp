# Financial Module Migration Notes

## AuditTrail Model Migration

**Date:** 2026-02-27

### What Changed
- `financial.models.AuditTrail` has been **removed**
- All audit trail functionality is now unified under `governance.models.AuditTrail`

### Why
- Eliminated duplicate audit trail systems
- Single source of truth for all system auditing
- Better integration with governance and compliance features

### Migration Guide

#### For Code Using AuditTrail

**Before:**
```python
from financial.models import AuditTrail

AuditTrail.log_action(
    action='create',
    entity_type='sale_payment',
    entity_id=payment.id,
    user=request.user,
    description='Payment created'
)
```

**After:**
```python
from governance.models import AuditTrail

AuditTrail.log_operation(
    model_name='sale_payment',
    object_id=payment.id,
    operation='CREATE',
    user=request.user,
    source_service='FinancialService',
    after_data={'description': 'Payment created'}
)
```

#### For PaymentAuditMixin

**Before:**
```python
from financial.models import PaymentAuditMixin
```

**After:**
```python
from financial.mixins import PaymentAuditMixin
```

The mixin interface remains the same, but now uses `governance.models.AuditTrail` internally.

#### For Views and URLs

- `/financial/audit-trail/` → `/governance/audit/`
- Sidebar link updated to point to governance audit management

### Database Migration

If you have existing `financial_audittrail` data, you may want to migrate it to `governance_audittrail`:

```python
# Migration script (run in Django shell)
from financial.models import AuditTrail as OldAudit  # if still exists
from governance.models import AuditTrail as NewAudit

# Map old records to new format
for old_record in OldAudit.objects.all():
    NewAudit.objects.create(
        model_name=old_record.entity_type,
        object_id=old_record.entity_id,
        operation=old_record.action.upper(),
        user=old_record.user,
        timestamp=old_record.timestamp,
        source_service='FinancialService',
        ip_address=old_record.ip_address,
        user_agent=old_record.user_agent,
        after_data={
            'description': old_record.description,
            'old_values': old_record.old_values,
            'new_values': old_record.new_values,
        }
    )
```

### Benefits

1. **Unified Auditing**: All system operations logged in one place
2. **Better Governance**: Integrated with governance dashboard and monitoring
3. **Reduced Complexity**: No duplicate models or views
4. **Enhanced Features**: Access to quarantine, system logs, and advanced filtering
