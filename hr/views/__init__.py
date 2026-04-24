"""
Views لوحدة الموارد البشرية
"""
# الدوال المنقولة للملفات الجديدة
from .employee_views import (
    employee_list,
    employee_detail,
    employee_form,
    employee_delete,
    employee_reinstate,
    check_component_code,
    employee_export,
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
    attendance_export_excel,
    attendance_check_in,
    attendance_check_out,
    attendance_summary_list,
    attendance_summary_detail,
    approve_attendance_summary,
    recalculate_attendance_summary,
    update_absence_multiplier,
    calculate_attendance_summaries,
    calculate_exempt_summaries,
    ramadan_settings_list,
    ramadan_settings_create,
    ramadan_settings_update,
    ramadan_settings_delete,
    fetch_ramadan_dates,
    penalty_list,
    penalty_create,
    penalty_update,
    penalty_delete,
    penalty_toggle_active,
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
    leave_cancel,
    employee_leave_info_api,
    leave_update_multiplier,
)
from .leave_type_views import (
    leave_type_list,
    leave_type_save,
    leave_type_delete,
    leave_type_toggle,
)
from .leave_bulk_operations import (
    bulk_approve_leaves,
    bulk_reject_leaves,
)
from .official_holiday_views import (
    official_holiday_list,
    official_holiday_create,
    official_holiday_update,
    official_holiday_delete,
    official_holiday_toggle,
)
from .permission_views import (
    permission_list,
    permission_request,
    get_permission_quota_ajax,
    permission_detail,
    permission_approve,
    permission_reject,
    permission_type_list,
    permission_type_form,
    permission_type_delete,
)
from .penalty_reward_views import (
    penalty_reward_list,
    penalty_reward_create,
    penalty_reward_detail,
    penalty_reward_edit,
    penalty_reward_delete,
    penalty_reward_approve,
    penalty_reward_reject,
)
from .leave_balance_views import (
    leave_balance_list,
    leave_balance_employee,
    leave_balance_update,
    leave_balance_update_all,
    leave_balance_rollover,
    leave_balance_accrual_status,
    leave_encashment_process,
    leave_balance_get_api,
)
from .contract_views import (
    # CRUD
    contract_list,
    contract_detail,
    contract_form,
    
    # Activation & Preview
    contract_activate,
    contract_activation_preview,
    contract_activate_with_components,
    contract_smart_activate,
    
    # Component Management
    contract_preview_components,
    contract_apply_component_selection,
    contract_optimize_components,
    contract_components_unified,
    sync_component,
    sync_contract_components,
    
    # Documents & Amendments
    contract_document_upload,
    contract_document_delete,
    contract_amendment_create,
)
from .payroll_advance_views import (
    payroll_list,
    payroll_detail,
    payroll_approve,
    payroll_unapprove,
    payroll_delete,
    payroll_export,
    advance_list,
    advance_request,
    advance_detail,
    advance_approve,
    advance_reject,
    advance_pay,
)
from .payroll_line_ajax_views import (
    payroll_line_update,
    payroll_line_add,
    payroll_line_delete,
)
from .payroll_payment_views import (
    payroll_pay,
    payroll_print,
)
from .other_views import (
    organization_chart,
    hr_settings,
    leave_policy_settings,
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
    employee_shift_api,
    contract_check_overlap,
)
from .insurance_views import (
    employee_add_insurance_component,
    insurance_payment_list,
    insurance_payment_generate,
    insurance_payment_pay,
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
    biometric_mapping_export,
    api_link_single_log,
    api_process_single_log,
    api_mapping_suggestions,
    api_bulk_link_logs,
    api_bulk_process_logs,
    api_biometric_stats,
    api_cleanup_old_logs,
    api_process_all_biometric_logs,
    api_reset_month_processing,
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

# إضافة دوال العقود الإضافية (من contract_views الموحد)
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
from .contract_import import (
    contract_import,
    contract_import_template,
)
# ملاحظة: تم حذف contract_views_new.py ودمج contract_activate في contract_views.py
# contract_create_with_components و contract_update_with_components تم استبدالهم بـ contract_form
# contract_deactivate و contract_component_delete غير مستخدمين حالياً

# معالجة الرواتب المتكاملة
from .payroll_processing_views import (
    integrated_payroll_dashboard,
    process_monthly_payrolls,
    calculate_single_payroll,
    payroll_recalculate,
)

__all__ = [
    'employee_list',
    'employee_detail',
    'employee_form',
    'employee_delete',
    'employee_reinstate',
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
    'attendance_summary_list',
    'attendance_summary_detail',
    'approve_attendance_summary',
    'recalculate_attendance_summary',
    'update_absence_multiplier',
    'calculate_attendance_summaries',
    'calculate_exempt_summaries',
    'ramadan_settings_list',
    'ramadan_settings_create',
    'ramadan_settings_update',
    'ramadan_settings_delete',
    'fetch_ramadan_dates',
    'penalty_list',
    'penalty_create',
    'penalty_update',
    'penalty_delete',
    'penalty_toggle_active',
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
    'leave_cancel',
    'employee_leave_info_api',
    'leave_update_multiplier',
    'permission_list',
    'permission_request',
    'get_permission_quota_ajax',
    'permission_detail',
    'permission_approve',
    'permission_reject',
    'permission_type_list',
    'leave_balance_list',
    'leave_balance_employee',
    'leave_balance_update',
    'leave_balance_update_all',
    'leave_balance_rollover',
    'leave_balance_accrual_status',
    'leave_encashment_process',
    'leave_balance_get_api',
    # Contract CRUD
    'contract_list',
    'contract_detail',
    'contract_form',
    
    # Contract Activation
    'contract_activate',
    'contract_activation_preview',
    'contract_activate_with_components',
    'contract_smart_activate',
    
    # Contract Components
    'contract_preview_components',
    'contract_apply_component_selection',
    'contract_optimize_components',
    'contract_components_unified',
    'sync_component',
    'sync_contract_components',
    
    # Contract Documents & Amendments
    'contract_document_upload',
    'contract_document_delete',
    'contract_amendment_create',
    'payroll_list',
    'payroll_detail',
    'payroll_approve',
    'payroll_pay',
    'payroll_print',
    'payroll_line_update',
    'payroll_line_add',
    'payroll_line_delete',
    'advance_list',
    'advance_request',
    'advance_detail',
    'advance_approve',
    'advance_reject',
    # دوال أخرى
    'organization_chart',
    'hr_settings',
    'leave_policy_settings',
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
    'employee_shift_api',
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
    # Contract Lifecycle & Increases
    'get_salary_component_templates',
    'contract_renew',
    'contract_terminate',
    'contract_create_increase_schedule',
    'contract_increase_action',
    'contract_increase_apply',
    'contract_increase_cancel',
    'contract_expiring',
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
    'biometric_mapping_export',
    'api_link_single_log',
    'api_process_single_log',
    'api_mapping_suggestions',
    'api_bulk_link_logs',
    'api_bulk_process_logs',
    'api_biometric_stats',
    'api_cleanup_old_logs',
    'api_process_all_biometric_logs',
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

    # معالجة الرواتب المتكاملة
    'integrated_payroll_dashboard',
    'process_monthly_payrolls',
    'calculate_single_payroll',
    'payroll_recalculate',
    'calculate_attendance_summaries',
    'attendance_summary_detail',
    'approve_attendance_summary',
    'recalculate_attendance_summary',
    'payroll_print',
    # الإجازات الرسمية
    'official_holiday_list',
    'official_holiday_create',
    'official_holiday_update',
    'official_holiday_delete',
    'official_holiday_toggle',
    # دفعات التأمين
    'employee_add_insurance_component',
    'insurance_payment_list',
    'insurance_payment_generate',
    'insurance_payment_pay',
]
