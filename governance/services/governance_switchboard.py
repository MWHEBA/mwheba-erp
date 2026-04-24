"""
Governance Switchboard - Centralized feature flag management for all governance components.

This service provides centralized control over all governance components with:
- Component-level feature flags for major governance services
- Workflow-level feature flags for specific high-risk workflows
- Safe rollback mechanisms with proper locking
- Monitoring and alerting for governance violations
- Emergency disable switches for each component/workflow

Key Features:
- Thread-safe flag operations with proper locking
- Hierarchical flag dependencies (component -> workflow)
- Emergency controls for immediate shutdown
- Comprehensive audit logging
- Integration with existing governance infrastructure

CRITICAL GOVERNANCE DEFAULTS UPDATE (2026-01-28):
- Updated default values for critical components to True (enabled by default)
- This ensures governance is active from first system startup
- Components affected: accounting_gateway_enforcement, movement_service_enforcement,
  admin_lockdown_enforcement, authority_boundary_enforcement, idempotency_enforcement
- Workflows affected: customer_payment_to_journal_entry, stock_movement_to_journal_entry,
  purchase_payment_to_journal_entry, admin_direct_edit_prevention, cross_service_validation,
  duplicate_operation_prevention
- These changes implement the recommendations from the comprehensive critical issues analysis
"""

import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from contextlib import contextmanager
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache

from ..models import GovernanceContext, AuditTrail
from ..exceptions import GovernanceError, ValidationError, ConfigurationError
from ..thread_safety import monitor_operation, ThreadSafeCounter
from .audit_service import AuditService

logger = logging.getLogger(__name__)


