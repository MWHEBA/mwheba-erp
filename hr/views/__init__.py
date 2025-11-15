"""
Views لوحدة الموارد البشرية
"""
# الدوال المنقولة للملفات الجديدة
from .dashboard import dashboard
from .employee_views import (
    employee_list,
    employee_detail,
    employee_form,
    employee_delete,
    check_component_code,
)
from .employee_import import (
    export_employees,
    employee_import,
    import_employees_from_csv,
    import_employees_from_excel,
)
from .department_views import (
    department_list,
    department_delete,
    department_form,
)
from .job_title_views import (
    job_title_list,
    job_title_delete,
    job_title_form,
)
from .attendance_views import (
    attendance_list,
    attendance_check_in,
    attendance_check_out,
)
from .shift_views import (
    shift_list,
    shift_delete,
    shift_assign_employees,
    shift_form,
)
from .biometric_views import (
    biometric_device_list,
    biometric_device_detail,
    biometric_device_logs_ajax,
    biometric_device_form,
    biometric_device_delete,
    biometric_device_test,
    biometric_agent_setup,
    biometric_device_download_agent,
    biometric_log_list,
)
from .biometric_api import (
    BridgeSyncThrottle,
    biometric_bridge_sync,
)
from .leave_views import (
    leave_list,
    leave_request,
    leave_detail,
    leave_approve,
    leave_reject,
)
from .leave_balance_views import (
    leave_balance_list,
    leave_balance_employee,
    leave_balance_update,
    leave_balance_rollover,
    leave_balance_accrual_status,
)
from .contract_views import (
    contract_list,
    contract_detail,
    contract_activate,
    sync_component,
    sync_contract_components,
    contract_document_upload,
    contract_document_delete,
    contract_amendment_create,
    contract_activation_preview,
    contract_activate_with_components,
)
from .payroll_advance_views import (
    payroll_list,
    payroll_detail,
    payroll_edit_lines,
    payroll_approve,
    payroll_delete,
    advance_list,
    advance_request,
    advance_detail,
    advance_approve,
    advance_reject,
)
from .payroll_payment_views import (
    payroll_pay,
)
from .other_views import (
    organization_chart,
    hr_settings,
    employee_create_user,
    employee_link_user,
    employee_unlink_user,
    check_employee_email,
    check_employee_mobile,
    check_employee_national_id,
    salary_component_templates_list,
    salary_component_template_form,
    salary_component_template_delete,
    employee_detail_api,
    contract_check_overlap,
)
from .salary_component_views import (
    employee_salary_components,
    salary_component_create,
    salary_component_edit,
    salary_component_delete,
    salary_component_toggle_active,
    # salary_component_quick_add, # تم حذفها - النظام الموحد
    salary_component_classify,
    salary_component_renew,
    salary_component_bulk_renew,
    # النظام الموحد الجديد
    UnifiedSalaryComponentView,
    get_template_details,
    get_form_preview,
    validate_component_name,
)
from .report_views import (
    reports_home,
    attendance_report,
    leave_report,
    payroll_report,
    employee_report,
)
from .biometric_advanced_views import (
    biometric_dashboard,
    biometric_mapping_list,
    biometric_mapping_create,
    biometric_mapping_update,
    biometric_mapping_delete,
    biometric_mapping_bulk_import,
    api_link_single_log,
    api_process_single_log,
    api_mapping_suggestions,
    api_bulk_link_logs,
    api_bulk_process_logs,
    api_biometric_stats,
)
from .admin_maintenance_views import (
    maintenance_dashboard,
    maintenance_overview,
    maintenance_report,
    maintenance_cleanup_expired,
    maintenance_cleanup_orphaned,
    maintenance_fix_inconsistencies,
    maintenance_auto_renewals,
    employee_components_analysis,
    test_connection_internal,
)

# النظام الموحد للعقود
from .contract_unified_views import (
    contract_create_unified,
    contract_edit_unified,
    SmartContractActivationView,
    ContractActivationPreviewView,
    contract_optimize_components,
    contract_components_unified,
    contract_preview_components,
    contract_apply_component_selection,
)

# إضافة دوال العقود الإضافية
from .contract_views import (
    get_salary_component_templates,
    contract_renew,
    contract_terminate,
    contract_create_increase_schedule,
    contract_increase_action,
    contract_increase_apply,
    contract_increase_cancel,
    contract_expiring,
)
from .contract_form_views import (
    contract_form,
)
# ملاحظة: تم حذف contract_views_new.py ودمج contract_activate في contract_views.py
# contract_create_with_components و contract_update_with_components تم استبدالهم بـ contract_form
# contract_deactivate و contract_component_delete غير مستخدمين حالياً

