"""
Validate Repair Results - Phase 4B Implementation

This management command validates repair results to ensure all approved repairs
completed successfully, no new corruption was introduced, and system integrity
is maintained.

Usage:
    python manage.py validate_repair_results --execution-report path/to/execution_report.json

Features:
- Verify all approved repairs completed successfully
- Confirm no new corruption introduced during repair
- Validate system integrity after repair operations
- Generate comprehensive validation reports
"""

import json
import os
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.repair_validation_service import RepairValidationService

User = get_user_model()


class Command(BaseCommand):
    help = 'Validate repair results and system integrity (Phase 4B)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--execution-report',
            type=str,
            required=True,
            help='Path to the repair execution report JSON file'
        )
        
        parser.add_argument(
            '--user',
            type=str,
            default='admin',
            help='Username to execute validation as (default: admin)'
        )
        
        parser.add_argument(
            '--output-dir',
            type=str,
            default='reports',
            help='Directory to save validation reports (default: reports)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write("="*70)
        self.stdout.write(self.style.SUCCESS("🔍 REPAIR VALIDATION SERVICE - PHASE 4B"))
        self.stdout.write("="*70)
        self.stdout.write("")
        
        # Validate inputs
        execution_report_path = options['execution_report']
        if not os.path.exists(execution_report_path):
            raise CommandError(f"Execution report file not found: {execution_report_path}")
        
        # Load execution report
        try:
            with open(execution_report_path, 'r', encoding='utf-8') as f:
                execution_report = json.load(f)
            self.stdout.write(f"✅ Loaded execution report: {execution_report_path}")
        except Exception as e:
            raise CommandError(f"Failed to load execution report: {e}")
        
        # Extract execution results
        execution_results = execution_report.get('execution_results', {})
        if not execution_results:
            raise CommandError("No execution results found in report")
        
        # Get user
        try:
            user = User.objects.get(username=options['user'])
            self.stdout.write(f"✅ Running validation as user: {user.username}")
        except User.DoesNotExist:
            raise CommandError(f"User not found: {options['user']}")
        
        # Create output directory
        output_dir = options['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        
        # Display validation summary
        self._display_validation_summary(execution_results)
        
        # Initialize repair validation service
        validation_service = RepairValidationService()
        validation_service.set_user(user)
        
        self.stdout.write("")
        self.stdout.write("🔍 Starting comprehensive validation...")
        self.stdout.write("")
        
        try:
            # Execute comprehensive validation
            validation_results = validation_service.validate_repair_results(execution_results)
            
            # Generate validation report
            report_path = self._generate_validation_report(validation_results, output_dir)
            
            # Display results
            self._display_validation_results(validation_results)
            
            self.stdout.write("")
            self.stdout.write(f"📄 Validation report saved: {report_path}")
            self.stdout.write("")
            
            # Determine final status
            overall_status = validation_results.get('overall_validation', {}).get('overall_status', 'UNKNOWN')
            
            if overall_status == 'EXCELLENT':
                self.stdout.write(self.style.SUCCESS("✅ Validation EXCELLENT - All repairs successful, system integrity maintained!"))
            elif overall_status == 'GOOD_WITH_WARNINGS':
                self.stdout.write(self.style.SUCCESS("✅ Validation GOOD - Repairs successful with minor warnings"))
            elif overall_status == 'ACCEPTABLE_WITH_ISSUES':
                self.stdout.write(self.style.WARNING("⚠️  Validation ACCEPTABLE - Some issues found but no critical failures"))
            elif overall_status == 'CRITICAL_ISSUES_FOUND':
                self.stdout.write(self.style.ERROR("❌ Validation FAILED - Critical issues found, immediate attention required"))
            else:
                self.stdout.write(self.style.WARNING(f"⚠️  Validation status: {overall_status}"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Critical error during validation: {e}"))
            raise CommandError(f"Validation failed: {e}")
        
        self.stdout.write("")
        self.stdout.write("="*70)
    
    def _display_validation_summary(self, execution_results):
        """Display validation summary"""
        self.stdout.write("📋 VALIDATION SUMMARY")
        self.stdout.write("-" * 50)
        
        execution_summary = execution_results.get('execution_summary', {})
        
        self.stdout.write(f"Execution status: {execution_results.get('overall_status', 'Unknown')}")
        self.stdout.write(f"Total objects processed: {execution_summary.get('total_objects_processed', 0)}")
        self.stdout.write(f"Objects repaired: {execution_summary.get('total_objects_repaired', 0)}")
        self.stdout.write(f"Objects quarantined: {execution_summary.get('total_objects_quarantined', 0)}")
        self.stdout.write(f"Objects failed: {execution_summary.get('total_objects_failed', 0)}")
        
        repair_results = execution_results.get('repair_results', {})
        self.stdout.write(f"Repair operations completed: {len(repair_results)}")
        
        self.stdout.write("")
        self.stdout.write("Validating:")
        self.stdout.write("  • Repair completion status")
        self.stdout.write("  • No new corruption introduced")
        self.stdout.write("  • System integrity maintained")
        self.stdout.write("  • Audit trail completeness")
        self.stdout.write("")
    
    def _display_validation_results(self, validation_results):
        """Display validation results"""
        self.stdout.write("📊 VALIDATION RESULTS")
        self.stdout.write("-" * 50)
        
        validation_summary = validation_results.get('validation_summary', {})
        self.stdout.write(f"Validation status: {validation_summary.get('status', 'Unknown')}")
        
        overall_validation = validation_results.get('overall_validation', {})
        self.stdout.write(f"Overall assessment: {overall_validation.get('overall_status', 'Unknown')}")
        self.stdout.write(f"Average integrity score: {overall_validation.get('average_integrity_score', 0):.1f}%")
        self.stdout.write("")
        
        # Display results by validation type
        validation_types = [
            ('repair_completion_validation', 'Repair Completion'),
            ('corruption_prevention_validation', 'Corruption Prevention'),
            ('system_integrity_validation', 'System Integrity'),
            ('audit_trail_validation', 'Audit Trail')
        ]
        
        for key, name in validation_types:
            validation_data = validation_results.get(key, {})
            status = validation_data.get('status', 'Unknown')
            passed_checks = validation_data.get('passed_checks', 0)
            failed_checks = validation_data.get('failed_checks', 0)
            warnings = validation_data.get('warnings', 0)
            
            status_icon = "✅" if status == "COMPLETED" and failed_checks == 0 else "⚠️" if failed_checks == 0 else "❌"
            
            self.stdout.write(f"{status_icon} {name}:")
            self.stdout.write(f"    Status: {status}")
            self.stdout.write(f"    Passed: {passed_checks}, Failed: {failed_checks}, Warnings: {warnings}")
            
            if validation_data.get('critical_issues', 0) > 0:
                self.stdout.write(f"    🚨 Critical issues: {validation_data.get('critical_issues', 0)}")
            
            self.stdout.write("")
        
        # Display recommendations
        recommendations = overall_validation.get('recommendations', [])
        if recommendations:
            self.stdout.write("📋 RECOMMENDATIONS:")
            for i, rec in enumerate(recommendations, 1):
                self.stdout.write(f"  {i}. {rec}")
            self.stdout.write("")
    
    def _generate_validation_report(self, validation_results, output_dir):
        """Generate comprehensive validation report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"repair_validation_report_{timestamp}.json"
        report_path = os.path.join(output_dir, report_filename)
        
        # Add metadata to the report
        report_data = {
            'metadata': {
                'report_type': 'REPAIR_VALIDATION_REPORT',
                'phase': '4B_VALIDATION',
                'generated_at': timezone.now().isoformat(),
                'generator': 'validate_repair_results management command',
                'version': '1.0'
            },
            'validation_results': validation_results
        }
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            
            # Also generate a human-readable markdown report
            markdown_report_path = self._generate_markdown_report(validation_results, output_dir, timestamp)
            
            return report_path
            
        except Exception as e:
            raise CommandError(f"Failed to generate validation report: {e}")
    
    def _generate_markdown_report(self, validation_results, output_dir, timestamp):
        """Generate human-readable markdown report"""
        markdown_filename = f"repair_validation_report_{timestamp}.md"
        markdown_path = os.path.join(output_dir, markdown_filename)
        
        validation_summary = validation_results['validation_summary']
        overall_validation = validation_results.get('overall_validation', {})
        
        markdown_content = f"""# Repair Validation Report - Phase 4B

**Generated:** {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Phase:** 4B - Repair Results Validation  
**Status:** {validation_summary.get('status', 'Unknown')}  
**Overall Assessment:** {overall_validation.get('overall_status', 'Unknown')}

---

## Executive Summary

This report validates the results of approved repair operations executed in Phase 4B of the Code Governance System. The validation ensures all repairs completed successfully, no new corruption was introduced, and system integrity is maintained.

### Validation Summary
- **Validation Status:** {validation_summary.get('status', 'Unknown')}
- **Overall Assessment:** {overall_validation.get('overall_status', 'Unknown')}
- **Average Integrity Score:** {overall_validation.get('average_integrity_score', 0):.1f}%
- **Total Validations:** {overall_validation.get('total_validations', 0)}
- **Passed Validations:** {overall_validation.get('passed_validations', 0)}
- **Failed Validations:** {overall_validation.get('failed_validations', 0)}

### Check Summary
- **Total Checks:** {overall_validation.get('total_checks', 0)}
- **Passed Checks:** {overall_validation.get('passed_checks', 0)}
- **Failed Checks:** {overall_validation.get('failed_checks', 0)}
- **Warnings:** {overall_validation.get('total_warnings', 0)}
- **Critical Issues:** {overall_validation.get('total_critical_issues', 0)}

---

## Validation Results by Category

"""
        
        # Add validation results by category
        validation_categories = [
            ('repair_completion_validation', 'Repair Completion Validation', 
             'Validates that all approved repairs completed successfully'),
            ('corruption_prevention_validation', 'Corruption Prevention Validation', 
             'Confirms no new corruption was introduced during repair operations'),
            ('system_integrity_validation', 'System Integrity Validation', 
             'Validates overall system integrity after repair operations'),
            ('audit_trail_validation', 'Audit Trail Validation', 
             'Validates audit trail completeness and accuracy')
        ]
        
        for key, title, description in validation_categories:
            validation_data = validation_results.get(key, {})
            status = validation_data.get('status', 'Unknown')
            
            status_icon = "✅" if status == "COMPLETED" and validation_data.get('failed_checks', 0) == 0 else "⚠️" if validation_data.get('failed_checks', 0) == 0 else "❌"
            
            markdown_content += f"""### {status_icon} {title}

**Description:** {description}  
**Status:** {status}  
**Integrity Score:** {validation_data.get('system_integrity_score', 0):.1f}%

**Results:**
- ✅ **Passed Checks:** {validation_data.get('passed_checks', 0)}
- ❌ **Failed Checks:** {validation_data.get('failed_checks', 0)}
- ⚠️ **Warnings:** {validation_data.get('warnings', 0)}
- 🚨 **Critical Issues:** {validation_data.get('critical_issues', 0)}

"""
            
            # Add details if there are issues
            if validation_data.get('failed_checks', 0) > 0 or validation_data.get('critical_issues', 0) > 0:
                markdown_content += "**Issues Found:**\n"
                if validation_data.get('failed_checks', 0) > 0:
                    markdown_content += f"- {validation_data.get('failed_checks', 0)} validation checks failed\n"
                if validation_data.get('critical_issues', 0) > 0:
                    markdown_content += f"- {validation_data.get('critical_issues', 0)} critical issues identified\n"
                markdown_content += "\n"
            
            markdown_content += "---\n\n"
        
        # Add recommendations section
        recommendations = overall_validation.get('recommendations', [])
        if recommendations:
            markdown_content += f"""## Recommendations

Based on the validation results, the following recommendations are provided:

"""
            for i, rec in enumerate(recommendations, 1):
                markdown_content += f"{i}. **{rec}**\n"
            
            markdown_content += "\n---\n\n"
        
        # Add next steps based on overall status
        overall_status = overall_validation.get('overall_status', 'UNKNOWN')
        
        markdown_content += "## Next Steps\n\n"
        
        if overall_status == 'EXCELLENT':
            markdown_content += """✅ **VALIDATION EXCELLENT**

All repair operations completed successfully with no issues detected. The system integrity is fully maintained.

### Immediate Actions
- ✅ **Phase 4B Complete** - All approved repairs successfully executed and validated
- ✅ **System Ready** - System is ready for normal operations
- ✅ **Proceed to Phase 5** - Begin ongoing governance monitoring

### Recommendations
- Continue monitoring system for any new corruption patterns
- Review quarantined items for potential manual resolution
- Implement ongoing governance controls as planned
"""
        
        elif overall_status == 'GOOD_WITH_WARNINGS':
            markdown_content += """✅ **VALIDATION GOOD WITH WARNINGS**

Repair operations completed successfully but some warnings were identified. These do not affect system integrity but should be reviewed.

### Immediate Actions
- ✅ **Phase 4B Complete** - All approved repairs successfully executed
- ⚠️ **Review Warnings** - Address identified warnings when convenient
- ✅ **System Operational** - System is ready for normal operations

### Recommendations
- Review warning details and plan resolution
- Monitor system for any related issues
- Proceed with Phase 5 implementation
"""
        
        elif overall_status == 'ACCEPTABLE_WITH_ISSUES':
            markdown_content += """⚠️ **VALIDATION ACCEPTABLE WITH ISSUES**

Repair operations completed but some issues were identified. System integrity is maintained but attention is needed.

### Immediate Actions
- ⚠️ **Review Issues** - Address identified issues promptly
- ✅ **System Stable** - System integrity is maintained
- 🔍 **Monitor Closely** - Increase monitoring frequency

### Recommendations
- Prioritize resolution of identified issues
- Consider additional repair operations if needed
- Delay Phase 5 implementation until issues are resolved
"""
        
        elif overall_status == 'CRITICAL_ISSUES_FOUND':
            markdown_content += """❌ **VALIDATION FAILED - CRITICAL ISSUES**

Critical issues were identified that require immediate attention. System integrity may be compromised.

### Immediate Actions Required
- 🚨 **Address Critical Issues** - Immediate attention required
- 🔍 **Investigate Root Cause** - Determine why repairs failed
- 🛡️ **Protect System Integrity** - Consider rollback if necessary

### Recommendations
- Do not proceed with normal operations until issues are resolved
- Consider emergency rollback procedures
- Engage technical team for immediate resolution
- Postpone Phase 5 implementation indefinitely
"""
        
        else:
            markdown_content += f"""⚠️ **VALIDATION STATUS: {overall_status}**

The validation completed with an unknown or unexpected status. Manual review is required.

### Immediate Actions
- 🔍 **Manual Review Required** - Examine validation results in detail
- 📞 **Contact Technical Team** - Seek expert assistance
- ⏸️ **Pause Operations** - Do not proceed until status is clarified

### Recommendations
- Review all validation details manually
- Determine appropriate next steps based on findings
- Document any issues for future reference
"""
        
        markdown_content += f"""

---

## Technical Details

**Validation Duration:** {validation_summary.get('duration', 'Unknown')}  
**Validation Type:** {validation_summary.get('validation_type', 'Unknown')}  
**Execution Results Analyzed:** {validation_summary.get('execution_results_analyzed', False)}

---

**Report Generated:** {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Generator:** Code Governance System - Repair Validation Service  
**Phase:** 4B - Repair Results Validation
"""
        
        try:
            with open(markdown_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            return markdown_path
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Failed to generate markdown report: {e}"))
            return None