"""
Repair Policy Framework - NO EXECUTION Phase 4A

This module implements the repair policy framework for the Code Governance System.
It defines repair policies, verification mechanisms, and rollback strategies
WITHOUT executing any repairs. This is analysis and planning only.

Key Features:
- RELINK/QUARANTINE/REBUILD/ADJUSTMENT policy definitions
- Verification and rollback mechanisms (framework only)
- Policy compliance validation
- Risk assessment and approval workflows
- NO automatic execution - requires explicit approval
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from ..models import AuditTrail, QuarantineRecord, GovernanceContext
from ..thread_safety import monitor_operation
from ..exceptions import GovernanceError

User = get_user_model()
logger = logging.getLogger(__name__)


class RepairPolicyType(Enum):
    """Enumeration of repair policy types"""
    RELINK = "RELINK"
    QUARANTINE = "QUARANTINE"
    REBUILD = "REBUILD"
    ADJUSTMENT = "ADJUSTMENT"


class ConfidenceLevel(Enum):
    """Enumeration of confidence levels"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RepairStatus(Enum):
    """Enumeration of repair operation status"""
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class RepairAction:
    """
    Defines a specific repair action within a repair plan.
    Framework only - NO EXECUTION.
    """
    action_id: str
    action_type: str
    description: str
    target_model: str
    target_objects: List[int]
    parameters: Dict[str, Any] = field(default_factory=dict)
    prerequisites: List[str] = field(default_factory=list)
    validation_rules: List[str] = field(default_factory=list)
    rollback_strategy: Optional[str] = None
    estimated_duration: Optional[timedelta] = None
    risk_level: str = "MEDIUM"
    
    def to_dict(self) -> Dict:
        """Convert repair action to dictionary"""
        return {
            'action_id': self.action_id,
            'action_type': self.action_type,
            'description': self.description,
            'target_model': self.target_model,
            'target_objects': self.target_objects,
            'parameters': self.parameters,
            'prerequisites': self.prerequisites,
            'validation_rules': self.validation_rules,
            'rollback_strategy': self.rollback_strategy,
            'estimated_duration': str(self.estimated_duration) if self.estimated_duration else None,
            'risk_level': self.risk_level
        }


@dataclass
class VerificationInvariant:
    """
    Defines an invariant that must hold after repair completion.
    """
    invariant_id: str
    description: str
    validation_query: str
    expected_result: Any
    tolerance: Optional[float] = None
    critical: bool = True
    
    def to_dict(self) -> Dict:
        """Convert verification invariant to dictionary"""
        return {
            'invariant_id': self.invariant_id,
            'description': self.description,
            'validation_query': self.validation_query,
            'expected_result': self.expected_result,
            'tolerance': self.tolerance,
            'critical': self.critical
        }


@dataclass
class RollbackStrategy:
    """
    Defines rollback strategy for repair operations.
    Framework only - NO EXECUTION.
    """
    strategy_id: str
    strategy_type: str  # SNAPSHOT, TRANSACTION, MANUAL
    description: str
    rollback_actions: List[Dict] = field(default_factory=list)
    verification_steps: List[str] = field(default_factory=list)
    recovery_time_estimate: Optional[timedelta] = None
    data_loss_risk: str = "NONE"  # NONE, MINIMAL, MODERATE, HIGH
    
    def to_dict(self) -> Dict:
        """Convert rollback strategy to dictionary"""
        return {
            'strategy_id': self.strategy_id,
            'strategy_type': self.strategy_type,
            'description': self.description,
            'rollback_actions': self.rollback_actions,
            'verification_steps': self.verification_steps,
            'recovery_time_estimate': str(self.recovery_time_estimate) if self.recovery_time_estimate else None,
            'data_loss_risk': self.data_loss_risk
        }


