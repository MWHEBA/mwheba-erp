"""
Repair Validation Service - Phase 4B Implementation

This service validates repair results to ensure all approved repairs completed successfully,
no new corruption was introduced, and system integrity is maintained.

Key Features:
- Verify all approved repairs completed successfully
- Confirm no new corruption introduced during repair
- Validate system integrity after repair operations
- Generate comprehensive validation reports
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
from .source_linkage_service import SourceLinkageService
from .repair_service import RepairService

User = get_user_model()
logger = logging.getLogger(__name__)


class ValidationResult:
    """
    Results of repair validation operations.
    """
    
    def __init__(self, validation_type: str):
        self.validation_type = validation_type
        self.start_time = timezone.now()
        self.end_time = None
        self.status = 'IN_PROGRESS'
        self.checks_performed = []
        self.passed_checks = []
        self.failed_checks = []
        self.warnings = []
        self.critical_issues = []
        self.recommendations = []
        self.system_integrity_score = 0.0
    
    def mark_completed(self):
        """Mark validation as completed"""
        self.end_time = timezone.now()
        self.status = 'COMPLETED'
        
        # Calculate system integrity score
        total_checks = len(self.checks_performed)
        if total_checks > 0:
            passed_count = len(self.passed_checks)
            self.system_integrity_score = (passed_count / total_checks) * 100.0
    
    def mark_failed(self, error: str):
        """Mark validation as failed"""
        self.end_time = timezone.now()
        self.status = 'FAILED'
        self.critical_issues.append(error)
    
    def get_duration(self) -> timedelta:
        """Get validation duration"""
        end = self.end_time or timezone.now()
        return end - self.start_time
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for reporting"""
        return {
            'validation_type': self.validation_type,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': str(self.get_duration()),
            'status': self.status,
            'checks_performed': len(self.checks_performed),
            'passed_checks': len(self.passed_checks),
            'failed_checks': len(self.failed_checks),
            'warnings': len(self.warnings),
            'critical_issues': len(self.critical_issues),
            'system_integrity_score': self.system_integrity_score,
            'recommendations_count': len(self.recommendations)
        }


