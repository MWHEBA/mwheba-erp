"""
Management command to run comprehensive corruption detection scan.
This command implements Task 17.1 - Run corruption detection on existing data.

Phase 4A Implementation:
- Comprehensive corruption detection using RepairService
- Generate detailed reports with risk assessment
- Present repair recommendations for stakeholder approval
- REPORT-ONLY mode - no repairs executed
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from governance.services.repair_service import RepairService
import json
import logging
import os

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run comprehensive corruption detection scan and generate reports for stakeholder approval'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--corruption-types',
            nargs='+',
            choices=[
                'ORPHANED_JOURNAL_ENTRIES',
                'NEGATIVE_STOCK',
                'MULTIPLE_ACTIVE_ACADEMIC_YEARS',
                'UNBALANCED_JOURNAL_ENTRIES'
            ],
            help='Specific corruption types to scan for (default: all types)'
        )
        
        parser.add_argument(
            '--output-dir',
            type=str,
            default='reports',
            help='Output directory for corruption reports (default: reports)'
        )
        
        parser.add_argument(
            '--format',
            choices=['json', 'markdown', 'both'],
            default='both',
            help='Output format for reports (default: both)'
        )
        
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Include detailed repair plans in the output'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress detailed output'
        )
        
        parser.add_argument(
            '--user',
            type=str,
            help='Username to run the scan as (default: first superuser)'
        )
    
    def handle(self, *args, **options):
        """Execute the comprehensive corruption detection scan"""
        
        try:
            # Get user for audit trail
            user = self._get_scan_user(options.get('user'))
            
            # Initialize RepairService
            repair_service = RepairService()
            repair_service.set_user(user)
            
            # Display scan header
            if not options['quiet']:
                self.stdout.write("="*70)
                self.stdout.write("COMPREHENSIVE CORRUPTION DETECTION SCAN")
                self.stdout.write("Phase 4A - Analysis Only (No Repairs)")
                self.stdout.write("="*70)
                self.stdout.write(f"Scan initiated by: {user.username}")
                self.stdout.write(f"Timestamp: {timezone.now().isoformat()}")
                self.stdout.write("")
            
            # Run corruption scan
            corruption_types = options.get('corruption_types')
            if corruption_types and not options['quiet']:
                self.stdout.write(f"Scanning for specific types: {', '.join(corruption_types)}")
            elif not options['quiet']:
                self.stdout.write("Scanning for all corruption types...")
            
            self.stdout.write("")
            
            # Execute the scan
            corruption_report = repair_service.scan_for_corruption(corruption_types)
            
            # Display scan results
            self._display_scan_results(corruption_report, options['quiet'])
            
            # Generate comprehensive repair report
            if options['detailed']:
                if not options['quiet']:
                    self.stdout.write("Generating comprehensive repair plan...")
                repair_report = repair_service.create_repair_report(corruption_report)
            else:
                repair_report = {
                    'scan_summary': corruption_report.get_summary(),
                    'corruption_details': corruption_report.corruption_types,
                    'policy_recommendations': corruption_report.recommendations,
                    'phase': '4A_ANALYSIS_ONLY',
                    'execution_blocked': True
                }
            
            # Save reports
            self._save_reports(corruption_report, repair_report, options)
            
            # Display next steps
            self._display_next_steps(corruption_report, options['quiet'])
            
            # Return appropriate exit code
            if corruption_report.total_issues > 0:
                self.stdout.write(
                    self.style.WARNING(f"\nScan completed with {corruption_report.total_issues} issues found.")
                )
                return  # Exit code 0 but with warning
            else:
                self.stdout.write(
                    self.style.SUCCESS("\nScan completed - no corruption detected!")
                )
        
        except Exception as e:
            logger.error(f"Error in corruption detection scan: {e}", exc_info=True)
            raise CommandError(f"Corruption scan failed: {e}")
    
    def _get_scan_user(self, username: str = None) -> User:
        """Get user for running the scan"""
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"User '{username}' not found")
        
        # Get first superuser
        superuser = User.objects.filter(is_superuser=True).first()
        if not superuser:
            raise CommandError("No superuser found. Please create a superuser first.")
        
        return superuser
    
    def _display_scan_results(self, corruption_report, quiet: bool):
        """Display scan results summary"""
        if quiet:
            return
        
        self.stdout.write("SCAN RESULTS")
        self.stdout.write("-" * 40)
        
        if corruption_report.total_issues == 0:
            self.stdout.write(self.style.SUCCESS("✓ No corruption detected!"))
            return
        
        self.stdout.write(f"Total issues found: {corruption_report.total_issues}")
        self.stdout.write("")
        
        for corruption_type, data in corruption_report.corruption_types.items():
            count = data['count']
            confidence = data['confidence']
            
            # Color code by confidence
            if confidence == 'HIGH':
                style = self.style.ERROR
            elif confidence == 'MEDIUM':
                style = self.style.WARNING
            else:
                style = self.style.NOTICE
            
            self.stdout.write(
                style(f"• {corruption_type}: {count} issues (Confidence: {confidence})")
            )
            
            # Show sample issues
            if count > 0 and 'issues' in data:
                sample_count = min(3, len(data['issues']))
                for i, issue in enumerate(data['issues'][:sample_count]):
                    if corruption_type == 'ORPHANED_JOURNAL_ENTRIES':
                        self.stdout.write(f"    - Entry #{issue.get('entry_id', 'N/A')}: {issue.get('description', 'N/A')}")
                    elif corruption_type == 'NEGATIVE_STOCK':
                        self.stdout.write(f"    - Product {issue.get('product_name', 'N/A')}: {issue.get('current_quantity', 'N/A')}")
                    elif corruption_type == 'MULTIPLE_ACTIVE_ACADEMIC_YEARS':
                        self.stdout.write(f"    - Year {issue.get('year_name', 'N/A')}: Active")
                    elif corruption_type == 'UNBALANCED_JOURNAL_ENTRIES':
                        self.stdout.write(f"    - Entry #{issue.get('entry_id', 'N/A')}: Diff {issue.get('difference', 'N/A')}")
                
                if count > sample_count:
                    self.stdout.write(f"    ... and {count - sample_count} more issues")
        
        self.stdout.write("")
    
    def _save_reports(self, corruption_report, repair_report, options):
        """Save corruption and repair reports to files"""
        output_dir = options['output_dir']
        format_type = options['format']
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate timestamp for filenames
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        
        # Save corruption report
        if format_type in ['json', 'both']:
            corruption_json_file = os.path.join(output_dir, f'corruption_scan_{timestamp}.json')
            with open(corruption_json_file, 'w', encoding='utf-8') as f:
                json.dump(corruption_report.to_dict(), f, indent=2, ensure_ascii=False, default=str)
            
            if not options['quiet']:
                self.stdout.write(f"✓ Corruption report saved: {corruption_json_file}")
        
        if format_type in ['markdown', 'both']:
            corruption_md_file = os.path.join(output_dir, f'corruption_scan_{timestamp}.md')
            self._save_corruption_markdown(corruption_report, corruption_md_file)
            
            if not options['quiet']:
                self.stdout.write(f"✓ Corruption report saved: {corruption_md_file}")
        
        # Save repair report
        if format_type in ['json', 'both']:
            repair_json_file = os.path.join(output_dir, f'repair_plan_{timestamp}.json')
            with open(repair_json_file, 'w', encoding='utf-8') as f:
                json.dump(repair_report, f, indent=2, ensure_ascii=False, default=str)
            
            if not options['quiet']:
                self.stdout.write(f"✓ Repair plan saved: {repair_json_file}")
        
        if format_type in ['markdown', 'both']:
            repair_md_file = os.path.join(output_dir, f'repair_plan_{timestamp}.md')
            self._save_repair_markdown(repair_report, repair_md_file)
            
            if not options['quiet']:
                self.stdout.write(f"✓ Repair plan saved: {repair_md_file}")
    
    def _save_corruption_markdown(self, corruption_report, filename):
        """Save corruption report in markdown format"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Corruption Detection Report\n\n")
            f.write(f"**Scan Timestamp:** {corruption_report.scan_timestamp.isoformat()}\n")
            f.write(f"**Total Issues:** {corruption_report.total_issues}\n\n")
            
            if corruption_report.total_issues == 0:
                f.write("✅ **No corruption detected!**\n\n")
                return
            
            f.write("## Summary\n\n")
            for corruption_type, data in corruption_report.corruption_types.items():
                confidence_emoji = "🔴" if data['confidence'] == 'HIGH' else "🟡" if data['confidence'] == 'MEDIUM' else "⚪"
                f.write(f"- {confidence_emoji} **{corruption_type}**: {data['count']} issues (Confidence: {data['confidence']})\n")
            
            f.write("\n## Detailed Findings\n\n")
            for corruption_type, data in corruption_report.corruption_types.items():
                f.write(f"### {corruption_type}\n\n")
                f.write(f"**Count:** {data['count']}\n")
                f.write(f"**Confidence:** {data['confidence']}\n\n")
                
                if 'evidence' in data and data['evidence']:
                    f.write("**Evidence:**\n")
                    for key, value in data['evidence'].items():
                        f.write(f"- {key}: {value}\n")
                    f.write("\n")
                
                if data['count'] > 0 and 'issues' in data:
                    f.write("**Sample Issues:**\n")
                    for i, issue in enumerate(data['issues'][:5]):
                        f.write(f"{i+1}. {self._format_issue_for_markdown(corruption_type, issue)}\n")
                    
                    if data['count'] > 5:
                        f.write(f"... and {data['count'] - 5} more issues\n")
                    f.write("\n")
            
            f.write("## Policy Recommendations\n\n")
            for rec in corruption_report.recommendations:
                f.write(f"- **{rec['corruption_type']}**: {rec['policy']} - {rec['reason']}\n")
            
            f.write("\n## Next Steps\n\n")
            f.write("1. Review corruption findings with stakeholders\n")
            f.write("2. Approve specific repair policies for each corruption type\n")
            f.write("3. Schedule Phase 4B execution after approval\n")
            f.write("4. Ensure backup and rollback procedures are in place\n")
    
    def _save_repair_markdown(self, repair_report, filename):
        """Save repair plan in markdown format"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Comprehensive Repair Plan\n\n")
            f.write("**Phase:** 4A Analysis Only (No Repairs)\n")
            f.write("**Execution Blocked:** Yes - Requires Stakeholder Approval\n\n")
            
            # Scan summary
            summary = repair_report.get('scan_summary', {})
            f.write("## Scan Summary\n\n")
            f.write(f"- **Total Issues:** {summary.get('total_issues', 0)}\n")
            f.write(f"- **Corruption Types:** {len(summary.get('corruption_types', []))}\n")
            f.write(f"- **High Confidence Issues:** {summary.get('high_confidence_issues', 0)}\n")
            f.write(f"- **Recommendations:** {summary.get('recommendations_count', 0)}\n\n")
            
            # Risk assessment
            if 'risk_assessment' in repair_report:
                risk = repair_report['risk_assessment']
                f.write("## Risk Assessment\n\n")
                f.write(f"- **Overall Risk Level:** {risk.get('risk_level', 'UNKNOWN')}\n")
                f.write(f"- **Estimated Duration:** {risk.get('total_estimated_duration', 'Unknown')}\n")
                f.write(f"- **Requires Approval:** {risk.get('requires_stakeholder_approval', True)}\n")
                f.write(f"- **Requires Testing:** {risk.get('requires_testing', True)}\n")
                f.write(f"- **Requires Backup:** {risk.get('requires_backup', True)}\n\n")
            
            # Policy recommendations
            f.write("## Policy Recommendations\n\n")
            for rec in repair_report.get('policy_recommendations', []):
                f.write(f"### {rec['corruption_type']}\n")
                f.write(f"- **Policy:** {rec['policy']}\n")
                f.write(f"- **Reason:** {rec['reason']}\n\n")
            
            # Approval requirements
            f.write("## Approval Requirements\n\n")
            f.write("**⚠️ STAKEHOLDER APPROVAL REQUIRED BEFORE EXECUTION**\n\n")
            f.write("This report is for analysis and approval purposes only. No repairs will be executed until:\n\n")
            f.write("1. Stakeholders review and approve the corruption findings\n")
            f.write("2. Specific repair policies are approved for each corruption type\n")
            f.write("3. Risk assessment and execution timeline are approved\n")
            f.write("4. Backup and rollback procedures are validated\n")
            f.write("5. Phase 4B execution is explicitly authorized\n\n")
            
            f.write("## Contact Information\n\n")
            f.write("For questions or approval of this repair plan, please contact:\n")
            f.write("- System Administrator\n")
            f.write("- Database Administrator\n")
            f.write("- Business Stakeholders\n")
    
    def _format_issue_for_markdown(self, corruption_type, issue):
        """Format issue details for markdown display"""
        if corruption_type == 'ORPHANED_JOURNAL_ENTRIES':
            return f"Entry #{issue.get('entry_id', 'N/A')} - {issue.get('description', 'N/A')}"
        elif corruption_type == 'NEGATIVE_STOCK':
            return f"Product {issue.get('product_name', 'N/A')} has quantity {issue.get('current_quantity', 'N/A')}"
        elif corruption_type == 'MULTIPLE_ACTIVE_ACADEMIC_YEARS':
            return f"Academic Year {issue.get('year_name', 'N/A')} is active"
        elif corruption_type == 'UNBALANCED_JOURNAL_ENTRIES':
            return f"Entry #{issue.get('entry_id', 'N/A')} has difference of {issue.get('difference', 'N/A')}"
        else:
            return str(issue)
    
    def _display_next_steps(self, corruption_report, quiet: bool):
        """Display next steps for stakeholder approval"""
        if quiet:
            return
        
        self.stdout.write("")
        self.stdout.write("="*70)
        self.stdout.write("NEXT STEPS - STAKEHOLDER APPROVAL REQUIRED")
        self.stdout.write("="*70)
        
        if corruption_report.total_issues == 0:
            self.stdout.write("✅ No corruption found - system is healthy!")
            self.stdout.write("   Consider running periodic scans to maintain data integrity.")
        else:
            self.stdout.write("📋 PHASE 4A COMPLETE - Analysis Only")
            self.stdout.write("")
            self.stdout.write("Required Actions:")
            self.stdout.write("1. 📊 Review corruption reports with stakeholders")
            self.stdout.write("2. ✅ Approve specific repair policies for each corruption type")
            self.stdout.write("3. 🔍 Validate repair plan compliance and risk assessment")
            self.stdout.write("4. 📅 Schedule Phase 4B execution after approval")
            self.stdout.write("5. 💾 Ensure backup and rollback procedures are in place")
            self.stdout.write("6. 🧪 Conduct rollback testing for high-risk operations")
            self.stdout.write("")
            self.stdout.write("⚠️  NO REPAIRS WILL BE EXECUTED WITHOUT EXPLICIT APPROVAL")
        
        self.stdout.write("="*70)