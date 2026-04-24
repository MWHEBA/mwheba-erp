# Governance System Infrastructure

## Overview

This document describes the governance infrastructure implemented as part of Task 1 of the Code Governance System. The infrastructure provides the foundation for preventing data corruption and ensuring system integrity through centralized control mechanisms.

## Components Implemented

### 1. Core Models (`governance/models.py`)

#### IdempotencyRecord
- **Purpose**: Prevents duplicate operations through unique operation keys
- **Features**: 
  - Thread-safe check and record operations
  - Automatic expiration handling
  - Unique constraints on (operation_type, idempotency_key)
- **Key Methods**: `check_and_record()`, `is_expired()`

#### AuditTrail
- **Purpose**: Comprehensive logging of all sensitive operations
- **Features**:
  - Before/after data capture
  - IP address and user agent tracking
  - Source service identification
  - Thread-safe logging operations
- **Key Methods**: `log_operation()`, `_get_client_ip()`

#### QuarantineRecord
- **Purpose**: Isolates suspicious or corrupted data for investigation
- **Features**:
  - Multiple corruption types support
  - Resolution workflow with notes
  - Status tracking (QUARANTINED → UNDER_REVIEW → RESOLVED)
- **Key Methods**: `resolve()`, status management

#### AuthorityDelegation
- **Purpose**: Manages temporary authority delegation between services
- **Features**:
  - Time-bounded delegations (max 24 hours)
  - Automatic expiration
  - Revocation capabilities
  - Superuser-only creation
- **Key Methods**: `is_valid()`, `revoke()`, `check_delegation()`

#### GovernanceContext
- **Purpose**: Thread-safe context management for governance operations
- **Features**:
  - Thread-local storage for user/service context
  - Safe context management across concurrent requests
- **Key Methods**: `set_context()`, `get_current_user()`, `clear_context()`

### 2. Exception Handling (`governance/exceptions.py`)

Comprehensive exception hierarchy for structured error handling:
- `GovernanceError` - Base exception with context support
- `AuthorityViolationError` - Authority boundary violations
- `ValidationError` - Business rule validation failures
- `ConcurrencyError` - Race conditions and locking failures
- `IdempotencyError` - Duplicate operation attempts
- `QuarantineError` - Data quarantine issues
- `RepairError` - Data repair failures
- `SignalError` - Signal processing issues
- `GatewayError` - Gateway operation failures
- `ConfigurationError` - System configuration issues

### 3. Thread Safety (`governance/thread_safety.py`)

Database-appropriate concurrency control:

#### DatabaseLockManager
- Adapts to different database backends (SQLite vs PostgreSQL)
- Provides `select_for_update()` when supported
- Falls back to atomic transactions for SQLite

#### IdempotencyLock
- Thread-safe idempotency checking with timeout
- Handles lock contention gracefully
- Automatic retry with backoff

#### StockLockManager
- Specialized locking for stock operations
- Prevents negative stock through proper locking
- Creates stock records if missing

#### ConcurrencyMonitor
- Tracks concurrent operations
- Detects high concurrency scenarios
- Provides operation statistics

### 4. Services (`governance/services/`)

#### IdempotencyService
- **Purpose**: Manages idempotency across all governance operations
- **Key Features**:
  - Thread-safe operation checking and recording
  - Standardized key generation methods
  - Cleanup of expired records
  - Operation statistics
- **Key Methods**: 
  - `check_and_record_operation()`
  - `generate_journal_entry_key()`
  - `generate_stock_movement_key()`
  - `cleanup_expired_records()`

#### AuditService
- **Purpose**: Comprehensive audit trail management
- **Key Features**:
  - Structured operation logging
  - Authority violation tracking
  - Admin access logging
  - Gateway operation logging
- **Key Methods**:
  - `log_operation()`
  - `log_authority_violation()`
  - `log_admin_access()`
  - `get_object_history()`

#### QuarantineService
- **Purpose**: Data quarantine and resolution management
- **Key Features**:
  - Safe data isolation
  - Resolution workflow management
  - Corruption type tracking
  - Specialized quarantine methods
- **Key Methods**:
  - `quarantine_data()`
  - `resolve_quarantine()`
  - `quarantine_orphaned_journal_entry()`
  - `quarantine_negative_stock()`

#### AuthorityService
- **Purpose**: Authority boundary enforcement and delegation
- **Key Features**:
  - Authority matrix validation
  - Temporary delegation management
  - Critical model protection
  - Violation logging
- **Key Methods**:
  - `validate_authority()`
  - `delegate_authority()`
  - `revoke_delegation()`
  - `check_delegation()`