class RepairPolicyFramework:
    """
    Comprehensive repair policy framework for corruption handling.
    Framework only - NO EXECUTION in Phase 4A.
    """
    
    def __init__(self):
        self.policies = self._initialize_policies()
        self.verification_templates = self._initialize_verification_templates()
        self.rollback_templates = self._initialize_rollback_templates()
    
    def _initialize_policies(self) -> Dict[str, Dict]:
        """Initialize repair policy matrix"""
        return {
            'ORPHANED_JOURNAL_ENTRIES': {
                ConfidenceLevel.HIGH: {
                    'policy': RepairPolicyType.RELINK,
                    'description': 'High confidence orphaned entries can be relinked to sources',
                    'risk_level': 'LOW',
                    'approval_required': False,
                    'batch_size': 50,
                    'verification_required': True
                },
                ConfidenceLevel.MEDIUM: {
                    'policy': RepairPolicyType.QUARANTINE,
                    'description': 'Medium confidence entries should be quarantined for review',
                    'risk_level': 'MEDIUM',
                    'approval_required': True,
                    'batch_size': 25,
                    'verification_required': True
                },
                ConfidenceLevel.LOW: {
                    'policy': RepairPolicyType.QUARANTINE,
                    'description': 'Low confidence entries require manual investigation',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 10,
                    'verification_required': True
                }
            },
            'NEGATIVE_STOCK': {
                ConfidenceLevel.HIGH: {
                    'policy': RepairPolicyType.ADJUSTMENT,
                    'description': 'Adjust negative stock to zero with movement record',
                    'risk_level': 'MEDIUM',
                    'approval_required': True,
                    'batch_size': 20,
                    'verification_required': True
                },
                ConfidenceLevel.MEDIUM: {
                    'policy': RepairPolicyType.ADJUSTMENT,
                    'description': 'Adjust negative stock with additional validation',
                    'risk_level': 'MEDIUM',
                    'approval_required': True,
                    'batch_size': 10,
                    'verification_required': True
                },
                ConfidenceLevel.LOW: {
                    'policy': RepairPolicyType.QUARANTINE,
                    'description': 'Quarantine suspicious negative stock for investigation',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 5,
                    'verification_required': True
                }
            },
            'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS': {
                ConfidenceLevel.HIGH: {
                    'policy': RepairPolicyType.REBUILD,
                    'description': 'Rebuild accounting period status from business rules',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 1,
                    'verification_required': True
                },
                ConfidenceLevel.MEDIUM: {
                    'policy': RepairPolicyType.REBUILD,
                    'description': 'Rebuild with additional validation checks',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 1,
                    'verification_required': True
                },
                ConfidenceLevel.LOW: {
                    'policy': RepairPolicyType.QUARANTINE,
                    'description': 'Quarantine conflicting periods for manual resolution',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 1,
                    'verification_required': True
                }
            },
            'UNBALANCED_JOURNAL_ENTRIES': {
                ConfidenceLevel.HIGH: {
                    'policy': RepairPolicyType.ADJUSTMENT,
                    'description': 'Adjust journal entry to balance debits and credits',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 5,
                    'verification_required': True
                },
                ConfidenceLevel.MEDIUM: {
                    'policy': RepairPolicyType.QUARANTINE,
                    'description': 'Quarantine unbalanced entries for manual review',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 5,
                    'verification_required': True
                },
                ConfidenceLevel.LOW: {
                    'policy': RepairPolicyType.QUARANTINE,
                    'description': 'Quarantine suspicious entries for investigation',
                    'risk_level': 'HIGH',
                    'approval_required': True,
                    'batch_size': 1,
                    'verification_required': True
                }
            }
        }
    
    def _initialize_verification_templates(self) -> Dict[str, List[VerificationInvariant]]:
        """Initialize verification invariant templates"""
        return {
            'ORPHANED_JOURNAL_ENTRIES': [
                VerificationInvariant(
                    invariant_id='OJE_001',
                    description='All journal entries have valid source references',
                    validation_query='SELECT COUNT(*) FROM finance_journalentry WHERE source_module IS NULL OR source_model IS NULL OR source_id IS NULL',
                    expected_result=0,
                    critical=True
                ),
                VerificationInvariant(
                    invariant_id='OJE_002',
                    description='No orphaned entries remain after repair',
                    validation_query='SELECT COUNT(*) FROM finance_journalentry je LEFT JOIN {source_table} st ON je.source_id = st.id WHERE st.id IS NULL',
                    expected_result=0,
                    critical=True
                ),
                VerificationInvariant(
                    invariant_id='OJE_003',
                    description='Source linkage references exist in target tables',
                    validation_query='SELECT COUNT(*) FROM finance_journalentry WHERE NOT EXISTS (SELECT 1 FROM {source_table} WHERE id = source_id)',
                    expected_result=0,
                    critical=True
                )
            ],
            'NEGATIVE_STOCK': [
                VerificationInvariant(
                    invariant_id='NS_001',
                    description='All stock quantities are non-negative',
                    validation_query='SELECT COUNT(*) FROM product_stock WHERE quantity < 0',
                    expected_result=0,
                    critical=True
                ),
                VerificationInvariant(
                    invariant_id='NS_002',
                    description='Stock movements balance correctly',
                    validation_query='SELECT COUNT(*) FROM product_stock s WHERE s.quantity != (SELECT COALESCE(SUM(sm.quantity_change), 0) FROM product_stockmovement sm WHERE sm.product_id = s.product_id)',
                    expected_result=0,
                    tolerance=0.01,
                    critical=True
                ),
                VerificationInvariant(
                    invariant_id='NS_003',
                    description='Adjustment movements have proper documentation',
                    validation_query='SELECT COUNT(*) FROM product_stockmovement WHERE movement_type = "ADJUSTMENT" AND (notes IS NULL OR notes = "")',
                    expected_result=0,
                    critical=False
                )
            ],
            'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS': [
                VerificationInvariant(
                    invariant_id='MAP_001',
                    description='No overlapping active accounting periods',
                    validation_query='SELECT COUNT(*) FROM financial_accountingperiod p1 JOIN financial_accountingperiod p2 ON p1.id != p2.id WHERE p1.is_active = TRUE AND p2.is_active = TRUE',
                    expected_result=0,
                    critical=True
                ),
            ],
            'UNBALANCED_JOURNAL_ENTRIES': [
                VerificationInvariant(
                    invariant_id='UJE_001',
                    description='All journal entries are balanced',
                    validation_query='SELECT COUNT(*) FROM finance_journalentry je WHERE ABS((SELECT COALESCE(SUM(debit_amount), 0) FROM finance_journalentryline WHERE journal_entry_id = je.id) - (SELECT COALESCE(SUM(credit_amount), 0) FROM finance_journalentryline WHERE journal_entry_id = je.id)) > 0.01',
                    expected_result=0,
                    tolerance=0.01,
                    critical=True
                ),
                VerificationInvariant(
                    invariant_id='UJE_002',
                    description='No journal entries have zero total amounts',
                    validation_query='SELECT COUNT(*) FROM finance_journalentry je WHERE (SELECT COALESCE(SUM(debit_amount), 0) + COALESCE(SUM(credit_amount), 0) FROM finance_journalentryline WHERE journal_entry_id = je.id) = 0',
                    expected_result=0,
                    critical=False
                )
            ]
        }
    
    def _initialize_rollback_templates(self) -> Dict[str, RollbackStrategy]:
        """Initialize rollback strategy templates"""
        return {
            'RELINK_ROLLBACK': RollbackStrategy(
                strategy_id='RB_RELINK_001',
                strategy_type='TRANSACTION',
                description='Rollback journal entry relinking operations',
                rollback_actions=[
                    {
                        'action': 'RESTORE_ORIGINAL_LINKAGE',
                        'description': 'Restore original source linkage values',
                        'sql': 'UPDATE finance_journalentry SET source_module = ?, source_model = ?, source_id = ? WHERE id = ?'
                    },
                    {
                        'action': 'REMOVE_AUDIT_RECORDS',
                        'description': 'Remove audit records created during repair',
                        'sql': 'DELETE FROM governance_audittrail WHERE source_service = "RepairService" AND operation = "RELINK" AND timestamp >= ?'
                    }
                ],
                verification_steps=[
                    'Verify original linkage values are restored',
                    'Confirm no data corruption introduced',
                    'Validate audit trail consistency'
                ],
                recovery_time_estimate=timedelta(minutes=15),
                data_loss_risk='NONE'
            ),
            'ADJUSTMENT_ROLLBACK': RollbackStrategy(
                strategy_id='RB_ADJUSTMENT_001',
                strategy_type='SNAPSHOT',
                description='Rollback stock and journal entry adjustments',
                rollback_actions=[
                    {
                        'action': 'RESTORE_STOCK_QUANTITIES',
                        'description': 'Restore original stock quantities from snapshot',
                        'sql': 'UPDATE product_stock SET quantity = ? WHERE id = ?'
                    },
                    {
                        'action': 'REMOVE_ADJUSTMENT_MOVEMENTS',
                        'description': 'Remove adjustment movements created during repair',
                        'sql': 'DELETE FROM product_stockmovement WHERE movement_type = "REPAIR_ADJUSTMENT" AND created_at >= ?'
                    },
                    {
                        'action': 'REMOVE_ADJUSTMENT_JOURNAL_ENTRIES',
                        'description': 'Remove journal entries created for adjustments',
                        'sql': 'DELETE FROM finance_journalentry WHERE source_module = "RepairService" AND created_at >= ?'
                    }
                ],
                verification_steps=[
                    'Verify stock quantities match pre-repair snapshot',
                    'Confirm adjustment movements are removed',
                    'Validate journal entry consistency'
                ],
                recovery_time_estimate=timedelta(minutes=30),
                data_loss_risk='MINIMAL'
            ),
            'REBUILD_ROLLBACK': RollbackStrategy(
                strategy_id='RB_REBUILD_001',
                strategy_type='MANUAL',
                description='Rollback accounting period rebuild operations',
                rollback_actions=[
                    {
                        'action': 'RESTORE_PERIOD_STATUS',
                        'description': 'Manually restore accounting period active status',
                        'sql': 'UPDATE financial_accountingperiod SET is_active = ? WHERE id = ?'
                    },
                    {
                        'action': 'VALIDATE_BUSINESS_RULES',
                        'description': 'Manually validate business rule compliance',
                        'sql': 'SELECT * FROM financial_accountingperiod WHERE is_active = TRUE'
                    }
                ],
                verification_steps=[
                    'Manually verify accounting period status is correct',
                    'Confirm business rules are satisfied',
                    'Validate financial transaction consistency'
                ],
                recovery_time_estimate=timedelta(hours=2),
                data_loss_risk='MODERATE'
            ),
            'QUARANTINE_ROLLBACK': RollbackStrategy(
                strategy_id='RB_QUARANTINE_001',
                strategy_type='TRANSACTION',
                description='Rollback quarantine operations',
                rollback_actions=[
                    {
                        'action': 'RESTORE_FROM_QUARANTINE',
                        'description': 'Restore data from quarantine records',
                        'sql': 'UPDATE {target_table} SET {fields} WHERE id = ?'
                    },
                    {
                        'action': 'REMOVE_QUARANTINE_RECORDS',
                        'description': 'Remove quarantine records created during repair',
                        'sql': 'DELETE FROM governance_quarantinerecord WHERE quarantined_at >= ? AND corruption_type = ?'
                    }
                ],
                verification_steps=[
                    'Verify data is restored from quarantine',
                    'Confirm quarantine records are cleaned up',
                    'Validate data integrity'
                ],
                recovery_time_estimate=timedelta(minutes=10),
                data_loss_risk='NONE'
            )
        }
    
    def get_policy(self, corruption_type: str, confidence: ConfidenceLevel) -> Dict:
        """
        Get repair policy for corruption type and confidence level.
        
        Args:
            corruption_type: Type of corruption
            confidence: Confidence level
            
        Returns:
            Dict: Policy configuration
        """
        policies = self.policies.get(corruption_type, {})
        return policies.get(confidence, {
            'policy': RepairPolicyType.QUARANTINE,
            'description': 'Default quarantine policy for unknown corruption',
            'risk_level': 'HIGH',
            'approval_required': True,
            'batch_size': 1,
            'verification_required': True
        })
    
    def create_repair_plan(self, corruption_type: str, confidence: ConfidenceLevel, 
                          corrupted_objects: List[Dict]) -> 'DetailedRepairPlan':
        """
        Create detailed repair plan for specific corruption.
        Framework only - NO EXECUTION.
        
        Args:
            corruption_type: Type of corruption
            confidence: Confidence level
            corrupted_objects: List of corrupted objects
            
        Returns:
            DetailedRepairPlan: Comprehensive repair plan
        """
        policy_config = self.get_policy(corruption_type, confidence)
        policy_type = policy_config['policy']
        
        # Create repair actions based on policy type
        repair_actions = self._create_repair_actions(
            corruption_type, policy_type, corrupted_objects, policy_config
        )
        
        # Get verification invariants
        verification_invariants = self.verification_templates.get(corruption_type, [])
        
        # Get rollback strategy
        rollback_strategy = self._get_rollback_strategy(policy_type)
        
        # Create detailed repair plan
        plan = DetailedRepairPlan(
            corruption_type=corruption_type,
            policy_type=policy_type,
            confidence=confidence,
            repair_actions=repair_actions,
            verification_invariants=verification_invariants,
            rollback_strategy=rollback_strategy,
            policy_config=policy_config,
            affected_objects_count=len(corrupted_objects),
            estimated_duration=self._estimate_repair_duration(repair_actions),
            risk_assessment=self._assess_repair_risk(corruption_type, policy_type, len(corrupted_objects))
        )
        
        return plan
    
    def _create_repair_actions(self, corruption_type: str, policy_type: RepairPolicyType, 
                             corrupted_objects: List[Dict], policy_config: Dict) -> List[RepairAction]:
        """Create specific repair actions based on policy type"""
        actions = []
        batch_size = policy_config.get('batch_size', 10)
        
        if policy_type == RepairPolicyType.RELINK:
            actions.extend(self._create_relink_actions(corruption_type, corrupted_objects, batch_size))
        elif policy_type == RepairPolicyType.QUARANTINE:
            actions.extend(self._create_quarantine_actions(corruption_type, corrupted_objects, batch_size))
        elif policy_type == RepairPolicyType.REBUILD:
            actions.extend(self._create_rebuild_actions(corruption_type, corrupted_objects, batch_size))
        elif policy_type == RepairPolicyType.ADJUSTMENT:
            actions.extend(self._create_adjustment_actions(corruption_type, corrupted_objects, batch_size))
        
        return actions
    
    def _create_relink_actions(self, corruption_type: str, corrupted_objects: List[Dict], 
                             batch_size: int) -> List[RepairAction]:
        """Create relink repair actions"""
        actions = []
        
        if corruption_type == 'ORPHANED_JOURNAL_ENTRIES':
            # Group objects into batches
            for i in range(0, len(corrupted_objects), batch_size):
                batch = corrupted_objects[i:i + batch_size]
                object_ids = []
                for obj in batch:
                    entry_id = obj.get('entry_id')
                    if entry_id is not None:
                        object_ids.append(entry_id)
                    else:
                        # Handle objects without entry_id (e.g., scan errors)
                        logger.warning(f"Object missing entry_id in relink batch: {obj}")
                
                if not object_ids:
                    # Skip batch if no valid entry IDs
                    continue
                
                action = RepairAction(
                    action_id=f'RELINK_JE_BATCH_{i // batch_size + 1}',
                    action_type='RELINK_JOURNAL_ENTRIES',
                    description=f'Relink {len(batch)} orphaned journal entries to their sources',
                    target_model='JournalEntry',
                    target_objects=object_ids,
                    parameters={
                        'validation_method': 'SOURCE_LINKAGE_SERVICE',
                        'fallback_policy': 'QUARANTINE_ON_FAILURE',
                        'batch_size': len(batch)
                    },
                    prerequisites=[
                        'Verify source records exist',
                        'Validate source linkage allowlist',
                        'Check for duplicate linkages'
                    ],
                    validation_rules=[
                        'Source module must be in allowlist',
                        'Source record must exist',
                        'No duplicate source linkages allowed'
                    ],
                    rollback_strategy='TRANSACTION',
                    estimated_duration=timedelta(minutes=5 * len(batch)),
                    risk_level='LOW'
                )
                actions.append(action)
        
        return actions
    
    def _create_quarantine_actions(self, corruption_type: str, corrupted_objects: List[Dict], 
                                 batch_size: int) -> List[RepairAction]:
        """Create quarantine repair actions"""
        actions = []
        
        # Group objects into batches
        for i in range(0, len(corrupted_objects), batch_size):
            batch = corrupted_objects[i:i + batch_size]
            
            # Determine target model and object IDs based on corruption type
            if corruption_type == 'ORPHANED_JOURNAL_ENTRIES':
                target_model = 'JournalEntry'
                object_ids = []
                for obj in batch:
                    entry_id = obj.get('entry_id')
                    if entry_id is not None:
                        object_ids.append(entry_id)
            elif corruption_type == 'NEGATIVE_STOCK':
                target_model = 'Stock'
                object_ids = []
                for obj in batch:
                    stock_id = obj.get('stock_id')
                    if stock_id is not None:
                        object_ids.append(stock_id)
            elif corruption_type == 'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS':
                target_model = 'AccountingPeriod'
                object_ids = []
                for obj in batch:
                    period_id = obj.get('period_id')
                    if period_id is not None:
                        object_ids.append(period_id)
            else:
                target_model = 'Unknown'
                object_ids = [obj.get('id', 0) for obj in batch]
            
            action = RepairAction(
                action_id=f'QUARANTINE_{corruption_type}_BATCH_{i // batch_size + 1}',
                action_type='QUARANTINE_OBJECTS',
                description=f'Quarantine {len(batch)} {corruption_type.lower()} objects for manual review',
                target_model=target_model,
                target_objects=object_ids,
                parameters={
                    'corruption_type': corruption_type,
                    'quarantine_reason': f'Detected during corruption scan',
                    'batch_size': len(batch)
                },
                prerequisites=[
                    'Verify objects exist',
                    'Check quarantine capacity',
                    'Prepare quarantine documentation'
                ],
                validation_rules=[
                    'Objects must exist before quarantine',
                    'Quarantine records must be created',
                    'Original data must be preserved'
                ],
                rollback_strategy='TRANSACTION',
                estimated_duration=timedelta(minutes=2 * len(batch)),
                risk_level='LOW'
            )
            actions.append(action)
        
        return actions
    
    def _create_rebuild_actions(self, corruption_type: str, corrupted_objects: List[Dict], 
                              batch_size: int) -> List[RepairAction]:
        """Create rebuild repair actions"""
        actions = []
        
        if corruption_type == 'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS':
            action = RepairAction(
                action_id='REBUILD_ACCOUNTING_PERIOD_STATUS',
                action_type='REBUILD_PERIOD_STATUS',
                description='Rebuild accounting period active status from business rules',
                target_model='AccountingPeriod',
                target_objects=[obj.get('period_id', 0) for obj in corrupted_objects],
                parameters={
                    'rebuild_method': 'BUSINESS_RULE_BASED',
                    'current_date_check': True,
                },
                prerequisites=[
                    'Backup current accounting period data',
                    'Validate business rules',
                    'Check financial transaction dependencies'
                ],
                validation_rules=[
                    'Only one period can be open at a time',
                    'Open period must cover current date',
                    'No transaction conflicts'
                ],
                rollback_strategy='MANUAL',
                estimated_duration=timedelta(hours=1),
                risk_level='HIGH'
            )
            actions.append(action)
        
        return actions
    
    def _create_adjustment_actions(self, corruption_type: str, corrupted_objects: List[Dict], 
                                 batch_size: int) -> List[RepairAction]:
        """Create adjustment repair actions"""
        actions = []
        
        if corruption_type == 'NEGATIVE_STOCK':
            # Group objects into batches
            for i in range(0, len(corrupted_objects), batch_size):
                batch = corrupted_objects[i:i + batch_size]
                object_ids = [obj['stock_id'] for obj in batch]
                
                action = RepairAction(
                    action_id=f'ADJUST_NEGATIVE_STOCK_BATCH_{i // batch_size + 1}',
                    action_type='ADJUST_STOCK_QUANTITIES',
                    description=f'Adjust {len(batch)} negative stock quantities to zero',
                    target_model='Stock',
                    target_objects=object_ids,
                    parameters={
                        'adjustment_method': 'SET_TO_ZERO',
                        'create_movement_record': True,
                        'create_journal_entry': True,
                        'batch_size': len(batch)
                    },
                    prerequisites=[
                        'Backup stock quantities',
                        'Prepare adjustment movements',
                        'Validate accounting impact'
                    ],
                    validation_rules=[
                        'Stock quantities must be non-negative after adjustment',
                        'Movement records must be created',
                        'Journal entries must balance'
                    ],
                    rollback_strategy='SNAPSHOT',
                    estimated_duration=timedelta(minutes=10 * len(batch)),
                    risk_level='MEDIUM'
                )
                actions.append(action)
        
        elif corruption_type == 'UNBALANCED_JOURNAL_ENTRIES':
            # Group objects into batches
            for i in range(0, len(corrupted_objects), batch_size):
                batch = corrupted_objects[i:i + batch_size]
                object_ids = [obj['entry_id'] for obj in batch]
                
                action = RepairAction(
                    action_id=f'BALANCE_JOURNAL_ENTRIES_BATCH_{i // batch_size + 1}',
                    action_type='BALANCE_JOURNAL_ENTRIES',
                    description=f'Balance {len(batch)} unbalanced journal entries',
                    target_model='JournalEntry',
                    target_objects=object_ids,
                    parameters={
                        'balancing_method': 'ADD_BALANCING_LINE',
                        'balancing_account': 'SUSPENSE_ACCOUNT',
                        'require_approval': True,
                        'batch_size': len(batch)
                    },
                    prerequisites=[
                        'Backup journal entry data',
                        'Identify balancing accounts',
                        'Calculate adjustment amounts'
                    ],
                    validation_rules=[
                        'Debits must equal credits after adjustment',
                        'Balancing lines must be documented',
                        'Suspense account must exist'
                    ],
                    rollback_strategy='TRANSACTION',
                    estimated_duration=timedelta(minutes=15 * len(batch)),
                    risk_level='HIGH'
                )
                actions.append(action)
        
        return actions
    
    def _get_rollback_strategy(self, policy_type: RepairPolicyType) -> RollbackStrategy:
        """Get appropriate rollback strategy for policy type"""
        strategy_mapping = {
            RepairPolicyType.RELINK: 'RELINK_ROLLBACK',
            RepairPolicyType.QUARANTINE: 'QUARANTINE_ROLLBACK',
            RepairPolicyType.REBUILD: 'REBUILD_ROLLBACK',
            RepairPolicyType.ADJUSTMENT: 'ADJUSTMENT_ROLLBACK'
        }
        
        strategy_key = strategy_mapping.get(policy_type, 'QUARANTINE_ROLLBACK')
        return self.rollback_templates[strategy_key]
    
    def _estimate_repair_duration(self, repair_actions: List[RepairAction]) -> timedelta:
        """Estimate total duration for repair actions"""
        total_duration = timedelta()
        for action in repair_actions:
            if action.estimated_duration:
                total_duration += action.estimated_duration
        return total_duration
    
    def _assess_repair_risk(self, corruption_type: str, policy_type: RepairPolicyType, 
                          object_count: int) -> Dict:
        """Assess risk level for repair operation"""
        base_risk = {
            RepairPolicyType.QUARANTINE: 'LOW',
            RepairPolicyType.RELINK: 'LOW',
            RepairPolicyType.ADJUSTMENT: 'MEDIUM',
            RepairPolicyType.REBUILD: 'HIGH'
        }.get(policy_type, 'HIGH')
        
        # Adjust risk based on object count
        if object_count > 100:
            risk_levels = {'LOW': 'MEDIUM', 'MEDIUM': 'HIGH', 'HIGH': 'CRITICAL'}
            base_risk = risk_levels.get(base_risk, 'CRITICAL')
        elif object_count > 50:
            risk_levels = {'LOW': 'MEDIUM', 'MEDIUM': 'HIGH'}
            base_risk = risk_levels.get(base_risk, base_risk)
        
        return {
            'overall_risk': base_risk,
            'factors': {
                'policy_type': policy_type.value,
                'object_count': object_count,
                'corruption_type': corruption_type
            },
            'mitigation_required': base_risk in ['HIGH', 'CRITICAL'],
            'approval_required': True,
            'testing_required': base_risk != 'LOW'
        }
    
    def validate_policy_compliance(self, repair_plan: 'DetailedRepairPlan') -> Dict:
        """
        Validate repair plan compliance with policies.
        Framework only - NO EXECUTION.
        
        Args:
            repair_plan: Repair plan to validate
            
        Returns:
            Dict: Compliance validation results
        """
        compliance_results = {
            'is_compliant': True,
            'violations': [],
            'warnings': [],
            'recommendations': []
        }
        
        # Check policy matrix compliance
        expected_policy = self.get_policy(repair_plan.corruption_type, repair_plan.confidence)
        if repair_plan.policy_type != expected_policy['policy']:
            compliance_results['violations'].append({
                'type': 'POLICY_MISMATCH',
                'description': f'Plan uses {repair_plan.policy_type.value} but policy matrix recommends {expected_policy["policy"].value}',
                'severity': 'HIGH'
            })
            compliance_results['is_compliant'] = False
        
        # Check batch size compliance
        for action in repair_plan.repair_actions:
            if len(action.target_objects) > expected_policy.get('batch_size', 10):
                compliance_results['warnings'].append({
                    'type': 'BATCH_SIZE_EXCEEDED',
                    'description': f'Action {action.action_id} exceeds recommended batch size',
                    'severity': 'MEDIUM'
                })
        
        # Check verification requirements
        if expected_policy.get('verification_required', True) and not repair_plan.verification_invariants:
            compliance_results['violations'].append({
                'type': 'MISSING_VERIFICATION',
                'description': 'Policy requires verification but no invariants defined',
                'severity': 'HIGH'
            })
            compliance_results['is_compliant'] = False
        
        # Check approval requirements
        if expected_policy.get('approval_required', True):
            compliance_results['recommendations'].append({
                'type': 'APPROVAL_REQUIRED',
                'description': 'This repair plan requires stakeholder approval before execution',
                'action': 'Obtain approval before proceeding to Phase 4B'
            })
        
        # Check risk assessment
        if repair_plan.risk_assessment['overall_risk'] in ['HIGH', 'CRITICAL']:
            compliance_results['recommendations'].append({
                'type': 'HIGH_RISK_MITIGATION',
                'description': 'High risk operation requires additional safeguards',
                'action': 'Implement additional testing and monitoring'
            })
        
        return compliance_results


