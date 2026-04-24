# -*- coding: utf-8 -*-
"""
Governance Services Module

This module contains all the core services for the Code Governance System,
including audit services, authority management, and security controls.
"""

from .audit_service import AuditService, audit_operation
from .repair_service import RepairService, CorruptionReport, RepairPolicy, RepairPlan
from .repair_policy_framework import (
    RepairPolicyFramework, RepairPolicyType, ConfidenceLevel, 
    DetailedRepairPlan, RepairStatus, RepairAction, VerificationInvariant, RollbackStrategy
)
from .quarantine_system import (
    QuarantineSystem, QuarantineStorage, QuarantineManager, QuarantineReporter,
    quarantine_system
)
from .governance_switchboard import (
    governance_switchboard, GovernanceSwitchboard,
    is_component_enabled, is_workflow_enabled,
    enable_component, disable_component,
    enable_workflow, disable_workflow,
    activate_emergency, record_violation, get_governance_health
)
from .accounting_gateway import AccountingGateway, JournalEntryLineData, SourceInfo
from .movement_service import MovementService, MovementType
from .authority_service import AuthorityService
from .idempotency_service import IdempotencyService
from .source_linkage_service import SourceLinkageService
from .signal_router import SignalRouter, signal_router
from .monitoring_service import (
    monitoring_service, MonitoringService,
    record_governance_metric, record_governance_violation,
    get_governance_health as get_monitoring_health,
    perform_component_health_check
)
from .governance_monitoring import (
    governance_monitoring, GovernanceMonitoringService,
    ViolationType, AlertLevel, start_monitoring, stop_monitoring,
    record_violation as record_monitoring_violation,
    record_metric, get_monitoring_status, get_violation_summary
)
from .payroll_governance_service import PayrollGovernanceService
from .payroll_gateway import PayrollGateway, PayrollData, SalaryComponentData
from .service_governance import governed_service
from .signal_governance import (
    governed_signal_handler, SignalErrorHandler, SignalPerformanceMonitor
)

__all__ = [
    'AuditService',
    'audit_operation',
    'RepairService',
    'CorruptionReport',
    'RepairPolicy',
    'RepairPlan',
    'RepairPolicyFramework',
    'RepairPolicyType',
    'ConfidenceLevel',
    'DetailedRepairPlan',
    'RepairStatus',
    'RepairAction',
    'VerificationInvariant',
    'RollbackStrategy',
    'QuarantineSystem',
    'QuarantineStorage',
    'QuarantineManager',
    'QuarantineReporter',
    'quarantine_system',
    'governance_switchboard',
    'GovernanceSwitchboard',
    'is_component_enabled',
    'is_workflow_enabled',
    'enable_component',
    'disable_component',
    'enable_workflow',
    'disable_workflow',
    'activate_emergency',
    'record_violation',
    'get_governance_health',
    'AccountingGateway',
    'JournalEntryLineData',
    'SourceInfo',
    'MovementService',
    'MovementType',
    'AuthorityService',
    'IdempotencyService',
    'SourceLinkageService',
    'SignalRouter',
    'signal_router',
    'monitoring_service',
    'MonitoringService',
    'record_governance_metric',
    'record_governance_violation',
    'get_monitoring_health',
    'perform_component_health_check',
    'governance_monitoring',
    'GovernanceMonitoringService',
    'ViolationType',
    'AlertLevel',
    'start_monitoring',
    'stop_monitoring',
    'record_monitoring_violation',
    'record_metric',
    'get_monitoring_status',
    'get_violation_summary',
    'PayrollGovernanceService',
    'PayrollGateway',
    'PayrollData',
    'SalaryComponentData',
    'governed_service',
    'governed_signal_handler',
    'SignalErrorHandler',
    'SignalPerformanceMonitor'
]