"""
Test Data Cleanup Manager

Comprehensive cleanup utilities for integrity test data with safety checks
and detailed reporting.
"""

import logging
from typing import Dict, List, Optional, Set
from django.db import transaction, connection
from django.apps import apps
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)


class TestDataCleanupManager:
    """Advanced test data cleanup manager with safety checks"""
    
    def __init__(self):
        self.cleanup_order = [
            # Order matters - clean dependent models first
            'governance.IdempotencyRecord',
            'governance.AuditTrail',
            'governance.QuarantineRecord',
            'product.StockMovement',
            'purchase.PurchaseItem',
            'purchase.Purchase',
            'sale.SaleItem',
            'sale.Sale',
            'financial.JournalEntryLine',
            'financial.JournalEntry',
            'product.Stock',
            'product.Product',
            'product.Category',
            'product.Unit',
            'product.Warehouse',
            'supplier.Supplier',
            'client.Customer',
            'users.User'  # Clean test users last
        ]
        
        self.test_data_patterns = {
            # Patterns to identify test data
            'users.User': ['username__startswith=test_', 'username__startswith=integrity_', 'username__startswith=concurrent_'],
            'product.Warehouse': ['code__startswith=TEST_', 'code__startswith=CONC_', 'code__startswith=CONST_'],
            'product.Product': ['code__startswith=TEST_', 'code__startswith=PPUR_', 'code__startswith=PSAL_', 'code__startswith=CONC_'],
            'supplier.Supplier': ['code__startswith=TEST_', 'code__startswith=CONC_'],
            'client.Customer': ['code__startswith=TEST_', 'code__startswith=CONC_'],
            'purchase.Purchase': ['number__startswith=PUR-'],
            'sale.Sale': ['number__startswith=SAL-'],
            'activities.Activity': ['name__startswith=Test Activity'],
            'governance.IdempotencyRecord': ['operation_type__startswith=TEST_'],
            'governance.AuditTrail': ['source_service=IntegrityTestSuite']
        }
        
        self.safety_checks = {
            'max_records_per_model': 10000,  # Safety limit
            'require_test_patterns': True,   # Only delete records matching test patterns
            'dry_run_first': True,          # Always do dry run first
            'backup_before_delete': False   # Option to backup before deletion
        }
    
    def cleanup_all_test_data(self, dry_run: bool = True) -> Dict:
        """Clean up all test data with comprehensive reporting"""
        logger.info(f"Starting {'dry run' if dry_run else 'actual'} cleanup of all test data...")
        
        cleanup_stats = {
            'dry_run': dry_run,
            'models_processed': 0,
            'total_records_found': 0,
            'total_records_deleted': 0,
            'models': {},
            'errors': [],
            'warnings': [],
            'safety_violations': []
        }
        
        try:
            with transaction.atomic():
                for model_name in self.cleanup_order:
                    try:
                        model_stats = self._cleanup_model(model_name, dry_run)
                        cleanup_stats['models'][model_name] = model_stats
                        cleanup_stats['models_processed'] += 1
                        cleanup_stats['total_records_found'] += model_stats['records_found']
                        cleanup_stats['total_records_deleted'] += model_stats['records_deleted']
                        
                        # Check for safety violations
                        if model_stats['records_found'] > self.safety_checks['max_records_per_model']:
                            cleanup_stats['safety_violations'].append(
                                f"{model_name}: {model_stats['records_found']} records exceeds safety limit"
                            )
                        
                    except Exception as e:
                        error_msg = f"Error cleaning {model_name}: {e}"
                        logger.error(error_msg)
                        cleanup_stats['errors'].append(error_msg)
                        cleanup_stats['models'][model_name] = {
                            'error': str(e),
                            'records_found': 0,
                            'records_deleted': 0
                        }
                
                # If dry run, rollback transaction
                if dry_run:
                    transaction.set_rollback(True)
                    logger.info("Dry run completed - no actual changes made")
                else:
                    logger.info(f"Cleanup completed - {cleanup_stats['total_records_deleted']} records deleted")
        
        except Exception as e:
            error_msg = f"Critical error during cleanup: {e}"
            logger.error(error_msg)
            cleanup_stats['errors'].append(error_msg)
        
        return cleanup_stats
    
    def _cleanup_model(self, model_name: str, dry_run: bool = True) -> Dict:
        """Clean up a specific model"""
        try:
            app_label, model_name_only = model_name.split('.')
            model = apps.get_model(app_label, model_name_only)
            
            # Get test data queryset
            queryset = self._get_test_data_queryset(model, model_name)
            
            # Count records
            records_found = queryset.count()
            
            if records_found == 0:
                logger.debug(f"No test data found in {model_name}")
                return {
                    'records_found': 0,
                    'records_deleted': 0,
                    'patterns_used': self.test_data_patterns.get(model_name, [])
                }
            
            # Safety check
            if records_found > self.safety_checks['max_records_per_model']:
                logger.warning(
                    f"Safety check: {model_name} has {records_found} records "
                    f"(exceeds limit of {self.safety_checks['max_records_per_model']})"
                )
            
            # Delete records (or simulate if dry run)
            records_deleted = 0
            if not dry_run:
                deleted_info = queryset.delete()
                records_deleted = deleted_info[0] if deleted_info else 0
                logger.debug(f"Deleted {records_deleted} records from {model_name}")
            else:
                records_deleted = records_found  # Simulate deletion count
                logger.debug(f"Would delete {records_found} records from {model_name}")
            
            return {
                'records_found': records_found,
                'records_deleted': records_deleted,
                'patterns_used': self.test_data_patterns.get(model_name, [])
            }
            
        except Exception as e:
            logger.error(f"Error cleaning model {model_name}: {e}")
            raise
    
    def _get_test_data_queryset(self, model, model_name: str):
        """Get queryset for test data based on patterns"""
        from django.db.models import Q
        
        patterns = self.test_data_patterns.get(model_name, [])
        
        if not patterns:
            # If no patterns defined, return empty queryset for safety
            logger.warning(f"No test data patterns defined for {model_name} - skipping")
            return model.objects.none()
        
        # Build query from patterns
        query = Q()
        for pattern in patterns:
            if '=' in pattern:
                field, value = pattern.split('=', 1)
                if '__startswith' in field:
                    field_name = field.replace('__startswith', '')
                    query |= Q(**{f"{field_name}__startswith": value})
                elif '__contains' in field:
                    field_name = field.replace('__contains', '')
                    query |= Q(**{f"{field_name}__contains": value})
                else:
                    query |= Q(**{field: value})
        
        return model.objects.filter(query)
    
    def cleanup_specific_models(self, model_names: List[str], dry_run: bool = True) -> Dict:
        """Clean up specific models only"""
        logger.info(f"Cleaning up specific models: {model_names}")
        
        cleanup_stats = {
            'dry_run': dry_run,
            'models_processed': 0,
            'total_records_deleted': 0,
            'models': {},
            'errors': []
        }
        
        try:
            with transaction.atomic():
                for model_name in model_names:
                    if model_name in self.cleanup_order:
                        try:
                            model_stats = self._cleanup_model(model_name, dry_run)
                            cleanup_stats['models'][model_name] = model_stats
                            cleanup_stats['models_processed'] += 1
                            cleanup_stats['total_records_deleted'] += model_stats['records_deleted']
                        except Exception as e:
                            error_msg = f"Error cleaning {model_name}: {e}"
                            cleanup_stats['errors'].append(error_msg)
                            cleanup_stats['models'][model_name] = {'error': str(e)}
                    else:
                        logger.warning(f"Model {model_name} not in cleanup order - skipping")
                
                if dry_run:
                    transaction.set_rollback(True)
        
        except Exception as e:
            error_msg = f"Critical error during specific cleanup: {e}"
            logger.error(error_msg)
            cleanup_stats['errors'].append(error_msg)
        
        return cleanup_stats
    
    def cleanup_by_age(self, days_old: int, dry_run: bool = True) -> Dict:
        """Clean up test data older than specified days"""
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        logger.info(f"Cleaning up test data older than {cutoff_date}")
        
        cleanup_stats = {
            'dry_run': dry_run,
            'cutoff_date': cutoff_date.isoformat(),
            'models_processed': 0,
            'total_records_deleted': 0,
            'models': {},
            'errors': []
        }
        
        # Models with timestamp fields
        timestamped_models = {
            'governance.IdempotencyRecord': 'created_at',
            'governance.AuditTrail': 'timestamp',
            'purchase.Purchase': 'created_at',
            'sale.Sale': 'created_at',
            'activities.Activity': 'created_at',
            'users.User': 'date_joined'
        }
        
        try:
            with transaction.atomic():
                for model_name, timestamp_field in timestamped_models.items():
                    try:
                        app_label, model_name_only = model_name.split('.')
                        model = apps.get_model(app_label, model_name_only)
                        
                        # Get test data older than cutoff
                        base_queryset = self._get_test_data_queryset(model, model_name)
                        old_queryset = base_queryset.filter(**{f"{timestamp_field}__lt": cutoff_date})
                        
                        records_found = old_queryset.count()
                        records_deleted = 0
                        
                        if records_found > 0:
                            if not dry_run:
                                deleted_info = old_queryset.delete()
                                records_deleted = deleted_info[0] if deleted_info else 0
                            else:
                                records_deleted = records_found
                        
                        cleanup_stats['models'][model_name] = {
                            'records_found': records_found,
                            'records_deleted': records_deleted,
                            'timestamp_field': timestamp_field
                        }
                        cleanup_stats['models_processed'] += 1
                        cleanup_stats['total_records_deleted'] += records_deleted
                        
                    except Exception as e:
                        error_msg = f"Error cleaning old data from {model_name}: {e}"
                        cleanup_stats['errors'].append(error_msg)
                        cleanup_stats['models'][model_name] = {'error': str(e)}
                
                if dry_run:
                    transaction.set_rollback(True)
        
        except Exception as e:
            error_msg = f"Critical error during age-based cleanup: {e}"
            logger.error(error_msg)
            cleanup_stats['errors'].append(error_msg)
        
        return cleanup_stats
    
    def get_test_data_statistics(self) -> Dict:
        """Get statistics about test data without deleting"""
        logger.info("Gathering test data statistics...")
        
        stats = {
            'total_test_records': 0,
            'models': {},
            'database_info': {
                'vendor': connection.vendor,
                'database_name': connection.settings_dict.get('NAME', 'unknown')
            }
        }
        
        for model_name in self.cleanup_order:
            try:
                app_label, model_name_only = model_name.split('.')
                model = apps.get_model(app_label, model_name_only)
                
                # Get test data count
                test_queryset = self._get_test_data_queryset(model, model_name)
                test_count = test_queryset.count()
                
                # Get total count
                total_count = model.objects.count()
                
                stats['models'][model_name] = {
                    'test_records': test_count,
                    'total_records': total_count,
                    'test_percentage': (test_count / total_count * 100) if total_count > 0 else 0,
                    'patterns': self.test_data_patterns.get(model_name, [])
                }
                
                stats['total_test_records'] += test_count
                
            except Exception as e:
                logger.warning(f"Error getting stats for {model_name}: {e}")
                stats['models'][model_name] = {'error': str(e)}
        
        return stats
    
    def validate_cleanup_safety(self) -> Dict:
        """Validate that cleanup operations are safe"""
        logger.info("Validating cleanup safety...")
        
        validation = {
            'safe_to_proceed': True,
            'warnings': [],
            'critical_issues': [],
            'recommendations': []
        }
        
        # Check database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as e:
            validation['critical_issues'].append(f"Database connection error: {e}")
            validation['safe_to_proceed'] = False
        
        # Check for production indicators
        db_name = connection.settings_dict.get('NAME', '')
        if 'prod' in db_name.lower() or 'production' in db_name.lower():
            validation['critical_issues'].append(
                f"Database name '{db_name}' suggests production environment"
            )
            validation['safe_to_proceed'] = False
        
        # Check test data volume
        stats = self.get_test_data_statistics()
        if stats['total_test_records'] > 50000:
            validation['warnings'].append(
                f"Large volume of test data: {stats['total_test_records']} records"
            )
            validation['recommendations'].append("Consider cleanup by age or specific models")
        
        # Check for models with no test patterns
        models_without_patterns = [
            model for model in self.cleanup_order
            if model not in self.test_data_patterns
        ]
        
        if models_without_patterns:
            validation['warnings'].append(
                f"Models without test patterns: {models_without_patterns}"
            )
            validation['recommendations'].append(
                "Define test data patterns for all models to ensure safe cleanup"
            )
        
        return validation
    
    def export_cleanup_report(self, cleanup_stats: Dict, filename: Optional[str] = None) -> str:
        """Export cleanup report to file"""
        import json
        from datetime import datetime
        
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"test_data_cleanup_report_{timestamp}.json"
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'cleanup_stats': cleanup_stats,
            'database_info': {
                'vendor': connection.vendor,
                'database_name': connection.settings_dict.get('NAME', 'unknown')
            },
            'cleanup_configuration': {
                'cleanup_order': self.cleanup_order,
                'test_data_patterns': self.test_data_patterns,
                'safety_checks': self.safety_checks
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Cleanup report exported to: {filename}")
        return filename


def main():
    """Command line interface for cleanup manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Data Cleanup Manager')
    parser.add_argument(
        'action',
        choices=['stats', 'cleanup', 'cleanup-old', 'validate'],
        help='Action to perform'
    )
    parser.add_argument(
        '--models',
        nargs='+',
        help='Specific models to clean (for cleanup action)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Days old for cleanup-old action (default: 7)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Perform dry run (default: True)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute cleanup (overrides dry-run)'
    )
    parser.add_argument(
        '--export',
        help='Export report to file'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create cleanup manager
    cleanup_manager = TestDataCleanupManager()
    
    # Determine if this is a dry run
    dry_run = args.dry_run and not args.execute
    
    try:
        if args.action == 'stats':
            stats = cleanup_manager.get_test_data_statistics()
            print("\nTEST DATA STATISTICS")
            print("=" * 50)
            print(f"Total test records: {stats['total_test_records']}")
            print(f"Database: {stats['database_info']['vendor']} - {stats['database_info']['database_name']}")
            print("\nPer Model:")
            for model, model_stats in stats['models'].items():
                if 'error' not in model_stats:
                    print(f"  {model}: {model_stats['test_records']} test / {model_stats['total_records']} total")
        
        elif args.action == 'validate':
            validation = cleanup_manager.validate_cleanup_safety()
            print("\nCLEANUP SAFETY VALIDATION")
            print("=" * 50)
            print(f"Safe to proceed: {validation['safe_to_proceed']}")
            
            if validation['critical_issues']:
                print("\nCRITICAL ISSUES:")
                for issue in validation['critical_issues']:
                    print(f"  - {issue}")
            
            if validation['warnings']:
                print("\nWARNINGS:")
                for warning in validation['warnings']:
                    print(f"  - {warning}")
            
            if validation['recommendations']:
                print("\nRECOMMENDATIONS:")
                for rec in validation['recommendations']:
                    print(f"  - {rec}")
        
        elif args.action == 'cleanup':
            if args.models:
                results = cleanup_manager.cleanup_specific_models(args.models, dry_run)
            else:
                results = cleanup_manager.cleanup_all_test_data(dry_run)
            
            print(f"\nCLEANUP RESULTS ({'DRY RUN' if dry_run else 'EXECUTED'})")
            print("=" * 50)
            print(f"Models processed: {results['models_processed']}")
            print(f"Records deleted: {results['total_records_deleted']}")
            
            if results['errors']:
                print("\nERRORS:")
                for error in results['errors']:
                    print(f"  - {error}")
            
            if args.export:
                filename = cleanup_manager.export_cleanup_report(results, args.export)
                print(f"\nReport exported to: {filename}")
        
        elif args.action == 'cleanup-old':
            results = cleanup_manager.cleanup_by_age(args.days, dry_run)
            
            print(f"\nAGE-BASED CLEANUP RESULTS ({'DRY RUN' if dry_run else 'EXECUTED'})")
            print("=" * 50)
            print(f"Cutoff date: {results['cutoff_date']}")
            print(f"Models processed: {results['models_processed']}")
            print(f"Records deleted: {results['total_records_deleted']}")
            
            if results['errors']:
                print("\nERRORS:")
                for error in results['errors']:
                    print(f"  - {error}")
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())