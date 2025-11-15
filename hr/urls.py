"""
URLs لوحدة الموارد البشرية
"""
from django.urls import path, include
from . import views

app_name = 'hr'

urlpatterns = [
    # API URLs
    path('api/', include('hr.api_urls')),
    
    # New Unified Component Preview APIs
    path('api/contracts/<int:contract_id>/preview-components/', 
         views.contract_preview_components, name='contract_preview_components'),
    path('api/contracts/<int:contract_id>/apply-component-selection/', 
         views.contract_apply_component_selection, name='contract_apply_component_selection'),
    
    # Contract Analysis API
    path('api/employees/<int:employee_id>/components-analysis/', 
         views.employee_components_analysis, name='employee_components_analysis'),
    path('api/contracts/<int:contract_id>/preview-activation/', 
         views.ContractActivationPreviewView.as_view(), name='contract_preview_activation'),
    path('api/contracts/preview-activation/', 
         views.ContractActivationPreviewView.as_view(), name='contract_preview_activation_new'),
    path('api/contracts/<int:contract_id>/smart-activate/', 
         views.SmartContractActivationView.as_view(), name='contract_smart_activate'),
    path('api/employees/<int:employee_id>/optimize-components/', 
         views.contract_optimize_components, name='employee_optimize_components'),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # الموظفين
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/import/', views.employee_import, name='employee_import'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    path('employees/check-email/', views.check_employee_email, name='check_employee_email'),
    path('employees/check-mobile/', views.check_employee_mobile, name='check_employee_mobile'),
    path('employees/check-national-id/', views.check_employee_national_id, name='check_employee_national_id'),
    path('employees/<int:employee_id>/check-component-code/', views.check_component_code, name='check_component_code'),
    # نموذج موحد
    path('employees/form/', views.employee_form, name='employee_form'),
    path('employees/<int:pk>/form/', views.employee_form, name='employee_form_edit'),
    # ربط الموظفين بالمستخدمين
    path('employees/<int:pk>/create-user/', views.employee_create_user, name='employee_create_user'),
    path('employees/<int:pk>/link-user/', views.employee_link_user, name='employee_link_user'),
    path('employees/<int:pk>/unlink-user/', views.employee_unlink_user, name='employee_unlink_user'),
    
    # الأقسام
    path('departments/', views.department_list, name='department_list'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),
    # نموذج موحد
    path('departments/form/', views.department_form, name='department_form'),
    path('departments/<int:pk>/form/', views.department_form, name='department_form_edit'),
    
    # المسميات الوظيفية
    path('job-titles/', views.job_title_list, name='job_title_list'),
    path('job-titles/<int:pk>/delete/', views.job_title_delete, name='job_title_delete'),
    # نموذج موحد
    path('job-titles/form/', views.job_title_form, name='job_title_form'),
    path('job-titles/<int:pk>/form/', views.job_title_form, name='job_title_form_edit'),
    
    # الهيكل التنظيمي
    path('organization-chart/', views.organization_chart, name='organization_chart'),
    
    # إعدادات الموارد البشرية
    path('settings/', views.hr_settings, name='hr_settings'),
    
    # الحضور
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/check-in/', views.attendance_check_in, name='attendance_check_in'),
    path('attendance/check-out/', views.attendance_check_out, name='attendance_check_out'),
    
    # الورديات
    path('shifts/', views.shift_list, name='shift_list'),
    path('shifts/<int:pk>/delete/', views.shift_delete, name='shift_delete'),
    path('shifts/<int:pk>/assign/', views.shift_assign_employees, name='shift_assign_employees'),
    # نموذج موحد
    path('shifts/form/', views.shift_form, name='shift_form'),
    path('shifts/<int:pk>/form/', views.shift_form, name='shift_form_edit'),
    
    # ماكينات البصمة
    path('biometric/', views.biometric_device_list, name='biometric_dashboard'),
    path('biometric-devices/', views.biometric_device_list, name='biometric_device_list'),
    path('biometric-devices/<int:pk>/', views.biometric_device_detail, name='biometric_device_detail'),
    path('biometric-devices/<int:pk>/logs/', views.biometric_device_logs_ajax, name='biometric_device_logs_ajax'),
    path('biometric-devices/<int:pk>/delete/', views.biometric_device_delete, name='biometric_device_delete'),
    # نموذج موحد
    path('biometric-devices/form/', views.biometric_device_form, name='biometric_device_form'),
    path('biometric-devices/<int:pk>/form/', views.biometric_device_form, name='biometric_device_form_edit'),
    path('biometric-devices/<int:pk>/test/', views.biometric_device_test, name='biometric_device_test'),
    path('biometric-devices/<int:pk>/download-agent/', views.biometric_device_download_agent, name='biometric_device_download_agent'),
    path('biometric-devices/<int:pk>/agent-setup/', views.biometric_agent_setup, name='biometric_agent_setup'),
    path('biometric-logs/', views.biometric_log_list, name='biometric_log_list'),
    
    # Biometric Dashboard
    path('biometric/dashboard/', views.biometric_dashboard, name='biometric_dashboard'),
    
    # BiometricUserMapping Management
    path('biometric/mapping/', views.biometric_mapping_list, name='biometric_mapping_list'),
    path('biometric/mapping/create/', views.biometric_mapping_create, name='biometric_mapping_create'),
    path('biometric/mapping/<int:pk>/edit/', views.biometric_mapping_update, name='biometric_mapping_update'),
    path('biometric/mapping/<int:pk>/delete/', views.biometric_mapping_delete, name='biometric_mapping_delete'),
    path('biometric/mapping/bulk-import/', views.biometric_mapping_bulk_import, name='biometric_mapping_bulk_import'),
    
    # Bridge Agent API
    path('api/biometric/bridge-sync/', views.biometric_bridge_sync, name='biometric_bridge_sync'),
    
    # الإجازات
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/request/', views.leave_request, name='leave_request'),
    path('leaves/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:pk>/reject/', views.leave_reject, name='leave_reject'),
    
    # أرصدة الإجازات
    path('leave-balances/', views.leave_balance_list, name='leave_balance_list'),
    path('leave-balances/employee/<int:employee_id>/', views.leave_balance_employee, name='leave_balance_employee'),
    path('leave-balances/accrual-status/<int:employee_id>/', views.leave_balance_accrual_status, name='leave_balance_accrual_status'),
    path('leave-balances/update/', views.leave_balance_update, name='leave_balance_update'),
    path('leave-balances/rollover/', views.leave_balance_rollover, name='leave_balance_rollover'),
    
    # الرواتب
    path('payroll/', views.payroll_list, name='payroll_list'),
    path('payroll/<int:pk>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/<int:pk>/edit-lines/', views.payroll_edit_lines, name='payroll_edit_lines'),
    path('payroll/<int:pk>/approve/', views.payroll_approve, name='payroll_approve'),
    path('payroll/<int:pk>/delete/', views.payroll_delete, name='payroll_delete'),
    # ✨ مسارات الدفع الجديدة
    path('payroll/<int:pk>/pay/', views.payroll_pay, name='payroll_pay'),
    
    # السلف
    path('advances/', views.advance_list, name='advance_list'),
    path('advances/request/', views.advance_request, name='advance_request'),
    path('advances/<int:pk>/', views.advance_detail, name='advance_detail'),
    path('advances/<int:pk>/approve/', views.advance_approve, name='advance_approve'),
    path('advances/<int:pk>/reject/', views.advance_reject, name='advance_reject'),
    
    # معالجة الرواتب المتكاملة
    path('payroll/integrated/', views.integrated_payroll_dashboard, name='integrated_payroll_dashboard'),
    path('payroll/integrated/<int:pk>/', views.payroll_detail_integrated, name='payroll_detail_integrated'),
    path('payroll/integrated/calculate-summaries/', views.calculate_attendance_summaries, name='calculate_attendance_summaries'),
    path('payroll/integrated/process/', views.process_monthly_payrolls, name='process_monthly_payrolls'),
    path('payroll/integrated/calculate/<int:employee_id>/', views.calculate_single_payroll, name='calculate_single_payroll'),
    
    # ملخصات الحضور
    path('attendance/summaries/<int:pk>/', views.attendance_summary_detail, name='attendance_summary_detail'),
    path('attendance/summaries/<int:pk>/approve/', views.approve_attendance_summary, name='approve_attendance_summary'),
    path('attendance/summaries/<int:pk>/recalculate/', views.recalculate_attendance_summary, name='recalculate_attendance_summary'),
    
    # طباعة قسيمة الراتب
    path('payroll/<int:pk>/print/', views.payroll_print, name='payroll_print'),
    
    # العقود
    path('contracts/', views.contract_list, name='contract_list'),
    path('contracts/<int:pk>/', views.contract_detail, name='contract_detail'),
    # نموذج موحد
    path('contracts/form/', views.contract_form, name='contract_form'),
    path('contracts/<int:pk>/form/', views.contract_form, name='contract_form_edit'),
    
    # النظام الموحد للعقود
    path('contracts/unified/create/', views.contract_create_unified, name='contract_create_unified'),
    path('contracts/unified/<int:pk>/edit/', views.contract_edit_unified, name='contract_edit_unified'),
    path('employees/<int:employee_id>/components/unified/', views.contract_components_unified, name='contract_components_unified'),
    # تفعيل العقد
    path('contracts/<int:pk>/activate/', views.contract_activate, name='contract_activate_confirm'),
    path('contracts/<int:pk>/activation-preview/', views.contract_activation_preview, name='contract_activation_preview'),
    path('contracts/<int:pk>/activate-with-components/', views.contract_activate_with_components, name='contract_activate_with_components'),
    
    # إدارة العقود
    path('contracts/<int:pk>/renew/', views.contract_renew, name='contract_renew'),
    path('contracts/<int:pk>/terminate/', views.contract_terminate, name='contract_terminate'),
    path('contracts/expiring/', views.contract_expiring, name='contract_expiring'),
    # الزيادات المجدولة
    path('contracts/<int:pk>/increases/create/', views.contract_create_increase_schedule, name='contract_create_increase_schedule'),
    # المسار الموحد الجديد
    path('contracts/increases/<int:increase_id>/<str:action>/', views.contract_increase_action, name='contract_increase_action'),
    # المسارات القديمة للتوافق (deprecated)
    path('contracts/increases/<int:increase_id>/apply/', views.contract_increase_apply, name='contract_increase_apply'),
    path('contracts/increases/<int:increase_id>/cancel/', views.contract_increase_cancel, name='contract_increase_cancel'),
    # مرفقات العقود
    path('contracts/<int:pk>/documents/upload/', views.contract_document_upload, name='contract_document_upload'),
    path('contracts/<int:pk>/documents/<int:doc_id>/delete/', views.contract_document_delete, name='contract_document_delete'),
    # تعديلات العقود
    path('contracts/<int:pk>/amendments/create/', views.contract_amendment_create, name='contract_amendment_create'),
    
    # API التحقق من تداخل العقود
    path('contracts/check-overlap/', views.contract_check_overlap, name='contract_check_overlap'),
    
    # أدوات المزامنة للبنود
    path('components/<int:pk>/sync/', views.sync_component, name='sync_component'),
    path('contracts/<int:pk>/sync-components/', views.sync_contract_components, name='sync_contract_components'),
    
    # API الموظفين
    path('api/employees/<int:pk>/', views.employee_detail_api, name='employee_detail_api'),
    path('api/employees/<int:employee_id>/components-analysis/', views.employee_components_analysis, name='employee_components_analysis'),
    
    # أدوات الصيانة الإدارية
    path('admin/maintenance/', views.maintenance_dashboard, name='maintenance_dashboard'),
    path('admin/maintenance/overview/', views.maintenance_overview, name='maintenance_overview'),
    path('admin/maintenance/report/', views.maintenance_report, name='maintenance_report'),
    path('admin/maintenance/cleanup_expired/', views.maintenance_cleanup_expired, name='maintenance_cleanup_expired'),
    path('admin/maintenance/cleanup_orphaned/', views.maintenance_cleanup_orphaned, name='maintenance_cleanup_orphaned'),
    path('admin/maintenance/fix_inconsistencies/', views.maintenance_fix_inconsistencies, name='maintenance_fix_inconsistencies'),
    path('admin/maintenance/auto_renewals/', views.maintenance_auto_renewals, name='maintenance_auto_renewals'),
    
    # API قوالب مكونات الراتب
    path('api/salary-templates/', views.get_salary_component_templates, name='salary_templates_api'),
    
    # قوالب مكونات الراتب
    path('salary-component-templates/', views.salary_component_templates_list, name='salary_component_templates_list'),
    path('salary-component-templates/form/', views.salary_component_template_form, name='salary_component_template_form'),
    path('salary-component-templates/<int:pk>/form/', views.salary_component_template_form, name='salary_component_template_form_edit'),
    path('salary-component-templates/<int:pk>/delete/', views.salary_component_template_delete, name='salary_component_template_delete'),
    
    # بنود راتب الموظف
    path('employees/<int:employee_id>/salary-components/', views.employee_salary_components, name='employee_salary_components'),
    
    # النظام الموحد الجديد لبنود الراتب
    path('employees/<int:employee_id>/salary-components/unified/', views.UnifiedSalaryComponentView.as_view(), name='unified_salary_component_create'),
    path('employees/<int:employee_id>/salary-components/unified/<int:component_id>/', views.UnifiedSalaryComponentView.as_view(), name='unified_salary_component_edit'),
    
    # APIs للنظام الموحد
    path('api/salary-components/template-details/', views.get_template_details, name='get_template_details'),
    path('api/salary-components/form-preview/', views.get_form_preview, name='get_form_preview'),
    path('api/salary-components/validate-name/', views.validate_component_name, name='validate_component_name'),
    
    # النظام القديم (سيتم إزالته لاحقاً)
    path('employees/<int:employee_id>/salary-components/add/', views.salary_component_create, name='salary_component_create'),
    path('employees/<int:employee_id>/salary-components/<int:component_id>/edit/', views.salary_component_edit, name='salary_component_edit'),
    path('employees/<int:employee_id>/salary-components/<int:component_id>/delete/', views.salary_component_delete, name='salary_component_delete'),
    path('employees/<int:employee_id>/salary-components/<int:component_id>/toggle/', views.salary_component_toggle_active, name='salary_component_toggle_active'),
    # path('employees/<int:employee_id>/salary-components/quick-add/', views.salary_component_quick_add, name='salary_component_quick_add'), # تم حذفها - النظام الموحد
    
    # إدارة التصنيف والتجديد
    path('employees/<int:employee_id>/salary-components/classify/', views.salary_component_classify, name='salary_component_classify'),
    path('employees/<int:employee_id>/salary-components/renew/<int:component_id>/', views.salary_component_renew, name='salary_component_renew'),
    path('employees/<int:employee_id>/salary-components/bulk-renew/', views.salary_component_bulk_renew, name='salary_component_bulk_renew'),
    
    # التقارير
    path('reports/', include([
        path('', views.reports_home, name='reports_home'),
        path('attendance/', views.attendance_report, name='attendance_report'),
        path('leave/', views.leave_report, name='leave_report'),
        path('payroll-report/', views.payroll_report, name='payroll_report'),
        path('employee/', views.employee_report, name='employee_report'),
    ])),
]