@dataclass
class DetailedRepairPlan:
    """
    Comprehensive repair plan with all details for execution.
    Framework only - NO EXECUTION in Phase 4A.
    """
    corruption_type: str
    policy_type: RepairPolicyType
    confidence: ConfidenceLevel
    repair_actions: List[RepairAction]
    verification_invariants: List[VerificationInvariant]
    rollback_strategy: RollbackStrategy
    policy_config: Dict
    affected_objects_count: int
    estimated_duration: timedelta
    risk_assessment: Dict
    created_at: datetime = field(default_factory=timezone.now)
    status: RepairStatus = RepairStatus.PLANNED
    approval_required: bool = True
    
    def to_dict(self) -> Dict:
        """Convert repair plan to dictionary"""
        return {
            'corruption_type': self.corruption_type,
            'policy_type': self.policy_type.value,
            'confidence': self.confidence.value,
            'repair_actions': [action.to_dict() for action in self.repair_actions],
            'verification_invariants': [inv.to_dict() for inv in self.verification_invariants],
            'rollback_strategy': self.rollback_strategy.to_dict(),
            'policy_config': self.policy_config,
            'affected_objects_count': self.affected_objects_count,
            'estimated_duration': str(self.estimated_duration),
            'risk_assessment': self.risk_assessment,
            'created_at': self.created_at.isoformat(),
            'status': self.status.value,
            'approval_required': self.approval_required
        }
    
    def get_summary(self) -> Dict:
        """Get summary of repair plan"""
        return {
            'corruption_type': self.corruption_type,
            'policy': self.policy_type.value,
            'confidence': self.confidence.value,
            'affected_objects': self.affected_objects_count,
            'actions_count': len(self.repair_actions),
            'estimated_duration': str(self.estimated_duration),
            'risk_level': self.risk_assessment['overall_risk'],
            'approval_required': self.approval_required,
            'status': self.status.value
        }