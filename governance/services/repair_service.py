"""
RepairService - Analysis-Only Data Corruption Detection and Repair Policy Framework

This service implements Phase 4A of the code governance system - the Repair Engine
for data analysis and corruption detection. This is REPORT-ONLY mode with NO 
AUTO-REPAIR capabilities.

Key Features:
- Thread-safe corruption detection scanners
- ORM-based detection with proper locking
- Focus on 23 identified orphaned journal entries
- Comprehensive reporting for stakeholder approval
- NO automatic repairs - analysis only
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from datetime import timedelta
from django.db import transaction, connection
from django.apps import apps
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from ..models import QuarantineRecord, AuditTrail, GovernanceContext
from ..thread_safety import monitor_operation
from ..exceptions import GovernanceError
from .quarantine_service import QuarantineService
from .source_linkage_service import SourceLinkageService
from .repair_policy_framework import (
    RepairPolicyFramework, RepairPolicyType, ConfidenceLevel, 
    DetailedRepairPlan, RepairStatus
)

User = get_user_model()
logger = logging.getLogger(__name__)


class CorruptionReport:
    """
    Comprehensive corruption detection report with evidence and recommendations.
    """
    
    def __init__(self):
        self.corruption_types = {}
        self.total_issues = 0
        self.scan_timestamp = timezone.now()
        self.recommendations = []
        self.evidence = {}
        self.confidence_levels = {}
    
    def add_corruption(self, corruption_type: str, issues: List[Dict], 
                      confidence: str = 'HIGH', evidence: Dict = None):
        """
        Add corruption findings to the report.
        
        Args:
            corruption_type: Type of corruption detected
            issues: List of corrupted records with details
            confidence: Confidence level (HIGH/MEDIUM/LOW)
            evidence: Supporting evidence for the corruption
        """
        self.corruption_types[corruption_type] = {
            'count': len(issues),
            'issues': issues,
            'confidence': confidence,
            'evidence': evidence or {}
        }
        self.total_issues += len(issues)
        self.confidence_levels[corruption_type] = confidence
        
        # Add policy recommendations based on corruption type
        if corruption_type == 'ORPHANED_JOURNAL_ENTRIES':
            if confidence == 'HIGH':
                self.recommendations.append({
                    'corruption_type': corruption_type,
                    'policy': 'RELINK',
                    'reason': 'High confidence orphaned entries can be relinked to sources'
                })
            else:
                self.recommendations.append({
                    'corruption_type': corruption_type,
                    'policy': 'QUARANTINE',
                    'reason': 'Low confidence entries should be quarantined for manual review'
                })
        elif corruption_type == 'NEGATIVE_STOCK':
            self.recommendations.append({
                'corruption_type': corruption_type,
                'policy': 'ADJUSTMENT',
                'reason': 'Negative stock requires quantity adjustments'
            })
        elif corruption_type == 'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS':
            self.recommendations.append({
                'corruption_type': corruption_type,
                'policy': 'REBUILD',
                'reason': 'Multiple active accounting periods require rebuilding period status'
            })
    
    def get_summary(self) -> Dict:
        """Get summary of corruption findings"""
        return {
            'total_issues': self.total_issues,
            'corruption_types': list(self.corruption_types.keys()),
            'scan_timestamp': self.scan_timestamp.isoformat(),
            'high_confidence_issues': sum(
                1 for ct, data in self.corruption_types.items() 
                if data['confidence'] == 'HIGH'
            ),
            'recommendations_count': len(self.recommendations)
        }
    
    def to_dict(self) -> Dict:
        """Convert report to dictionary for serialization"""
        return {
            'summary': self.get_summary(),
            'corruption_types': self.corruption_types,
            'recommendations': self.recommendations,
            'evidence': self.evidence,
            'confidence_levels': self.confidence_levels
        }


class RepairPolicy:
    """
    Defines repair policies for different corruption types.
    Framework only - NO EXECUTION in Phase 4A.
    """
    
    # Repair Policy Matrix
    RELINK = 'RELINK'      # Attempt to relink orphaned records to sources
    QUARANTINE = 'QUARANTINE'  # Isolate suspicious data for manual review
    REBUILD = 'REBUILD'    # Rebuild data from authoritative sources
    ADJUSTMENT = 'ADJUSTMENT'  # Adjust data to correct inconsistencies
    
    POLICIES = {
        'ORPHANED_JOURNAL_ENTRIES': {
            'HIGH_CONFIDENCE': RELINK,
            'MEDIUM_CONFIDENCE': QUARANTINE,
            'LOW_CONFIDENCE': QUARANTINE
        },
        'NEGATIVE_STOCK': {
            'HIGH_CONFIDENCE': ADJUSTMENT,
            'MEDIUM_CONFIDENCE': ADJUSTMENT,
            'LOW_CONFIDENCE': QUARANTINE
        },
        'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS': {
            'HIGH_CONFIDENCE': REBUILD,
            'MEDIUM_CONFIDENCE': REBUILD,
            'LOW_CONFIDENCE': QUARANTINE
        },
        'UNBALANCED_JOURNAL_ENTRIES': {
            'HIGH_CONFIDENCE': ADJUSTMENT,
            'MEDIUM_CONFIDENCE': QUARANTINE,
            'LOW_CONFIDENCE': QUARANTINE
        }
    }
    
    @classmethod
    def get_policy(cls, corruption_type: str, confidence: str) -> str:
        """
        Get recommended repair policy for corruption type and confidence level.
        
        Args:
            corruption_type: Type of corruption
            confidence: Confidence level (HIGH/MEDIUM/LOW)
            
        Returns:
            str: Recommended repair policy
        """
        policies = cls.POLICIES.get(corruption_type, {})
        return policies.get(f"{confidence}_CONFIDENCE", cls.QUARANTINE)
    
    @classmethod
    def get_all_policies(cls) -> Dict:
        """Get all defined repair policies"""
        return cls.POLICIES.copy()


class RepairPlan:
    """
    Template for repairing specific corruption types.
    Framework only - NO EXECUTION in Phase 4A.
    """
    
    def __init__(self, corruption_type: str, policy: str):
        self.corruption_type = corruption_type
        self.policy = policy
        self.detection_query = None
        self.classification_rules = []
        self.repair_actions = []
        self.verification_invariants = []
        self.rollback_strategy = None
        self.created_at = timezone.now()
    
    def add_verification_invariant(self, invariant: str):
        """Add verification invariant for this repair plan"""
        self.verification_invariants.append(invariant)
    
    def add_repair_action(self, action: Dict):
        """Add repair action to the plan"""
        self.repair_actions.append(action)
    
    def to_dict(self) -> Dict:
        """Convert repair plan to dictionary"""
        return {
            'corruption_type': self.corruption_type,
            'policy': self.policy,
            'verification_invariants': self.verification_invariants,
            'repair_actions': self.repair_actions,
            'created_at': self.created_at.isoformat()
        }


class RepairService:
    """
    Analysis-only repair service for corruption detection and policy framework.
    
    Phase 4A Implementation:
    - Corruption detection scanners (thread-safe)
    - Repair policy framework (no execution)
    - Comprehensive reporting
    - NO automatic repairs
    """
    
    def __init__(self):
        self.user = None
        self.policy_framework = RepairPolicyFramework()
        self._initialize_scanners()
    
    def _initialize_scanners(self):
        """Initialize corruption detection scanners"""
        self.scanners = {
            'ORPHANED_JOURNAL_ENTRIES': self._scan_orphaned_journal_entries,
            'NEGATIVE_STOCK': self._scan_negative_stock,
            'MULTIPLE_ACTIVE_ACCOUNTING_PERIODS': self._scan_multiple_active_accounting_periods,
            'UNBALANCED_JOURNAL_ENTRIES': self._scan_unbalanced_journal_entries
        }
    
    def set_user(self, user):
        """Set user context for repair operations"""
        self.user = user
        GovernanceContext.set_context(user=user, service='RepairService')
    
    @monitor_operation("scan_for_corruption")
    def scan_for_corruption(self, corruption_types: Optional[List[str]] = None) -> CorruptionReport:
        """
        Scan database for all types of corruption.
        Thread-safe implementation with proper locking.
        
        Args:
            corruption_types: Optional list of specific corruption types to scan
            
        Returns:
            CorruptionReport: Comprehensive corruption report
        """
        logger.info("Starting corruption detection scan")
        
        report = CorruptionReport()
        
        # Determine which scanners to run
        scanners_to_run = corruption_types or list(self.scanners.keys())
        
        for corruption_type in scanners_to_run:
            if corruption_type not in self.scanners:
                logger.warning(f"Unknown corruption type: {corruption_type}")
                continue
            
            try:
                logger.info(f"Scanning for {corruption_type}")
                scanner = self.scanners[corruption_type]
                issues, confidence, evidence = scanner()
                
                if issues:
                    report.add_corruption(
                        corruption_type=corruption_type,
                        issues=issues,
                        confidence=confidence,
                        evidence=evidence
                    )
                    logger.warning(f"Found {len(issues)} issues of type {corruption_type}")
                else:
                    logger.info(f"No issues found for {corruption_type}")
                    
            except Exception as e:
                logger.error(f"Error scanning for {corruption_type}: {e}", exc_info=True)
                # Add error to report
                report.add_corruption(
                    corruption_type=f"{corruption_type}_SCAN_ERROR",
                    issues=[{'error': str(e), 'scanner': corruption_type}],
                    confidence='LOW',
                    evidence={'error_details': str(e)}
                )
        
        logger.info(f"Corruption scan completed. Found {report.total_issues} total issues")
        
        # Create audit trail for scan
        if self.user:
            AuditTrail.log_operation(
                model_name='RepairService',
                object_id=0,
                operation='CORRUPTION_SCAN',
                user=self.user,
                source_service='RepairService',
                after_data=report.get_summary()
            )
        
        return report
    
    def _scan_orphaned_journal_entries(self) -> Tuple[List[Dict], str, Dict]:
        """
        Scan for orphaned journal entries using ORM-based detection.
        Focus on the 23 identified orphaned entries.
        
        Returns:
            Tuple of (issues, confidence_level, evidence)
        """
        issues = []
        evidence = {}
        
        try:
            # Get JournalEntry model
            JournalEntry = apps.get_model('financial', 'JournalEntry')
            
            with transaction.atomic():
                # Use select_for_update for thread safety where supported
                if connection.vendor == 'postgresql':
                    entries = JournalEntry.objects.select_for_update().all()
                else:
                    # SQLite: Use atomic block for best-effort consistency
                    entries = JournalEntry.objects.all()
                
                total_entries = entries.count()
                orphaned_count = 0
                
                for entry in entries:
                    # Check source linkage using SourceLinkage service
                    if not self._validate_journal_entry_linkage(entry):
                        issues.append({
                            'entry_id': entry.id,
                            'source_module': getattr(entry, 'source_module', None),
                            'source_model': getattr(entry, 'source_model', None),
                            'source_id': getattr(entry, 'source_id', None),
                            'created_at': entry.date.isoformat() if hasattr(entry, 'date') else None,
                            'amount': 'N/A',  # JournalEntry doesn't have amount field directly
                            'description': getattr(entry, 'description', 'N/A'),
                            'number': getattr(entry, 'number', 'N/A'),
                            'entry_type': getattr(entry, 'entry_type', 'N/A')
                        })
                        orphaned_count += 1
                
                evidence = {
                    'total_journal_entries': total_entries,
                    'orphaned_entries': orphaned_count,
                    'orphaned_percentage': (orphaned_count / total_entries * 100) if total_entries > 0 else 0,
                    'scan_method': 'ORM_based_with_SourceLinkage_validation'
                }
                
                # Determine confidence based on validation method
                confidence = 'HIGH' if orphaned_count <= 25 else 'MEDIUM'
                
                logger.info(f"Orphaned journal entries scan: {orphaned_count}/{total_entries} orphaned")
                
        except Exception as e:
            logger.error(f"Error scanning orphaned journal entries: {e}", exc_info=True)
            issues = [{'error': f"Scan failed: {str(e)}"}]
            confidence = 'LOW'
            evidence = {'error': str(e)}
        
        return issues, confidence, evidence
    
    def _validate_journal_entry_linkage(self, entry) -> bool:
        """
        Validate journal entry source linkage using SourceLinkage service.
        
        Args:
            entry: JournalEntry instance
            
        Returns:
            bool: True if linkage is valid, False otherwise
        """
        try:
            # Check if entry has source linkage fields
            source_module = getattr(entry, 'source_module', None)
            source_model = getattr(entry, 'source_model', None)
            source_id = getattr(entry, 'source_id', None)
            
            if not all([source_module, source_model, source_id]):
                return False
            
            # Use SourceLinkageService for validation
            return SourceLinkageService.validate_linkage(source_module, source_model, source_id)
            
        except Exception as e:
            logger.error(f"Error validating linkage for entry {entry.id}: {e}")
            return False
    
    def _scan_negative_stock(self) -> Tuple[List[Dict], str, Dict]:
        """
        Scan for negative stock quantities using ORM-based detection.
        
        Returns:
            Tuple of (issues, confidence_level, evidence)
        """
        issues = []
        evidence = {}
        
        try:
            # Get Stock model
            Stock = apps.get_model('product', 'Stock')
            
            with transaction.atomic():
                # Use select_for_update for thread safety where supported
                if connection.vendor == 'postgresql':
                    negative_stocks = Stock.objects.select_for_update().filter(quantity__lt=0)
                else:
                    # SQLite: Use atomic block
                    negative_stocks = Stock.objects.filter(quantity__lt=0)
                
                total_stocks = Stock.objects.count()
                negative_count = negative_stocks.count()
                
                for stock in negative_stocks:
                    product_name = 'N/A'
                    try:
                        if hasattr(stock, 'product') and stock.product:
                            product_name = str(stock.product)
                        elif hasattr(stock, 'product_id'):
                            # Try to get product name from product_id
                            Product = apps.get_model('product', 'Product')
                            try:
                                product = Product.objects.get(id=stock.product_id)
                                product_name = str(product)
                            except Product.DoesNotExist:
                                product_name = f'Product ID {stock.product_id} (Not Found)'
                    except Exception:
                        product_name = 'Error getting product name'
                    
                    issues.append({
                        'stock_id': stock.id,
                        'product_id': getattr(stock, 'product_id', None),
                        'product_name': product_name,
                        'current_quantity': str(stock.quantity),
                        'last_updated': getattr(stock, 'updated_at', None)
                    })
                
                evidence = {
                    'total_stock_records': total_stocks,
                    'negative_stock_count': negative_count,
                    'negative_percentage': (negative_count / total_stocks * 100) if total_stocks > 0 else 0,
                    'scan_method': 'ORM_based_quantity_filter'
                }
                
                # High confidence for negative stock detection
                confidence = 'HIGH'
                
                logger.info(f"Negative stock scan: {negative_count}/{total_stocks} negative")
                
        except Exception as e:
            logger.error(f"Error scanning negative stock: {e}", exc_info=True)
            issues = [{'error': f"Scan failed: {str(e)}"}]
            confidence = 'LOW'
            evidence = {'error': str(e)}
        
        return issues, confidence, evidence
    
    def _scan_multiple_active_accounting_periods(self) -> Tuple[List[Dict], str, Dict]:
        """
        Scan for multiple active accounting periods using ORM-based detection.
        
        Returns:
            Tuple of (issues, confidence_level, evidence)
        """
        issues = []
        evidence = {}
        
        try:
            AccountingPeriod = apps.get_model('financial', 'AccountingPeriod')
            
            with transaction.atomic():
                if connection.vendor == 'postgresql':
                    active_periods = AccountingPeriod.objects.select_for_update().filter(status='open')
                else:
                    active_periods = AccountingPeriod.objects.filter(status='open')
                
                total_periods = AccountingPeriod.objects.count()
                active_count = active_periods.count()
                
                if active_count > 1:
                    for period in active_periods:
                        issues.append({
                            'period_id': period.id,
                            'period_name': str(period),
                            'start_date': getattr(period, 'start_date', None),
                            'end_date': getattr(period, 'end_date', None),
                            'status': getattr(period, 'status', None),
                            'name': getattr(period, 'name', 'N/A')
                        })
                
                evidence = {
                    'total_accounting_periods': total_periods,
                    'active_periods_count': active_count,
                    'expected_active_count': 1,
                    'scan_method': 'ORM_based_status_filter'
                }
                
                confidence = 'HIGH'
                logger.info(f"Accounting period scan: {active_count} open periods (expected: 1)")
                
        except Exception as e:
            logger.error(f"Error scanning accounting periods: {e}", exc_info=True)
            issues = [{'error': f"Scan failed: {str(e)}", 'period_id': 0, 'period_name': 'Error'}]
            confidence = 'LOW'
            evidence = {'error': str(e)}
        
        return issues, confidence, evidence
    
    def _scan_unbalanced_journal_entries(self) -> Tuple[List[Dict], str, Dict]:
        """
        Scan for unbalanced journal entries (debits != credits).
        
        Returns:
            Tuple of (issues, confidence_level, evidence)
        """
        issues = []
        evidence = {}
        
        try:
            # Get models
            JournalEntry = apps.get_model('financial', 'JournalEntry')
            JournalEntryLine = apps.get_model('financial', 'JournalEntryLine')
            
            with transaction.atomic():
                # Use select_for_update for thread safety where supported
                if connection.vendor == 'postgresql':
                    entries = JournalEntry.objects.select_for_update().all()
                else:
                    # SQLite: Use atomic block
                    entries = JournalEntry.objects.all()
                
                total_entries = entries.count()
                unbalanced_count = 0
                
                for entry in entries:
                    # Calculate debit and credit totals
                    lines = JournalEntryLine.objects.filter(journal_entry=entry)
                    debit_total = sum(line.debit_amount for line in lines if line.debit_amount)
                    credit_total = sum(line.credit_amount for line in lines if line.credit_amount)
                    
                    if abs(debit_total - credit_total) > Decimal('0.01'):  # Allow for rounding
                        issues.append({
                            'entry_id': entry.id,
                            'entry_number': getattr(entry, 'number', 'N/A'),
                            'debit_total': str(debit_total),
                            'credit_total': str(credit_total),
                            'difference': str(debit_total - credit_total),
                            'line_count': lines.count(),
                            'created_at': entry.date.isoformat() if hasattr(entry, 'date') else None
                        })
                        unbalanced_count += 1
                
                evidence = {
                    'total_journal_entries': total_entries,
                    'unbalanced_entries': unbalanced_count,
                    'unbalanced_percentage': (unbalanced_count / total_entries * 100) if total_entries > 0 else 0,
                    'tolerance': '0.01',
                    'scan_method': 'ORM_based_debit_credit_calculation'
                }
                
                # High confidence for balance calculation
                confidence = 'HIGH'
                
                logger.info(f"Unbalanced entries scan: {unbalanced_count}/{total_entries} unbalanced")
                
        except Exception as e:
            logger.error(f"Error scanning unbalanced entries: {e}", exc_info=True)
            issues = [{'error': f"Scan failed: {str(e)}"}]
            confidence = 'LOW'
            evidence = {'error': str(e)}
        
        return issues, confidence, evidence
    
    def generate_comprehensive_repair_plan(self, corruption_report: CorruptionReport) -> Dict:
        """
        Generate comprehensive repair plan using policy framework.
        Framework only - NO EXECUTION in Phase 4A.
        
        Args:
            corruption_report: Corruption detection report
            
        Returns:
            Dict: Comprehensive repair plan with all details
        """
        comprehensive_plan = {
            'scan_summary': corruption_report.get_summary(),
            'detailed_plans': {},
            'overall_risk_assessment': {},
            'execution_timeline': {},
            'approval_requirements': {},
            'compliance_validation': {},
            'phase': '4A_ANALYSIS_ONLY',
            'execution_blocked': True
        }
        
        total_duration = timedelta()
        overall_risk = 'LOW'
        
        # Generate detailed repair plan for each corruption type
        for corruption_type, data in corruption_report.corruption_types.items():
            confidence_str = data['confidence']
            confidence = ConfidenceLevel(confidence_str)
            corrupted_objects = data['issues']
            
            # Create detailed repair plan using policy framework
            detailed_plan = self.policy_framework.create_repair_plan(
                corruption_type=corruption_type,
                confidence=confidence,
                corrupted_objects=corrupted_objects
            )
            
            # Validate policy compliance
            compliance = self.policy_framework.validate_policy_compliance(detailed_plan)
            
            comprehensive_plan['detailed_plans'][corruption_type] = detailed_plan.to_dict()
            comprehensive_plan['compliance_validation'][corruption_type] = compliance
            
            # Update overall metrics
            total_duration += detailed_plan.estimated_duration
            if detailed_plan.risk_assessment['overall_risk'] == 'CRITICAL':
                overall_risk = 'CRITICAL'
            elif detailed_plan.risk_assessment['overall_risk'] == 'HIGH' and overall_risk != 'CRITICAL':
                overall_risk = 'HIGH'
            elif detailed_plan.risk_assessment['overall_risk'] == 'MEDIUM' and overall_risk == 'LOW':
                overall_risk = 'MEDIUM'
        
        # Overall risk assessment
        comprehensive_plan['overall_risk_assessment'] = {
            'risk_level': overall_risk,
            'total_estimated_duration': str(total_duration),
            'requires_stakeholder_approval': True,
            'requires_testing': overall_risk != 'LOW',
            'requires_backup': True,
            'rollback_capability': 'FULL'
        }
        
        # Execution timeline
        comprehensive_plan['execution_timeline'] = {
            'phase_4a_complete': True,
            'phase_4b_approval_required': True,
            'estimated_execution_time': str(total_duration),
            'recommended_execution_window': 'MAINTENANCE_WINDOW',
            'parallel_execution_possible': False  # Sequential execution for safety
        }
        
        # Approval requirements
        comprehensive_plan['approval_requirements'] = {
            'stakeholder_approval_required': True,
            'technical_review_required': True,
            'backup_verification_required': True,
            'rollback_testing_required': overall_risk in ['HIGH', 'CRITICAL'],
            'approval_documentation': [
                'Detailed repair plan review',
                'Risk assessment approval',
                'Backup and rollback procedures',
                'Execution timeline approval'
            ]
        }
        
        return comprehensive_plan
    
    def create_repair_report(self, corruption_report: CorruptionReport) -> Dict:
        """
        Create comprehensive repair report with recommendations.
        Analysis only - NO EXECUTION.
        
        Args:
            corruption_report: Corruption detection report
            
        Returns:
            Dict: Comprehensive repair report
        """
        # Generate comprehensive repair plan using policy framework
        comprehensive_plan = self.generate_comprehensive_repair_plan(corruption_report)
        
        repair_report = {
            'scan_summary': corruption_report.get_summary(),
            'corruption_details': corruption_report.corruption_types,
            'comprehensive_repair_plan': comprehensive_plan,
            'policy_recommendations': corruption_report.recommendations,
            'approval_required': True,
            'execution_blocked': True,
            'phase': '4A_ANALYSIS_ONLY',
            'next_steps': [
                'Review corruption findings with stakeholders',
                'Approve specific repair policies for each corruption type',
                'Validate repair plan compliance and risk assessment',
                'Schedule Phase 4B execution after approval',
                'Ensure backup and rollback procedures are in place',
                'Conduct rollback testing for high-risk operations'
            ]
        }
        
        # Add risk assessment from comprehensive plan
        repair_report['risk_assessment'] = comprehensive_plan['overall_risk_assessment']
        
        # Add compliance summary
        compliance_summary = {
            'all_plans_compliant': True,
            'total_violations': 0,
            'total_warnings': 0,
            'high_risk_operations': 0
        }
        
        for corruption_type, compliance in comprehensive_plan['compliance_validation'].items():
            if not compliance['is_compliant']:
                compliance_summary['all_plans_compliant'] = False
            compliance_summary['total_violations'] += len(compliance['violations'])
            compliance_summary['total_warnings'] += len(compliance['warnings'])
            
            # Count high-risk operations
            plan = comprehensive_plan['detailed_plans'][corruption_type]
            if plan['risk_assessment']['overall_risk'] in ['HIGH', 'CRITICAL']:
                compliance_summary['high_risk_operations'] += 1
        
        repair_report['compliance_summary'] = compliance_summary
        
        return repair_report
    
    def _assess_repair_risks(self, corruption_report: CorruptionReport) -> Dict:
        """
        Assess risks associated with repair operations.
        
        Args:
            corruption_report: Corruption detection report
            
        Returns:
            Dict: Risk assessment
        """
        risks = {
            'high_risk_operations': [],
            'medium_risk_operations': [],
            'low_risk_operations': [],
            'overall_risk_level': 'LOW'
        }
        
        for corruption_type, data in corruption_report.corruption_types.items():
            count = data['count']
            confidence = data['confidence']
            
            risk_level = 'LOW'
            if count > 50 or confidence == 'LOW':
                risk_level = 'HIGH'
            elif count > 10 or confidence == 'MEDIUM':
                risk_level = 'MEDIUM'
            
            risk_entry = {
                'corruption_type': corruption_type,
                'count': count,
                'confidence': confidence,
                'recommended_policy': RepairPolicy.get_policy(corruption_type, confidence)
            }
            
            risks[f'{risk_level.lower()}_risk_operations'].append(risk_entry)
        
        # Determine overall risk level
        if risks['high_risk_operations']:
            risks['overall_risk_level'] = 'HIGH'
        elif risks['medium_risk_operations']:
            risks['overall_risk_level'] = 'MEDIUM'
        
        return risks
    
    def quarantine_suspicious_data(self, corruption_report: CorruptionReport, 
                                 auto_quarantine: bool = False) -> Dict:
        """
        Quarantine suspicious data based on corruption report.
        Only quarantines if auto_quarantine is True or confidence is LOW.
        
        Args:
            corruption_report: Corruption detection report
            auto_quarantine: Whether to automatically quarantine low-confidence issues
            
        Returns:
            Dict: Quarantine operation results
        """
        quarantine_results = {
            'quarantined_items': [],
            'skipped_items': [],
            'errors': []
        }
        
        for corruption_type, data in corruption_report.corruption_types.items():
            confidence = data['confidence']
            issues = data['issues']
            
            # Only auto-quarantine low confidence issues or if explicitly requested
            if not auto_quarantine and confidence != 'LOW':
                quarantine_results['skipped_items'].extend([
                    {
                        'corruption_type': corruption_type,
                        'reason': f'Confidence {confidence} - manual approval required',
                        'count': len(issues)
                    }
                ])
                continue
            
            # Quarantine issues
            for issue in issues:
                try:
                    if corruption_type == 'ORPHANED_JOURNAL_ENTRIES':
                        quarantine_record = QuarantineService.quarantine_orphaned_journal_entry(
                            entry_id=issue['entry_id'],
                            user=self.user
                        )
                    elif corruption_type == 'NEGATIVE_STOCK':
                        quarantine_record = QuarantineService.quarantine_negative_stock(
                            stock_id=issue['stock_id'],
                            current_quantity=float(issue['current_quantity']),
                            user=self.user
                        )
                    else:
                        # Generic quarantine
                        model_name = self._get_model_name_for_corruption(corruption_type)
                        object_id = self._get_object_id_from_issue(issue)
                        quarantine_record = QuarantineService.quarantine_data(
                            model_name=model_name,
                            object_id=object_id,
                            corruption_type=corruption_type,
                            reason=f"Detected during corruption scan with {confidence} confidence",
                            original_data=issue,
                            user=self.user
                        )
                    
                    quarantine_results['quarantined_items'].append({
                        'quarantine_id': quarantine_record.id,
                        'corruption_type': corruption_type,
                        'object_details': issue
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to quarantine {corruption_type} issue: {e}")
                    quarantine_results['errors'].append({
                        'corruption_type': corruption_type,
                        'issue': issue,
                        'error': str(e)
                    })
        
        return quarantine_results
    
    def _get_model_name_for_corruption(self, corruption_type: str) -> str:
        """Get model name for corruption type"""
        mapping = {
            'ORPHANED_JOURNAL_ENTRIES': 'JournalEntry',
            'NEGATIVE_STOCK': 'Stock',
            'MULTIPLE_ACTIVE_ACADEMIC_YEARS': 'AcademicYear',
            'UNBALANCED_JOURNAL_ENTRIES': 'JournalEntry'
        }
        return mapping.get(corruption_type, 'Unknown')
    
    def _get_object_id_from_issue(self, issue: Dict) -> int:
        """Extract object ID from issue data"""
        # Try common ID field names
        for field in ['entry_id', 'stock_id', 'year_id', 'id']:
            if field in issue:
                return issue[field]
        return 0  # Fallback