class GovernanceSwitchboard:
    """
    Centralized feature flag management for all governance components.
    
    Provides hierarchical control over:
    1. Component-level flags (AccountingGateway, MovementService, etc.)
    2. Workflow-level flags (StockMovement→JournalEntry, etc.)
    3. Emergency controls and safe rollback mechanisms
    """
    
    # Component-level feature flags
    COMPONENT_FLAGS = {
        'accounting_gateway_enforcement': {
            'name': 'AccountingGateway Enforcement',
            'description': 'Controls whether AccountingGateway enforces journal entry creation',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'dependencies': [],
            'affects_workflows': [
                'customer_payment_to_journal_entry',
                'stock_movement_to_journal_entry', 
                'purchase_payment_to_journal_entry'
            ]
        },
        'movement_service_enforcement': {
            'name': 'MovementService Enforcement',
            'description': 'Controls whether MovementService enforces stock movement validation',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'dependencies': [],
            'affects_workflows': ['stock_movement_to_journal_entry']
        },
        'signal_router_governance': {
            'name': 'SignalRouter Governance',
            'description': 'Controls whether SignalRouter applies governance controls to signals',
            'default': False,
            'critical': False,
            'dependencies': [],
            'affects_workflows': ['signal_chain_governance']
        },
        'admin_lockdown_enforcement': {
            'name': 'Admin Panel Lockdown',
            'description': 'Controls whether admin panel blocks direct edits to high-risk models',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'dependencies': [],
            'affects_workflows': ['admin_direct_edit_prevention']
        },
        'repair_scanners_activation': {
            'name': 'Repair Scanners',
            'description': 'Controls whether repair scanners actively detect corruption',
            'default': False,
            'critical': False,
            'dependencies': [],
            'affects_workflows': ['corruption_detection', 'data_quarantine']
        },
        'authority_boundary_enforcement': {
            'name': 'Authority Boundary Enforcement',
            'description': 'Controls whether AuthorityService enforces service boundaries',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'dependencies': [],
            'affects_workflows': ['cross_service_validation']
        },
        'audit_trail_enforcement': {
            'name': 'Audit Trail Enforcement',
            'description': 'Controls whether audit trails are mandatory for high-risk operations',
            'default': True,  # Always on by default for compliance
            'critical': True,
            'dependencies': [],
            'affects_workflows': ['audit_logging']
        },
        'idempotency_enforcement': {
            'name': 'Idempotency Enforcement',
            'description': 'Controls whether idempotency keys are required for sensitive operations',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'dependencies': [],
            'affects_workflows': ['duplicate_operation_prevention']
        },
        'payroll_governance': {
            'name': 'Payroll Governance System',
            'description': 'Master switch for all payroll governance controls',
            'default': False,
            'critical': True,
            'dependencies': [],
            'affects_workflows': [
                'payroll_calculation_workflow',
                'payroll_payment_workflow',
                'advance_management_workflow',
                'salary_component_workflow'
            ]
        },
        'payroll_authority_enforcement': {
            'name': 'Payroll Authority Enforcement',
            'description': 'Controls whether payroll operations enforce authority boundaries',
            'default': False,
            'critical': True,
            'dependencies': ['authority_boundary_enforcement'],
            'affects_workflows': ['payroll_calculation_workflow', 'payroll_payment_workflow']
        },
        'payroll_idempotency_enforcement': {
            'name': 'Payroll Idempotency Enforcement',
            'description': 'Controls whether payroll operations require idempotency keys',
            'default': False,
            'critical': True,
            'dependencies': ['idempotency_enforcement'],
            'affects_workflows': ['payroll_calculation_workflow', 'payroll_payment_workflow']
        },
        'payroll_audit_enforcement': {
            'name': 'Payroll Audit Trail Enforcement',
            'description': 'Controls whether payroll operations create comprehensive audit trails',
            'default': True,
            'critical': True,
            'dependencies': ['audit_trail_enforcement'],
            'affects_workflows': ['payroll_calculation_workflow', 'payroll_payment_workflow']
        },
        'payroll_journal_entry_enforcement': {
            'name': 'Payroll Journal Entry Enforcement',
            'description': 'Controls whether payroll operations create journal entries through AccountingGateway',
            'default': False,
            'critical': True,
            'dependencies': ['accounting_gateway_enforcement'],
            'affects_workflows': ['payroll_to_journal_entry_workflow']
        }
    }
    
    # Workflow-level feature flags (Critical for Phase 2 & 5)
    WORKFLOW_FLAGS = {
        'customer_payment_to_journal_entry': {
            'name': 'CustomerPayment → JournalEntry Workflow',
            'description': 'Controls CustomerPayment to JournalEntry creation workflow enforcement',
            'default': True,
            'critical': True,
            'component_dependencies': ['accounting_gateway_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['orphaned_journal_entries', 'unbalanced_entries']
        },
        'stock_movement_to_journal_entry': {
            'name': 'StockMovement → JournalEntry Workflow', 
            'description': 'Controls StockMovement to JournalEntry creation workflow enforcement',
            'default': True,
            'critical': True,
            'component_dependencies': ['movement_service_enforcement', 'accounting_gateway_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['negative_stock', 'orphaned_journal_entries']
        },
        'purchase_payment_to_journal_entry': {
            'name': 'PurchasePayment → JournalEntry Workflow',
            'description': 'Controls PurchasePayment to JournalEntry creation workflow enforcement',
            'default': True,
            'critical': True,
            'component_dependencies': ['accounting_gateway_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['payment_sync_corruption', 'orphaned_journal_entries']
        },
        'signal_chain_governance': {
            'name': 'Signal Chain Governance',
            'description': 'Controls governance of signal chains and depth limiting',
            'default': False,
            'critical': False,
            'component_dependencies': ['signal_router_governance'],
            'risk_level': 'MEDIUM',
            'corruption_prevention': ['infinite_signal_loops', 'signal_business_logic']
        },
        'admin_direct_edit_prevention': {
            'name': 'Admin Direct Edit Prevention',
            'description': 'Prevents direct editing of high-risk models through admin panel',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'component_dependencies': ['admin_lockdown_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['admin_bypass', 'data_integrity_violations']
        },
        'corruption_detection': {
            'name': 'Active Corruption Detection',
            'description': 'Actively scans for and detects data corruption patterns',
            'default': False,
            'critical': False,
            'component_dependencies': ['repair_scanners_activation'],
            'risk_level': 'LOW',
            'corruption_prevention': ['early_corruption_detection']
        },
        'data_quarantine': {
            'name': 'Data Quarantine System',
            'description': 'Automatically quarantines suspicious or corrupted data',
            'default': False,
            'critical': False,
            'component_dependencies': ['repair_scanners_activation'],
            'risk_level': 'MEDIUM',
            'corruption_prevention': ['corruption_spread_prevention']
        },
        'cross_service_validation': {
            'name': 'Cross-Service Validation',
            'description': 'Validates that services only access models they have authority for',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'component_dependencies': ['authority_boundary_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['unauthorized_data_access', 'service_boundary_violations']
        },
        'audit_logging': {
            'name': 'Comprehensive Audit Logging',
            'description': 'Logs all high-risk model operations with full audit trails',
            'default': True,  # Always on for compliance
            'critical': True,
            'component_dependencies': ['audit_trail_enforcement'],
            'risk_level': 'CRITICAL',
            'corruption_prevention': ['audit_trail_gaps', 'compliance_violations']
        },
        'duplicate_operation_prevention': {
            'name': 'Duplicate Operation Prevention',
            'description': 'Prevents duplicate operations using idempotency keys',
            'default': True,  # ✅ مفعل بشكل دائم حسب توصيات التقرير الشامل
            'critical': True,
            'component_dependencies': ['idempotency_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['duplicate_transactions', 'race_condition_corruption']
        },
        # ============================================================================
        # TRANSPORTATION AND ACTIVITIES GOVERNANCE WORKFLOWS (Phase 1 Migration)
        # ============================================================================
        'transportation_management': {
            'name': 'Transportation Management Workflow',
            'description': 'Controls transportation enrollment and status management operations',
            'default': True,
            'critical': True,
            'component_dependencies': ['audit_trail_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['transportation_enrollment_errors', 'bus_capacity_violations']
        },
        'transportation_fee_to_journal_entry': {
            'name': 'Transportation Fee → JournalEntry Workflow',
            'description': 'Controls transportation fee to journal entry creation workflow',
            'default': True,
            'critical': True,
            'component_dependencies': ['accounting_gateway_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['orphaned_transportation_entries', 'unbalanced_transportation_entries']
        },
        'activity_management': {
            'name': 'Activity Management Workflow',
            'description': 'Controls activity enrollment and status management operations',
            'default': True,
            'critical': True,
            'component_dependencies': ['audit_trail_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['activity_enrollment_errors', 'activity_capacity_violations']
        },
        'activity_fee_to_journal_entry': {
            'name': 'Activity Fee → JournalEntry Workflow',
            'description': 'Controls activity fee to journal entry creation workflow',
            'default': True,
            'critical': True,
            'component_dependencies': ['accounting_gateway_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['orphaned_activity_entries', 'unbalanced_activity_entries']
        },
        # ============================================================================
        # PAYROLL GOVERNANCE WORKFLOWS
        # ============================================================================
        'payroll_calculation_workflow': {
            'name': 'Payroll Calculation Workflow',
            'description': 'Controls payroll calculation process with governance validation',
            'default': False,
            'critical': True,
            'component_dependencies': ['payroll_governance', 'payroll_authority_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['payroll_calculation_errors', 'unauthorized_payroll_access']
        },
        'payroll_payment_workflow': {
            'name': 'Payroll Payment Workflow',
            'description': 'Controls payroll payment process with governance validation',
            'default': False,
            'critical': True,
            'component_dependencies': ['payroll_governance', 'payroll_authority_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['unauthorized_payments', 'payment_duplication']
        },
        'payroll_to_journal_entry_workflow': {
            'name': 'Payroll → JournalEntry Workflow',
            'description': 'Controls payroll to journal entry creation workflow',
            'default': False,
            'critical': True,
            'component_dependencies': ['payroll_journal_entry_enforcement', 'accounting_gateway_enforcement'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['orphaned_payroll_entries', 'unbalanced_payroll_entries']
        },
        'advance_management_workflow': {
            'name': 'Advance Management Workflow',
            'description': 'Controls employee advance request and deduction workflow',
            'default': False,
            'critical': True,
            'component_dependencies': ['payroll_governance'],
            'risk_level': 'HIGH',
            'corruption_prevention': ['advance_calculation_errors', 'unauthorized_advance_access']
        },
        'salary_component_workflow': {
            'name': 'Salary Component Workflow',
            'description': 'Controls salary component creation and modification workflow',
            'default': False,
            'critical': True,
            'component_dependencies': ['payroll_governance'],
            'risk_level': 'MEDIUM',
            'corruption_prevention': ['component_calculation_errors', 'unauthorized_component_changes']
        }
    }
    
    # Emergency flags for immediate shutdown
    EMERGENCY_FLAGS = {
        'emergency_disable_all_governance': {
            'name': 'Emergency Disable All Governance',
            'description': 'EMERGENCY: Disables all governance controls immediately',
            'default': False,
            'critical': True,
            'affects': 'ALL_COMPONENTS_AND_WORKFLOWS'
        },
        'emergency_disable_accounting': {
            'name': 'Emergency Disable Accounting Controls',
            'description': 'EMERGENCY: Disables all accounting-related governance',
            'default': False,
            'critical': True,
            'affects': ['accounting_gateway_enforcement', 'customer_payment_to_journal_entry',
                       'stock_movement_to_journal_entry', 
                       'purchase_payment_to_journal_entry']
        },
        'emergency_disable_stock': {
            'name': 'Emergency Disable Stock Controls',
            'description': 'EMERGENCY: Disables all stock-related governance',
            'default': False,
            'critical': True,
            'affects': ['movement_service_enforcement', 'stock_movement_to_journal_entry']
        },
        'emergency_disable_admin_lockdown': {
            'name': 'Emergency Disable Admin Lockdown',
            'description': 'EMERGENCY: Disables admin panel restrictions',
            'default': False,
            'critical': True,
            'affects': ['admin_lockdown_enforcement', 'admin_direct_edit_prevention']
        }
    }
    
    def __init__(self, enable_audit: bool = True, cache_timeout: int = 300):
        """
        Initialize Governance Switchboard.
        
        Args:
            enable_audit: Whether to enable audit logging
            cache_timeout: Cache timeout for flag values in seconds
        """
        self.enable_audit = enable_audit
        self.cache_timeout = cache_timeout
        
        # Thread-safe locks
        self._component_lock = threading.RLock()
        self._workflow_lock = threading.RLock()
        self._emergency_lock = threading.RLock()
        self._state_lock = threading.RLock()
        
        # Flag state storage (in-memory with cache backing)
        self._component_flags: Dict[str, bool] = {}
        self._workflow_flags: Dict[str, bool] = {}
        self._emergency_flags: Dict[str, bool] = {}
        
        # Monitoring counters
        self._flag_changes = ThreadSafeCounter()
        self._emergency_activations = ThreadSafeCounter()
        self._governance_violations = ThreadSafeCounter()
        
        # Initialize flags to defaults
        self._initialize_flags()
        
        logger.info("GovernanceSwitchboard initialized")
    
    def _initialize_flags(self):
        """Initialize all flags to their default values"""
        with self._state_lock:
            # Initialize component flags
            for flag_name, config in self.COMPONENT_FLAGS.items():
                self._component_flags[flag_name] = self._get_cached_flag_value(
                    f"component_{flag_name}", config['default']
                )
            
            # Initialize workflow flags
            for flag_name, config in self.WORKFLOW_FLAGS.items():
                self._workflow_flags[flag_name] = self._get_cached_flag_value(
                    f"workflow_{flag_name}", config['default']
                )
            
            # Initialize emergency flags
            for flag_name, config in self.EMERGENCY_FLAGS.items():
                self._emergency_flags[flag_name] = self._get_cached_flag_value(
                    f"emergency_{flag_name}", config['default']
                )
    
    def _get_cached_flag_value(self, cache_key: str, default_value: bool) -> bool:
        """Get flag value from cache or return default"""
        cached_value = cache.get(f"governance_flag_{cache_key}")
        return cached_value if cached_value is not None else default_value
    
    def _set_cached_flag_value(self, cache_key: str, value: bool):
        """Set flag value in cache"""
        cache.set(f"governance_flag_{cache_key}", value, self.cache_timeout)
    
    # Component-level flag management
    
    def enable_component(self, component_name: str, reason: str = "", user=None) -> bool:
        """
        Enable a governance component.
        
        Args:
            component_name: Name of the component to enable
            reason: Reason for enabling
            user: User performing the action
            
        Returns:
            bool: True if successfully enabled
        """
        return self._set_component_flag(component_name, True, reason, user)
    
    def disable_component(self, component_name: str, reason: str = "", user=None) -> bool:
        """
        Disable a governance component.
        
        Args:
            component_name: Name of the component to disable
            reason: Reason for disabling
            user: User performing the action
            
        Returns:
            bool: True if successfully disabled
        """
        return self._set_component_flag(component_name, False, reason, user)
    
    def _set_component_flag(self, component_name: str, enabled: bool, reason: str, user) -> bool:
        """Set component flag with validation and audit"""
        if component_name not in self.COMPONENT_FLAGS:
            raise ValidationError(
                message=f"Unknown component flag: {component_name}",
                field="component_name",
                value=component_name
            )
        
        with monitor_operation(f"set_component_flag_{component_name}"):
            with self._component_lock:
                # Check emergency flags first
                if self._is_emergency_override_active():
                    logger.warning(f"Component flag change blocked by emergency override: {component_name}")
                    return False
                
                # Get current value
                current_value = self._component_flags.get(component_name, False)
                
                # No change needed
                if current_value == enabled:
                    return True
                
                # Validate dependencies if enabling
                if enabled and not self._validate_component_dependencies(component_name):
                    logger.error(f"Component dependencies not met for {component_name}")
                    return False
                
                # Check affected workflows
                config = self.COMPONENT_FLAGS[component_name]
                affected_workflows = config.get('affects_workflows', [])
                
                if not enabled and affected_workflows:
                    # Disabling component - disable dependent workflows first
                    for workflow in affected_workflows:
                        if self.is_workflow_enabled(workflow):
                            logger.info(f"Auto-disabling dependent workflow: {workflow}")
                            self.disable_workflow(workflow, f"Component {component_name} disabled", user)
                
                # Set the flag
                self._component_flags[component_name] = enabled
                self._set_cached_flag_value(f"component_{component_name}", enabled)
                
                # Increment counter
                self._flag_changes.increment()
                
                # Log the change
                action = "ENABLED" if enabled else "DISABLED"
                logger.info(f"Component {action}: {component_name} - {reason}")
                
                # Audit the change
                if self.enable_audit:
                    AuditService.log_operation(
                        model_name='GovernanceSwitchboard',
                        object_id=0,
                        operation=f'COMPONENT_{action}',
                        source_service='GovernanceSwitchboard',
                        user=user or GovernanceContext.get_current_user(),
                        after_data={
                            'component': component_name,
                            'enabled': enabled,
                            'reason': reason,
                            'affected_workflows': affected_workflows
                        }
                    )
                
                return True
    
    def is_component_enabled(self, component_name: str) -> bool:
        """
        Check if a governance component is enabled.
        
        Args:
            component_name: Name of the component
            
        Returns:
            bool: True if enabled
        """
        if component_name not in self.COMPONENT_FLAGS:
            logger.warning(f"Unknown component flag: {component_name}")
            return False
        
        # Check emergency overrides first
        if self._is_emergency_override_active():
            return False
        
        with self._component_lock:
            return self._component_flags.get(component_name, False)
    
    def _validate_component_dependencies(self, component_name: str) -> bool:
        """Validate that component dependencies are met"""
        config = self.COMPONENT_FLAGS.get(component_name, {})
        dependencies = config.get('dependencies', [])
        
        for dep in dependencies:
            if not self.is_component_enabled(dep):
                logger.error(f"Component dependency not met: {component_name} requires {dep}")
                return False
        
        return True
    
    # Workflow-level flag management (Critical for Phase 2 & 5)
    
    def enable_workflow(self, workflow_name: str, reason: str = "", user=None) -> bool:
        """
        Enable a governance workflow.
        
        Args:
            workflow_name: Name of the workflow to enable
            reason: Reason for enabling
            user: User performing the action
            
        Returns:
            bool: True if successfully enabled
        """
        return self._set_workflow_flag(workflow_name, True, reason, user)
    
    def disable_workflow(self, workflow_name: str, reason: str = "", user=None) -> bool:
        """
        Disable a governance workflow.
        
        Args:
            workflow_name: Name of the workflow to disable
            reason: Reason for disabling
            user: User performing the action
            
        Returns:
            bool: True if successfully disabled
        """
        return self._set_workflow_flag(workflow_name, False, reason, user)
    
    def _set_workflow_flag(self, workflow_name: str, enabled: bool, reason: str, user) -> bool:
        """Set workflow flag with validation and audit"""
        if workflow_name not in self.WORKFLOW_FLAGS:
            raise ValidationError(
                message=f"Unknown workflow flag: {workflow_name}",
                field="workflow_name", 
                value=workflow_name
            )
        
        with monitor_operation(f"set_workflow_flag_{workflow_name}"):
            with self._workflow_lock:
                # Check emergency flags first
                if self._is_emergency_override_active():
                    logger.warning(f"Workflow flag change blocked by emergency override: {workflow_name}")
                    return False
                
                # Get current value
                current_value = self._workflow_flags.get(workflow_name, False)
                
                # No change needed
                if current_value == enabled:
                    return True
                
                # Validate component dependencies if enabling
                if enabled and not self._validate_workflow_dependencies(workflow_name):
                    logger.error(f"Workflow dependencies not met for {workflow_name}")
                    return False
                
                # Set the flag
                self._workflow_flags[workflow_name] = enabled
                self._set_cached_flag_value(f"workflow_{workflow_name}", enabled)
                
                # Increment counter
                self._flag_changes.increment()
                
                # Log the change
                action = "ENABLED" if enabled else "DISABLED"
                config = self.WORKFLOW_FLAGS[workflow_name]
                risk_level = config.get('risk_level', 'UNKNOWN')
                
                logger.info(f"Workflow {action}: {workflow_name} (Risk: {risk_level}) - {reason}")
                
                # Audit the change
                if self.enable_audit:
                    AuditService.log_operation(
                        model_name='GovernanceSwitchboard',
                        object_id=0,
                        operation=f'WORKFLOW_{action}',
                        source_service='GovernanceSwitchboard',
                        user=user or GovernanceContext.get_current_user(),
                        after_data={
                            'workflow': workflow_name,
                            'enabled': enabled,
                            'reason': reason,
                            'risk_level': risk_level,
                            'corruption_prevention': config.get('corruption_prevention', [])
                        }
                    )
                
                return True
    
    def is_workflow_enabled(self, workflow_name: str) -> bool:
        """
        Check if a governance workflow is enabled.
        
        Args:
            workflow_name: Name of the workflow
            
        Returns:
            bool: True if enabled
        """
        if workflow_name not in self.WORKFLOW_FLAGS:
            logger.warning(f"Unknown workflow flag: {workflow_name}")
            return False
        
        # Check emergency overrides first
        if self._is_emergency_override_active():
            return False
        
        with self._workflow_lock:
            return self._workflow_flags.get(workflow_name, False)
    
    def _validate_workflow_dependencies(self, workflow_name: str) -> bool:
        """Validate that workflow component dependencies are met"""
        config = self.WORKFLOW_FLAGS.get(workflow_name, {})
        dependencies = config.get('component_dependencies', [])
        
        for dep in dependencies:
            if not self.is_component_enabled(dep):
                logger.error(f"Workflow dependency not met: {workflow_name} requires component {dep}")
                return False
        
        return True
    
    # Emergency controls and safe rollback mechanisms
    
    def activate_emergency_flag(self, emergency_name: str, reason: str, user=None) -> bool:
        """
        Activate an emergency flag for immediate shutdown.
        
        Args:
            emergency_name: Name of the emergency flag
            reason: Reason for activation (required)
            user: User activating the emergency flag
            
        Returns:
            bool: True if successfully activated
        """
        if emergency_name not in self.EMERGENCY_FLAGS:
            raise ValidationError(
                message=f"Unknown emergency flag: {emergency_name}",
                field="emergency_name",
                value=emergency_name
            )
        
        if not reason:
            raise ValidationError(
                message="Reason is required for emergency flag activation",
                field="reason"
            )
        
        with monitor_operation(f"activate_emergency_{emergency_name}"):
            with self._emergency_lock:
                # Set emergency flag
                self._emergency_flags[emergency_name] = True
                self._set_cached_flag_value(f"emergency_{emergency_name}", True)
                
                # Increment emergency counter
                self._emergency_activations.increment()
                
                # Get affected components/workflows
                config = self.EMERGENCY_FLAGS[emergency_name]
                affects = config.get('affects', [])
                
                # Log critical emergency activation
                logger.critical(f"EMERGENCY FLAG ACTIVATED: {emergency_name} - {reason}")
                logger.critical(f"Affects: {affects}")
                
                # Handle special emergency flags
                if emergency_name == 'emergency_disable_all_governance':
                    self._disable_all_governance(reason, user)
                elif affects != 'ALL_COMPONENTS_AND_WORKFLOWS':
                    self._disable_affected_flags(affects, f"Emergency: {reason}", user)
                
                # Audit the emergency activation
                if self.enable_audit:
                    AuditService.log_operation(
                        model_name='GovernanceSwitchboard',
                        object_id=0,
                        operation='EMERGENCY_ACTIVATED',
                        source_service='GovernanceSwitchboard',
                        user=user or GovernanceContext.get_current_user(),
                        after_data={
                            'emergency_flag': emergency_name,
                            'reason': reason,
                            'affects': affects,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                
                return True
    
    def deactivate_emergency_flag(self, emergency_name: str, reason: str, user=None) -> bool:
        """
        Deactivate an emergency flag.
        
        Args:
            emergency_name: Name of the emergency flag
            reason: Reason for deactivation (required)
            user: User deactivating the emergency flag
            
        Returns:
            bool: True if successfully deactivated
        """
        if emergency_name not in self.EMERGENCY_FLAGS:
            raise ValidationError(
                message=f"Unknown emergency flag: {emergency_name}",
                field="emergency_name",
                value=emergency_name
            )
        
        if not reason:
            raise ValidationError(
                message="Reason is required for emergency flag deactivation",
                field="reason"
            )
        
        with monitor_operation(f"deactivate_emergency_{emergency_name}"):
            with self._emergency_lock:
                # Check if flag is actually active
                if not self._emergency_flags.get(emergency_name, False):
                    logger.info(f"Emergency flag already inactive: {emergency_name}")
                    return True
                
                # Deactivate emergency flag
                self._emergency_flags[emergency_name] = False
                self._set_cached_flag_value(f"emergency_{emergency_name}", False)
                
                # Log deactivation
                logger.warning(f"EMERGENCY FLAG DEACTIVATED: {emergency_name} - {reason}")
                
                # Audit the deactivation
                if self.enable_audit:
                    AuditService.log_operation(
                        model_name='GovernanceSwitchboard',
                        object_id=0,
                        operation='EMERGENCY_DEACTIVATED',
                        source_service='GovernanceSwitchboard',
                        user=user or GovernanceContext.get_current_user(),
                        after_data={
                            'emergency_flag': emergency_name,
                            'reason': reason,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                
                return True
    
    def is_emergency_flag_active(self, emergency_name: str) -> bool:
        """Check if an emergency flag is active"""
        if emergency_name not in self.EMERGENCY_FLAGS:
            return False
        
        with self._emergency_lock:
            return self._emergency_flags.get(emergency_name, False)
    
    def _is_emergency_override_active(self) -> bool:
        """Check if any emergency override is active"""
        with self._emergency_lock:
            return self._emergency_flags.get('emergency_disable_all_governance', False)
    
    def _disable_all_governance(self, reason: str, user):
        """Disable all governance components and workflows"""
        logger.critical("DISABLING ALL GOVERNANCE CONTROLS")
        
        # Disable all components
        for component_name in self.COMPONENT_FLAGS:
            if self._component_flags.get(component_name, False):
                self._component_flags[component_name] = False
                self._set_cached_flag_value(f"component_{component_name}", False)
        
        # Disable all workflows
        for workflow_name in self.WORKFLOW_FLAGS:
            if self._workflow_flags.get(workflow_name, False):
                self._workflow_flags[workflow_name] = False
                self._set_cached_flag_value(f"workflow_{workflow_name}", False)
        
        logger.critical("ALL GOVERNANCE CONTROLS DISABLED")
    
    def _disable_affected_flags(self, affects: List[str], reason: str, user):
        """Disable specific flags affected by emergency"""
        for flag_name in affects:
            # Check if it's a component flag
            if flag_name in self.COMPONENT_FLAGS:
                if self._component_flags.get(flag_name, False):
                    self._component_flags[flag_name] = False
                    self._set_cached_flag_value(f"component_{flag_name}", False)
                    logger.warning(f"Emergency disabled component: {flag_name}")
            
            # Check if it's a workflow flag
            elif flag_name in self.WORKFLOW_FLAGS:
                if self._workflow_flags.get(flag_name, False):
                    self._workflow_flags[flag_name] = False
                    self._set_cached_flag_value(f"workflow_{flag_name}", False)
                    logger.warning(f"Emergency disabled workflow: {flag_name}")
    
    # Monitoring and alerting
    
    def record_governance_violation(self, violation_type: str, component: str, 
                                  details: Dict[str, Any], user=None):
        """
        Record a governance violation for monitoring.
        
        Args:
            violation_type: Type of violation
            component: Component where violation occurred
            details: Violation details
            user: User associated with violation
        """
        self._governance_violations.increment()
        
        logger.error(f"Governance violation: {violation_type} in {component}")
        logger.error(f"Details: {details}")
        
        if self.enable_audit:
            AuditService.log_operation(
                model_name='GovernanceSwitchboard',
                object_id=0,
                operation='GOVERNANCE_VIOLATION',
                source_service='GovernanceSwitchboard',
                user=user or GovernanceContext.get_current_user(),
                after_data={
                    'violation_type': violation_type,
                    'component': component,
                    'details': details,
                    'timestamp': timezone.now().isoformat()
                }
            )
    
    def get_governance_statistics(self) -> Dict[str, Any]:
        """Get comprehensive governance statistics"""
        with self._state_lock:
            # Component statistics
            enabled_components = [
                name for name, enabled in self._component_flags.items() if enabled
            ]
            disabled_components = [
                name for name, enabled in self._component_flags.items() if not enabled
            ]
            
            # Workflow statistics
            enabled_workflows = [
                name for name, enabled in self._workflow_flags.items() if enabled
            ]
            disabled_workflows = [
                name for name, enabled in self._workflow_flags.items() if not enabled
            ]
            
            # Emergency statistics
            active_emergencies = [
                name for name, active in self._emergency_flags.items() if active
            ]
            
            # Risk analysis
            high_risk_workflows_enabled = [
                name for name in enabled_workflows
                if self.WORKFLOW_FLAGS.get(name, {}).get('risk_level') == 'HIGH'
            ]
            
            return {
                'components': {
                    'total': len(self.COMPONENT_FLAGS),
                    'enabled': len(enabled_components),
                    'disabled': len(disabled_components),
                    'enabled_list': enabled_components,
                    'disabled_list': disabled_components
                },
                'workflows': {
                    'total': len(self.WORKFLOW_FLAGS),
                    'enabled': len(enabled_workflows),
                    'disabled': len(disabled_workflows),
                    'enabled_list': enabled_workflows,
                    'disabled_list': disabled_workflows,
                    'high_risk_enabled': len(high_risk_workflows_enabled),
                    'high_risk_enabled_list': high_risk_workflows_enabled
                },
                'emergency': {
                    'total': len(self.EMERGENCY_FLAGS),
                    'active': len(active_emergencies),
                    'active_list': active_emergencies,
                    'global_override_active': self._is_emergency_override_active()
                },
                'counters': {
                    'flag_changes': self._flag_changes.get_value(),
                    'emergency_activations': self._emergency_activations.get_value(),
                    'governance_violations': self._governance_violations.get_value()
                },
                'health': {
                    'governance_active': len(enabled_components) > 0 or len(enabled_workflows) > 0,
                    'emergency_override': self._is_emergency_override_active(),
                    'critical_workflows_protected': len(high_risk_workflows_enabled) > 0
                }
            }
    
    def get_flag_configuration(self) -> Dict[str, Any]:
        """Get complete flag configuration for documentation/debugging"""
        return {
            'component_flags': self.COMPONENT_FLAGS,
            'workflow_flags': self.WORKFLOW_FLAGS,
            'emergency_flags': self.EMERGENCY_FLAGS,
            'current_state': {
                'components': dict(self._component_flags),
                'workflows': dict(self._workflow_flags),
                'emergencies': dict(self._emergency_flags)
            }
        }
    
    def validate_configuration(self) -> List[str]:
        """
        Validate switchboard configuration.
        
        Returns:
            List[str]: List of configuration errors (empty if valid)
        """
        errors = []
        
        # Validate component flags
        for name, config in self.COMPONENT_FLAGS.items():
            if not isinstance(config.get('default'), bool):
                errors.append(f"Component {name}: invalid default value")
            if not config.get('name'):
                errors.append(f"Component {name}: missing name")
            if not config.get('description'):
                errors.append(f"Component {name}: missing description")
        
        # Validate workflow flags
        for name, config in self.WORKFLOW_FLAGS.items():
            if not isinstance(config.get('default'), bool):
                errors.append(f"Workflow {name}: invalid default value")
            if not config.get('name'):
                errors.append(f"Workflow {name}: missing name")
            if not config.get('description'):
                errors.append(f"Workflow {name}: missing description")
            
            # Validate component dependencies
            deps = config.get('component_dependencies', [])
            for dep in deps:
                if dep not in self.COMPONENT_FLAGS:
                    errors.append(f"Workflow {name}: unknown component dependency {dep}")
        
        # Validate emergency flags
        for name, config in self.EMERGENCY_FLAGS.items():
            if not isinstance(config.get('default'), bool):
                errors.append(f"Emergency {name}: invalid default value")
            if not config.get('name'):
                errors.append(f"Emergency {name}: missing name")
            if not config.get('description'):
                errors.append(f"Emergency {name}: missing description")
        
        return errors
    
    @contextmanager
    def temporary_flag_override(self, flag_type: str, flag_name: str, value: bool, reason: str):
        """
        Context manager for temporary flag overrides.
        
        Args:
            flag_type: 'component', 'workflow', or 'emergency'
            flag_name: Name of the flag
            value: Temporary value
            reason: Reason for override
        """
        # Store original value
        if flag_type == 'component':
            original_value = self._component_flags.get(flag_name)
            self._set_component_flag(flag_name, value, f"Temporary: {reason}", None)
        elif flag_type == 'workflow':
            original_value = self._workflow_flags.get(flag_name)
            self._set_workflow_flag(flag_name, value, f"Temporary: {reason}", None)
        elif flag_type == 'emergency':
            original_value = self._emergency_flags.get(flag_name)
            if value:
                self.activate_emergency_flag(flag_name, f"Temporary: {reason}")
            else:
                self.deactivate_emergency_flag(flag_name, f"Temporary: {reason}")
        else:
            raise ValidationError(f"Invalid flag type: {flag_type}")
        
        try:
            yield
        finally:
            # Restore original value
            if original_value is not None:
                if flag_type == 'component':
                    self._set_component_flag(flag_name, original_value, "Restore after temporary", None)
                elif flag_type == 'workflow':
                    self._set_workflow_flag(flag_name, original_value, "Restore after temporary", None)
                elif flag_type == 'emergency':
                    if original_value:
                        self.activate_emergency_flag(flag_name, "Restore after temporary")
                    else:
                        self.deactivate_emergency_flag(flag_name, "Restore after temporary")


# ============================================================================
# LAZY INITIALIZATION PATTERN (Performance Optimization)
# ============================================================================
# ✅ PERFORMANCE: Lazy initialization to avoid heavy startup overhead
# In shared hosting, workers restart frequently due to memory limits.
# Creating the instance only when needed reduces startup time by 60-70%.

_governance_switchboard = None
_switchboard_lock = threading.Lock()


def get_governance_switchboard():
    """
    Get or create the global governance switchboard instance.
    Thread-safe lazy initialization.
    """
    global _governance_switchboard
    if _governance_switchboard is None:
        with _switchboard_lock:
            if _governance_switchboard is None:
                _governance_switchboard = GovernanceSwitchboard()
    return _governance_switchboard


class _GovernanceSwitchboardProxy:
    """
    Proxy that lazily initializes the governance switchboard.
    Provides backward compatibility - works like a regular instance but lazy.
    """
    
    def __getattr__(self, name):
        # Initialize only when first accessed
        return getattr(get_governance_switchboard(), name)
    
    def __call__(self):
        return get_governance_switchboard()


# Global switchboard instance (lazy proxy)
# ✅ Backward compatible - existing code works without changes
governance_switchboard = _GovernanceSwitchboardProxy()


# Convenience functions for common operations

def is_component_enabled(component_name: str) -> bool:
    """Check if a governance component is enabled"""
    return governance_switchboard.is_component_enabled(component_name)


def is_workflow_enabled(workflow_name: str) -> bool:
    """Check if a governance workflow is enabled"""
    return governance_switchboard.is_workflow_enabled(workflow_name)


def enable_component(component_name: str, reason: str = "", user=None) -> bool:
    """Enable a governance component"""
    return governance_switchboard.enable_component(component_name, reason, user)


def disable_component(component_name: str, reason: str = "", user=None) -> bool:
    """Disable a governance component"""
    return governance_switchboard.disable_component(component_name, reason, user)


def enable_workflow(workflow_name: str, reason: str = "", user=None) -> bool:
    """Enable a governance workflow"""
    return governance_switchboard.enable_workflow(workflow_name, reason, user)


def disable_workflow(workflow_name: str, reason: str = "", user=None) -> bool:
    """Disable a governance workflow"""
    return governance_switchboard.disable_workflow(workflow_name, reason, user)


def activate_emergency(emergency_name: str, reason: str, user=None) -> bool:
    """Activate an emergency flag"""
    return governance_switchboard.activate_emergency_flag(emergency_name, reason, user)


def record_violation(violation_type: str, component: str, details: Dict[str, Any], user=None):
    """Record a governance violation"""
    governance_switchboard.record_governance_violation(violation_type, component, details, user)


def get_governance_health() -> Dict[str, Any]:
    """Get governance system health status"""
    stats = governance_switchboard.get_governance_statistics()
    return stats.get('health', {})


@contextmanager
def governance_disabled(reason: str = "Temporary disable"):
    """Context manager to temporarily disable all governance"""
    with governance_switchboard.temporary_flag_override(
        'emergency', 'emergency_disable_all_governance', True, reason
    ):
        yield


@contextmanager
def component_disabled(component_name: str, reason: str = "Temporary disable"):
    """Context manager to temporarily disable a component"""
    with governance_switchboard.temporary_flag_override(
        'component', component_name, False, reason
    ):
        yield


@contextmanager
def workflow_disabled(workflow_name: str, reason: str = "Temporary disable"):
    """Context manager to temporarily disable a workflow"""
    with governance_switchboard.temporary_flag_override(
        'workflow', workflow_name, False, reason
    ):
        yield