### 5. Admin Interface (`governance/admin.py`)

Comprehensive admin interface with:
- Read-only audit trails (immutable)
- Expired record cleanup controls
- Delegation management with revocation
- Quarantine resolution workflow
- Rich data display with JSON formatting
- Security controls (superuser-only delegations)

## Database Schema

### Tables Created
- `governance_idempotencyrecord` - Idempotency tracking
- `governance_audittrail` - Audit logging
- `governance_quarantinerecord` - Data quarantine
- `governance_authoritydelegation` - Authority management

### Indexes
Optimized indexes for:
- Operation type and idempotency key lookups
- Audit trail queries by model, user, and timestamp
- Quarantine record filtering
- Authority delegation validation

## Thread Safety Implementation

### Database-Level Concurrency
- **SQLite**: Atomic transactions with existence checks
- **PostgreSQL**: Row-level locking with `select_for_update()`
- **All Databases**: Idempotency keys as primary concurrency protection

### Context Management
- Thread-local storage for governance context
- Safe concurrent request handling
- Automatic context cleanup

### Monitoring
- Concurrent operation tracking
- High concurrency detection
- Performance monitoring hooks

## Testing

### Basic Functionality Test
- All core models creation and validation
- Service operations verification
- Thread-safety validation
- Exception handling verification

### Test Results
✅ All governance infrastructure components tested successfully
✅ Models create and validate correctly
✅ Services operate as expected
✅ Thread-safety mechanisms function properly

## Integration Points

### Settings Configuration
- Added `governance.apps.GovernanceConfig` to `INSTALLED_APPS`
- Resolved model conflicts with existing financial audit trail

### Database Migration
- Created initial migration `0001_initial.py`
- Applied successfully to database
- All tables and indexes created

## Next Steps

This infrastructure provides the foundation for:
1. **Phase 1**: Authority and Signal Foundation
2. **Phase 2**: Critical Gateway Implementation  
3. **Phase 3**: Admin Panel Security
4. **Phase 4**: Repair Engine Implementation
5. **Phase 5**: Gradual Governance Activation

## Usage Examples

### Basic Idempotency Protection
```python
from governance.services import IdempotencyService

# Generate standardized key
key = IdempotencyService.generate_journal_entry_key(
    'students', 'StudentFee', 123, 'create'
)

# Check and record operation
is_duplicate, record, data = IdempotencyService.check_and_record_operation(
    operation_type='journal_entry',
    idempotency_key=key,
    result_data={'entry_id': 456},
    user=request.user
)

if is_duplicate:
    return data  # Return existing result
```

### Audit Trail Logging
```python
from governance.services import AuditService

# Log operation with full context
AuditService.log_operation(
    model_name='JournalEntry',
    object_id=entry.id,
    operation='CREATE',
    source_service='AccountingGateway',
    user=request.user,
    before_data=None,
    after_data=model_to_dict(entry),
    request=request
)
```

### Authority Validation
```python
from governance.services import AuthorityService

# Validate service authority
try:
    AuthorityService.validate_authority(
        service_name='AccountingGateway',
        model_name='JournalEntry',
        operation='CREATE',
        user=request.user
    )
    # Proceed with operation
except AuthorityViolationError as e:
    # Handle unauthorized access
    logger.error(f"Authority violation: {e}")
    raise PermissionDenied()
```

### Data Quarantine
```python
from governance.services import QuarantineService

# Quarantine corrupted data
QuarantineService.quarantine_orphaned_journal_entry(
    entry_id=entry.id,
    user=request.user
)
```

## Security Considerations

1. **Authority Delegations**: Only superusers can create delegations
2. **Critical Models**: Cannot be delegated during runtime operations
3. **Audit Trails**: Immutable once created
4. **Thread Safety**: All operations are thread-safe
5. **Context Isolation**: Thread-local context prevents cross-request contamination

## Performance Considerations

1. **Database Indexes**: Optimized for common query patterns
2. **Batch Operations**: Cleanup operations use batching
3. **Connection Pooling**: Respects Django's connection management
4. **Memory Usage**: Thread-local storage is automatically cleaned up

## Monitoring and Maintenance

1. **Statistics**: All services provide operation statistics
2. **Cleanup Tasks**: Expired records can be cleaned up periodically
3. **Health Checks**: Authority matrix validation at startup
4. **Logging**: Comprehensive logging for debugging and monitoring

---

**Status**: ✅ COMPLETED - Task 1: Set up governance infrastructure and models

**Next Task**: Task 2: Implement SourceLinkage contract system (Cross-Domain)