# معالجة الرواتب المتكاملة
from .integrated_payroll_views import (
    integrated_payroll_dashboard,
    payroll_detail_integrated,
    calculate_attendance_summaries,
    process_monthly_payrolls,
    calculate_single_payroll,
    attendance_summary_detail,
    approve_attendance_summary,
    recalculate_attendance_summary,
    payroll_print,
)

__all__ = [
    'dashboard',
    'employee_list',
    'employee_detail',
    'employee_form',
    'employee_delete',
    'export_employees',
    'employee_import',
    'department_list',
    'department_delete',
    'department_form',
    'job_title_list',
    'job_title_delete',
    'job_title_form',
    'attendance_list',
    'attendance_check_in',
    'attendance_check_out',
    'shift_list',
    'shift_delete',
    'shift_assign_employees',
    'shift_form',
    'biometric_device_list',
    'biometric_device_detail',
    'biometric_device_logs_ajax',
    'biometric_device_form',
    'biometric_device_delete',
    'biometric_device_test',
    'biometric_agent_setup',
    'biometric_device_download_agent',
    'biometric_log_list',
    'BridgeSyncThrottle',
    'biometric_bridge_sync',
    'leave_list',
    'leave_request',
    'leave_detail',
    'leave_approve',
    'leave_reject',
    'leave_balance_list',
    'leave_balance_employee',
    'leave_balance_update',
    'leave_balance_rollover',
    'leave_balance_accrual_status',
    'contract_list',
    'contract_detail',
    'contract_activate',
    'contract_suspend',
    'contract_reactivate',
    'contract_document_upload',
    'contract_document_delete',
    'contract_amendment_create',
    'contract_activation_preview',
    'contract_activate_with_components',
    'payroll_list',
    'payroll_detail',
    'payroll_edit_lines',
    'payroll_approve',
    'advance_list',
    'advance_request',
    'advance_detail',
    'advance_approve',
    'advance_reject',
    # دوال أخرى
    'organization_chart',
    'hr_settings',
    'employee_create_user',
    'employee_link_user',
    'employee_unlink_user',
    'check_employee_email',
    'check_employee_mobile',
    'check_employee_national_id',
    'salary_component_templates_list',
    'salary_component_template_form',
    'salary_component_template_delete',
    'employee_detail_api',
    'contract_check_overlap',
    # دوال بنود الراتب
    'employee_salary_components',
    'salary_component_create',
    'salary_component_edit',
    'salary_component_delete',
    'salary_component_toggle_active',
    'salary_component_quick_add',
    'salary_component_classify',
    'salary_component_renew',
    'salary_component_bulk_renew',
    # النظام الموحد الجديد لبنود الراتب
    'unified_salary_component_view',
    'get_template_details',
    'get_form_preview',
    'validate_component_name',
    # دوال العقود الإضافية
    'get_salary_component_templates',
    'contract_renew',
    'contract_terminate',
    'contract_create_increase_schedule',
    'contract_increase_action',
    'contract_increase_apply',
    'contract_increase_cancel',
    'contract_expiring',
    'contract_form',
    # دوال التقارير
    'reports_home',
    'attendance_report',
    'leave_report',
    'payroll_report',
    'employee_report',
    # دوال البصمة المتقدمة
    'biometric_dashboard',
    'biometric_mapping_list',
    'biometric_mapping_create',
    'biometric_mapping_update',
    'biometric_mapping_delete',
    'biometric_mapping_bulk_import',
    'api_link_single_log',
    'api_process_single_log',
    'api_mapping_suggestions',
    'api_bulk_link_logs',
    'api_bulk_process_logs',
    'api_biometric_stats',
    # دوال الصيانة الإدارية
    'maintenance_dashboard',
    'maintenance_overview',
    'maintenance_report',
    'maintenance_cleanup_expired',
    'maintenance_cleanup_orphaned',
    'maintenance_fix_inconsistencies',
    'maintenance_auto_renewals',
    'employee_components_analysis',
    'test_connection_internal',
    # النظام الموحد للعقود
    'contract_create_unified',
    'contract_edit_unified',
    'SmartContractActivationView',
    'ContractActivationPreviewView',
    'contract_optimize_components',
    'contract_components_unified',
    # معالجة الرواتب المتكاملة
    'integrated_payroll_dashboard',
    'payroll_detail_integrated',
    'calculate_attendance_summaries',
    'process_monthly_payrolls',
    'calculate_single_payroll',
    'attendance_summary_detail',
    'approve_attendance_summary',
    'recalculate_attendance_summary',
    'payroll_print',
]