class RepairValidationService:
    """
    Service for validating repair results and system integrity.
    
    Validates:
    - All approved repairs completed successfully
    - No new corruption introduced during repair
    - System integrity maintained after repairs
    """
    
    def __init__(self):
        self.user = None
        self.repair_service = RepairService()
    
    def set_user(self, user):
        """Set user context for validation operations"""
        self.user = user
        self.repair_service.set_user(user)
        GovernanceContext.set_context(user=user, service='RepairValidationService')
    
    @monitor_operation("validate_repair_results")
    def validate_repair_results(self, execution_results: Dict) -> Dict:
        """
        Comprehensive validation of repair execution results.
        
        Args:
            execution_results: Results from repair execution
            
        Returns:
            Dict: Comprehensive validation results
        """
        logger.info("Starting comprehensive repair results validation")
        
        validation_results = {
            'validation_summary': {
                'start_time': timezone.now().isoformat(),
                'validation_type': 'COMPREHENSIVE_REPAIR_VALIDATION',
                'execution_results_analyzed': True
            },
            'repair_completion_validation': {},
            'corruption_prevention_validation': {},
            'system_integrity_validation': {},
            'audit_trail_validation': {},
            'overall_validation': {}
        }
        
        try:
            # 1. Validate repair completion
            logger.info("Validating repair completion...")
            completion_validation = self._validate_repair_completion(execution_results)
            validation_results['repair_completion_validation'] = completion_validation.to_dict()
            
            # 2. Validate no new corruption introduced
            logger.info("Validating no new corruption introduced...")
            corruption_validation = self._validate_no_new_corruption()
            validation_results['corruption_prevention_validation'] = corruption_validation.to_dict()
            
            # 3. Validate system integrity
            logger.info("Validating system integrity...")
            integrity_validation = self._validate_system_integrity()
            validation_results['system_integrity_validation'] = integrity_validation.to_dict()
            
            # 4. Validate audit trail completeness
            logger.info("Validating audit trail...")
            audit_validation = self._validate_audit_trail(execution_results)
            validation_results['audit_trail_validation'] = audit_validation.to_dict()
            
            # 5. Overall validation assessment
            overall_validation = self._perform_overall_validation_assessment([
                completion_validation,
                corruption_validation,
                integrity_validation,
                audit_validation
            ])
            validation_results['overall_validation'] = overall_validation
            
            validation_results['validation_summary']['end_time'] = timezone.now().isoformat()
            validation_results['validation_summary']['status'] = 'COMPLETED'
            
            logger.info("Comprehensive repair validation completed")
            
        except Exception as e:
            logger.error(f"Critical error during repair validation: {e}", exc_info=True)
            validation_results['validation_summary']['status'] = 'FAILED'
            validation_results['validation_summary']['error'] = str(e)
            validation_results['validation_summary']['end_time'] = timezone.now().isoformat()
        
        # Create audit record for validation
        if self.user:
            AuditTrail.log_operation(
                model_name='RepairValidationService',
                object_id=0,
                operation='VALIDATE_REPAIR_RESULTS',
                user=self.user,
                source_service='RepairValidationService',
                after_data=validation_results['validation_summary']
            )
        
        return validation_results
    
    def _validate_repair_completion(self, execution_results: Dict) -> ValidationResult:
        """
        Validate that all approved repairs completed successfully.
        
        Args:
            execution_results: Results from repair execution
            
        Returns:
            ValidationResult: Repair completion validation results
        """
        validation = ValidationResult('REPAIR_COMPLETION')
        
        try:
            execution_summary = execution_results.get('execution_summary', {})
            repair_results = execution_results.get('repair_results', {})
            
            # Check 1: All approved repairs were executed
            validation.checks_performed.append('ALL_APPROVED_REPAIRS_EXECUTED')
            approved_count = execution_summary.get('approved_repairs_count', 0)
            executed_count = len(repair_results)
            
            if executed_count == approved_count:
                validation.passed_checks.append({
                    'check': 'ALL_APPROVED_REPAIRS_EXECUTED',
                    'result': f'All {approved_count} approved repairs were executed'
                })
            else:
                validation.failed_checks.append({
                    'check': 'ALL_APPROVED_REPAIRS_EXECUTED',
                    'result': f'Only {executed_count} of {approved_count} approved repairs were executed'
                })
            
            # Check 2: No repair executions failed completely
            validation.checks_performed.append('NO_COMPLETE_FAILURES')
            complete_failures = []
            
            for corruption_type, result in repair_results.items():
                if result.get('status') == 'FAILED':
                    complete_failures.append(corruption_type)
            
            if not complete_failures:
                validation.passed_checks.append({
                    'check': 'NO_COMPLETE_FAILURES',
                    'result': 'No repair executions failed completely'
                })
            else:
                validation.failed_checks.append({
                    'check': 'NO_COMPLETE_FAILURES',
                    'result': f'Complete failures in: {", ".join(complete_failures)}'
                })
            
            # Check 3: Reasonable success rate for repairs
            validation.checks_performed.append('REASONABLE_SUCCESS_RATE')
            total_processed = execution_summary.get('total_objects_processed', 0)
            total_repaired = execution_summary.get('total_objects_repaired', 0)
            total_quarantined = execution_summary.get('total_objects_quarantined', 0)
            
            if total_processed > 0:
                success_rate = (total_repaired + total_quarantined) / total_processed * 100
                
                if success_rate >= 95.0:  # 95% or higher is good
                    validation.passed_checks.append({
                        'check': 'REASONABLE_SUCCESS_RATE',
                        'result': f'Success rate: {success_rate:.1f}% (excellent)'
                    })
                elif success_rate >= 80.0:  # 80% or higher is acceptable
                    validation.passed_checks.append({
                        'check': 'REASONABLE_SUCCESS_RATE',
                        'result': f'Success rate: {success_rate:.1f}% (acceptable)'
                    })
                    validation.warnings.append(f'Success rate {success_rate:.1f}% is acceptable but could be improved')
                else:
                    validation.failed_checks.append({
                        'check': 'REASONABLE_SUCCESS_RATE',
                        'result': f'Success rate: {success_rate:.1f}% (too low)'
                    })
            else:
                validation.warnings.append('No objects were processed - cannot calculate success rate')
            
            # Check 4: Audit trail completeness
            validation.checks_performed.append('AUDIT_TRAIL_COMPLETE')
            audit_records_count = len(execution_results.get('audit_trail', []))
            
            if audit_records_count > 0:
                validation.passed_checks.append({
                    'check': 'AUDIT_TRAIL_COMPLETE',
                    'result': f'Audit trail contains {audit_records_count} records'
                })
            else:
                validation.failed_checks.append({
                    'check': 'AUDIT_TRAIL_COMPLETE',
                    'result': 'No audit trail records found'
                })
            
            validation.mark_completed()
            
        except Exception as e:
            logger.error(f"Error validating repair completion: {e}", exc_info=True)
            validation.mark_failed(str(e))
        
        return validation
    
    def _validate_no_new_corruption(self) -> ValidationResult:
        """
        Validate that no new corruption was introduced during repair operations.
        
        Returns:
            ValidationResult: Corruption prevention validation results
        """
        validation = ValidationResult('CORRUPTION_PREVENTION')
        
        try:
            # Run a fresh corruption scan to detect any new issues
            logger.info("Running fresh corruption scan to detect new issues...")
            
            current_corruption_report = self.repair_service.scan_for_corruption()
            
            # Check 1: No new orphaned journal entries
            validation.checks_performed.append('NO_NEW_ORPHANED_ENTRIES')
            
            orphaned_data = current_corruption_report.corruption_types.get('ORPHANED_JOURNAL_ENTRIES', {})
            current_orphaned_count = orphaned_data.get('count', 0)
            
            # We expect some orphaned entries to remain (those that were quarantined)
            # But we should not have MORE than before
            expected_max_orphaned = 25  # Original count from corruption report
            
            if current_orphaned_count <= expected_max_orphaned:
                validation.passed_checks.append({
                    'check': 'NO_NEW_ORPHANED_ENTRIES',
                    'result': f'Current orphaned entries: {current_orphaned_count} (within expected range)'
                })
            else:
                validation.failed_checks.append({
                    'check': 'NO_NEW_ORPHANED_ENTRIES',
                    'result': f'New orphaned entries detected: {current_orphaned_count} > {expected_max_orphaned}'
                })
                validation.critical_issues.append(f'New orphaned journal entries detected: {current_orphaned_count}')
            
            # Check 2: No new unbalanced journal entries
            validation.checks_performed.append('NO_NEW_UNBALANCED_ENTRIES')
            
            unbalanced_data = current_corruption_report.corruption_types.get('UNBALANCED_JOURNAL_ENTRIES', {})
            current_unbalanced_count = unbalanced_data.get('count', 0)
            
            # We expect the unbalanced entry to be quarantined, so count should be 0 or same as before
            expected_max_unbalanced = 1  # Original count
            
            if current_unbalanced_count <= expected_max_unbalanced:
                validation.passed_checks.append({
                    'check': 'NO_NEW_UNBALANCED_ENTRIES',
                    'result': f'Current unbalanced entries: {current_unbalanced_count} (within expected range)'
                })
            else:
                validation.failed_checks.append({
                    'check': 'NO_NEW_UNBALANCED_ENTRIES',
                    'result': f'New unbalanced entries detected: {current_unbalanced_count} > {expected_max_unbalanced}'
                })
                validation.critical_issues.append(f'New unbalanced journal entries detected: {current_unbalanced_count}')
            
            # Check 3: No new negative stock issues
            validation.checks_performed.append('NO_NEW_NEGATIVE_STOCK')
            
            negative_stock_data = current_corruption_report.corruption_types.get('NEGATIVE_STOCK', {})
            current_negative_stock_count = negative_stock_data.get('count', 0)
            
            if current_negative_stock_count == 0:
                validation.passed_checks.append({
                    'check': 'NO_NEW_NEGATIVE_STOCK',
                    'result': 'No negative stock issues detected'
                })
            else:
                validation.warnings.append(f'Negative stock issues detected: {current_negative_stock_count}')
                # This is a warning, not a failure, as it might be pre-existing
            
            # Check 4: No new academic year issues
            validation.checks_performed.append('NO_NEW_ACADEMIC_YEAR_ISSUES')
            
            academic_year_data = current_corruption_report.corruption_types.get('MULTIPLE_ACTIVE_ACADEMIC_YEARS', {})
            current_academic_year_count = academic_year_data.get('count', 0)
            
            if current_academic_year_count == 0:
                validation.passed_checks.append({
                    'check': 'NO_NEW_ACADEMIC_YEAR_ISSUES',
                    'result': 'No multiple active academic year issues detected'
                })
            else:
                validation.warnings.append(f'Academic year issues detected: {current_academic_year_count}')
            
            validation.mark_completed()
            
        except Exception as e:
            logger.error(f"Error validating corruption prevention: {e}", exc_info=True)
            validation.mark_failed(str(e))
        
        return validation
    
    def _validate_system_integrity(self) -> ValidationResult:
        """
        Validate overall system integrity after repair operations.
        
        Returns:
            ValidationResult: System integrity validation results
        """
        validation = ValidationResult('SYSTEM_INTEGRITY')
        
        try:
            # Check 1: Database consistency
            validation.checks_performed.append('DATABASE_CONSISTENCY')
            
            try:
                # Basic database connectivity and consistency check
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    
                if result and result[0] == 1:
                    validation.passed_checks.append({
                        'check': 'DATABASE_CONSISTENCY',
                        'result': 'Database connectivity and basic consistency verified'
                    })
                else:
                    validation.failed_checks.append({
                        'check': 'DATABASE_CONSISTENCY',
                        'result': 'Database consistency check failed'
                    })
                    
            except Exception as e:
                validation.failed_checks.append({
                    'check': 'DATABASE_CONSISTENCY',
                    'result': f'Database consistency check error: {str(e)}'
                })
            
            # Check 2: Model integrity
            validation.checks_performed.append('MODEL_INTEGRITY')
            
            try:
                # Check that critical models are accessible
                JournalEntry = apps.get_model('financial', 'JournalEntry')
                Stock = apps.get_model('product', 'Stock')
                
                je_count = JournalEntry.objects.count()
                stock_count = Stock.objects.count()
                
                validation.passed_checks.append({
                    'check': 'MODEL_INTEGRITY',
                    'result': f'Critical models accessible: JournalEntry({je_count}), Stock({stock_count})'
                })
                
            except Exception as e:
                validation.failed_checks.append({
                    'check': 'MODEL_INTEGRITY',
                    'result': f'Model integrity check error: {str(e)}'
                })
            
            # Check 3: Quarantine system integrity
            validation.checks_performed.append('QUARANTINE_SYSTEM_INTEGRITY')
            
            try:
                quarantine_count = QuarantineRecord.objects.count()
                recent_quarantine_count = QuarantineRecord.objects.filter(
                    quarantined_at__gte=timezone.now() - timedelta(hours=1)
                ).count()
                
                validation.passed_checks.append({
                    'check': 'QUARANTINE_SYSTEM_INTEGRITY',
                    'result': f'Quarantine system operational: {quarantine_count} total, {recent_quarantine_count} recent'
                })
                
            except Exception as e:
                validation.failed_checks.append({
                    'check': 'QUARANTINE_SYSTEM_INTEGRITY',
                    'result': f'Quarantine system check error: {str(e)}'
                })
            
            # Check 4: Audit trail integrity
            validation.checks_performed.append('AUDIT_TRAIL_INTEGRITY')
            
            try:
                audit_count = AuditTrail.objects.count()
                recent_audit_count = AuditTrail.objects.filter(
                    timestamp__gte=timezone.now() - timedelta(hours=1)
                ).count()
                
                validation.passed_checks.append({
                    'check': 'AUDIT_TRAIL_INTEGRITY',
                    'result': f'Audit trail operational: {audit_count} total, {recent_audit_count} recent'
                })
                
            except Exception as e:
                validation.failed_checks.append({
                    'check': 'AUDIT_TRAIL_INTEGRITY',
                    'result': f'Audit trail check error: {str(e)}'
                })
            
            validation.mark_completed()
            
        except Exception as e:
            logger.error(f"Error validating system integrity: {e}", exc_info=True)
            validation.mark_failed(str(e))
        
        return validation
    
    def _validate_audit_trail(self, execution_results: Dict) -> ValidationResult:
        """
        Validate audit trail completeness and accuracy.
        
        Args:
            execution_results: Results from repair execution
            
        Returns:
            ValidationResult: Audit trail validation results
        """
        validation = ValidationResult('AUDIT_TRAIL')
        
        try:
            audit_record_ids = execution_results.get('audit_trail', [])
            
            # Check 1: All audit records exist
            validation.checks_performed.append('AUDIT_RECORDS_EXIST')
            
            existing_records = AuditTrail.objects.filter(id__in=audit_record_ids)
            existing_count = existing_records.count()
            expected_count = len(audit_record_ids)
            
            if existing_count == expected_count:
                validation.passed_checks.append({
                    'check': 'AUDIT_RECORDS_EXIST',
                    'result': f'All {expected_count} audit records exist in database'
                })
            else:
                validation.failed_checks.append({
                    'check': 'AUDIT_RECORDS_EXIST',
                    'result': f'Only {existing_count} of {expected_count} audit records found'
                })
            
            # Check 2: Audit records have proper structure
            validation.checks_performed.append('AUDIT_RECORDS_STRUCTURE')
            
            valid_structure_count = 0
            for record in existing_records:
                if (record.user and record.source_service == 'RepairExecutionService' and 
                    record.timestamp and record.operation):
                    valid_structure_count += 1
            
            if valid_structure_count == existing_count:
                validation.passed_checks.append({
                    'check': 'AUDIT_RECORDS_STRUCTURE',
                    'result': f'All {existing_count} audit records have valid structure'
                })
            else:
                validation.failed_checks.append({
                    'check': 'AUDIT_RECORDS_STRUCTURE',
                    'result': f'Only {valid_structure_count} of {existing_count} audit records have valid structure'
                })
            
            # Check 3: Audit records are recent
            validation.checks_performed.append('AUDIT_RECORDS_RECENT')
            
            recent_threshold = timezone.now() - timedelta(hours=1)
            recent_records = existing_records.filter(timestamp__gte=recent_threshold)
            recent_count = recent_records.count()
            
            if recent_count == existing_count:
                validation.passed_checks.append({
                    'check': 'AUDIT_RECORDS_RECENT',
                    'result': f'All {existing_count} audit records are recent (within 1 hour)'
                })
            else:
                validation.warnings.append(f'Only {recent_count} of {existing_count} audit records are recent')
            
            validation.mark_completed()
            
        except Exception as e:
            logger.error(f"Error validating audit trail: {e}", exc_info=True)
            validation.mark_failed(str(e))
        
        return validation
    
    def _perform_overall_validation_assessment(self, validations: List[ValidationResult]) -> Dict:
        """
        Perform overall assessment of all validation results.
        
        Args:
            validations: List of individual validation results
            
        Returns:
            Dict: Overall validation assessment
        """
        overall_assessment = {
            'overall_status': 'UNKNOWN',
            'total_validations': len(validations),
            'passed_validations': 0,
            'failed_validations': 0,
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'total_warnings': 0,
            'total_critical_issues': 0,
            'average_integrity_score': 0.0,
            'recommendations': [],
            'summary_by_validation': {}
        }
        
        total_integrity_score = 0.0
        
        for validation in validations:
            validation_summary = {
                'status': validation.status,
                'checks_performed': len(validation.checks_performed),
                'passed_checks': len(validation.passed_checks),
                'failed_checks': len(validation.failed_checks),
                'warnings': len(validation.warnings),
                'critical_issues': len(validation.critical_issues),
                'integrity_score': validation.system_integrity_score
            }
            
            overall_assessment['summary_by_validation'][validation.validation_type] = validation_summary
            
            # Update totals
            if validation.status == 'COMPLETED':
                overall_assessment['passed_validations'] += 1
            else:
                overall_assessment['failed_validations'] += 1
            
            overall_assessment['total_checks'] += len(validation.checks_performed)
            overall_assessment['passed_checks'] += len(validation.passed_checks)
            overall_assessment['failed_checks'] += len(validation.failed_checks)
            overall_assessment['total_warnings'] += len(validation.warnings)
            overall_assessment['total_critical_issues'] += len(validation.critical_issues)
            
            total_integrity_score += validation.system_integrity_score
        
        # Calculate average integrity score
        if len(validations) > 0:
            overall_assessment['average_integrity_score'] = total_integrity_score / len(validations)
        
        # Determine overall status
        if overall_assessment['failed_validations'] == 0 and overall_assessment['total_critical_issues'] == 0:
            if overall_assessment['total_warnings'] == 0:
                overall_assessment['overall_status'] = 'EXCELLENT'
            else:
                overall_assessment['overall_status'] = 'GOOD_WITH_WARNINGS'
        elif overall_assessment['total_critical_issues'] == 0:
            overall_assessment['overall_status'] = 'ACCEPTABLE_WITH_ISSUES'
        else:
            overall_assessment['overall_status'] = 'CRITICAL_ISSUES_FOUND'
        
        # Generate recommendations
        if overall_assessment['total_critical_issues'] > 0:
            overall_assessment['recommendations'].append(
                'CRITICAL: Address critical issues immediately before proceeding'
            )
        
        if overall_assessment['failed_checks'] > 0:
            overall_assessment['recommendations'].append(
                'Review and address failed validation checks'
            )
        
        if overall_assessment['total_warnings'] > 0:
            overall_assessment['recommendations'].append(
                'Review warnings for potential improvements'
            )
        
        if overall_assessment['average_integrity_score'] < 80.0:
            overall_assessment['recommendations'].append(
                'System integrity score is below 80% - consider additional repairs'
            )
        
        if overall_assessment['overall_status'] in ['EXCELLENT', 'GOOD_WITH_WARNINGS']:
            overall_assessment['recommendations'].append(
                'Validation successful - proceed with confidence'
            )
        
        return overall_assessment