# Governance views package

# Import all main views
from .main_views import (
    GovernanceBaseView,
    AuditManagementView,
    SystemHealthView,
    SecurityCenterView,
    SecurityPoliciesView,
    SignalsManagementView,
    ReportsBuilderView,
    delete_old_audit_logs,
    mark_exception_resolved,
    mark_exception_ignored,
    recheck_exception,
    get_incident_details,
    resolve_incident,
    block_ip_address,
    unblock_ip_address,
    terminate_session,
    rotate_encryption_key,
    create_encryption_key,
    run_security_scan,
    rotate_all_keys,
    export_security_report
)

# Import settings view
from .settings_view import GovernanceSettingsView

# Import Reports API views
from .reports_api import (
    GetAvailableFieldsAPI,
    GenerateReportAPI,
    SaveReportAPI,
    RunSavedReportAPI,
    DeleteReportAPI,
    DownloadReportAPI,
    CreateScheduleAPI,
    PauseScheduleAPI,
    ResumeScheduleAPI,
)

# Import payroll signal dashboard views (commented out due to circular import)
# from .payroll_signal_dashboard import (
#     payroll_signal_dashboard,
#     enable_governance,
#     disable_governance,
#     activate_kill_switch,
#     deactivate_kill_switch,
#     promote_signal,
#     api_status,
#     api_signal_metrics,
#     PayrollSignalControlView
# )

# Make all views available at package level
__all__ = [
    'GovernanceBaseView',
    'AuditManagementView',
    'SystemHealthView',
    'SecurityCenterView',
    'SecurityPoliciesView',
    'SignalsManagementView',
    'ReportsBuilderView',
    'GovernanceSettingsView',
    'delete_old_audit_logs',
    'mark_exception_resolved',
    'mark_exception_ignored',
    'recheck_exception',
    'get_incident_details',
    'resolve_incident',
    'block_ip_address',
    'unblock_ip_address',
    'terminate_session',
    'rotate_encryption_key',
    'create_encryption_key',
    'run_security_scan',
    'rotate_all_keys',
    'export_security_report',
    # Reports API
    'GetAvailableFieldsAPI',
    'GenerateReportAPI',
    'SaveReportAPI',
    'RunSavedReportAPI',
    'DeleteReportAPI',
    'DownloadReportAPI',
    'CreateScheduleAPI',
    'PauseScheduleAPI',
    'ResumeScheduleAPI',
]