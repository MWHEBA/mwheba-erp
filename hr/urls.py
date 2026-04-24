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
    path('api/contracts/<int:pk>/preview-activation/', 
         views.contract_activation_preview, name='contract_preview_activation'),
    path('api/contracts/<int:contract_id>/smart-activate/', 
         views.contract_smart_activate, name='contract_smart_activate'),
    path('api/employees/<int:employee_id>/optimize-components/', 
         views.contract_optimize_components, name='employee_optimize_components'),
    
    # الموظفين
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/import/', views.employee_import, name='employee_import'),
    path('employees/export/', views.employee_export, name='employee_export'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    path('employees/<int:pk>/reinstate/', views.employee_reinstate, name='employee_reinstate'),
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
    path('employees/<int:pk>/add-insurance-component/', views.employee_add_insurance_component, name='employee_add_insurance_component'),

    # دفعات التأمين
    path('insurance-payments/', views.insurance_payment_list, name='insurance_payment_list'),
    path('insurance-payments/generate/', views.insurance_payment_generate, name='insurance_payment_generate'),
    path('insurance-payments/<int:pk>/pay/', views.insurance_payment_pay, name='insurance_payment_pay'),
    
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
    path('settings/leave-policy/', views.leave_policy_settings, name='leave_policy_settings'),

    # إعدادات رمضان
    path('ramadan-settings/', views.ramadan_settings_list, name='ramadan_settings_list'),
    path('ramadan-settings/create/', views.ramadan_settings_create, name='ramadan_settings_create'),
    path('ramadan-settings/<int:pk>/update/', views.ramadan_settings_update, name='ramadan_settings_update'),
    path('ramadan-settings/<int:pk>/delete/', views.ramadan_settings_delete, name='ramadan_settings_delete'),
    path('ramadan-settings/fetch-dates/', views.fetch_ramadan_dates, name='fetch_ramadan_dates'),

    # جدول الجزاءات
    path('attendance-penalties/', views.penalty_list, name='penalty_list'),
    path('attendance-penalties/create/', views.penalty_create, name='penalty_create'),
    path('attendance-penalties/<int:pk>/update/', views.penalty_update, name='penalty_update'),
    path('attendance-penalties/<int:pk>/delete/', views.penalty_delete, name='penalty_delete'),
    path('attendance-penalties/<int:pk>/toggle/', views.penalty_toggle_active, name='penalty_toggle_active'),
    
    # الحضور
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/export/', views.attendance_export_excel, name='attendance_export_excel'),
    path('attendance/check-in/', views.attendance_check_in, name='attendance_check_in'),
    path('attendance/check-out/', views.attendance_check_out, name='attendance_check_out'),
    path('attendance/summaries/', views.attendance_summary_list, name='attendance_summary_list'),
    
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
    path('biometric/mapping/export/', views.biometric_mapping_export, name='biometric_mapping_export'),
    
    # Bridge Agent API
    path('api/biometric/bridge-sync/', views.biometric_bridge_sync, name='biometric_bridge_sync'),
    # Biometric logs APIs (linking/processing)
    path('api/biometric/logs/bulk-link/', views.api_bulk_link_logs, name='api_bulk_link_logs'),
    path('api/biometric/logs/cleanup/', views.api_cleanup_old_logs, name='api_cleanup_old_logs'),
    path('api/biometric/logs/process-all/', views.api_process_all_biometric_logs, name='api_process_all_biometric_logs'),
    path('api/biometric/logs/reset-month/', views.api_reset_month_processing, name='api_reset_month_processing'),
    
    # الإجازات الرسمية
    path('official-holidays/', views.official_holiday_list, name='official_holiday_list'),
    path('official-holidays/create/', views.official_holiday_create, name='official_holiday_create'),
    path('official-holidays/<int:pk>/update/', views.official_holiday_update, name='official_holiday_update'),
    path('official-holidays/<int:pk>/delete/', views.official_holiday_delete, name='official_holiday_delete'),
    path('official-holidays/<int:pk>/toggle/', views.official_holiday_toggle, name='official_holiday_toggle'),

    # أنواع الإجازات
    path('leave-types/', views.leave_type_list, name='leave_type_list'),
    path('leave-types/save/', views.leave_type_save, name='leave_type_save'),
    path('leave-types/<int:pk>/save/', views.leave_type_save, name='leave_type_save_edit'),
    path('leave-types/<int:pk>/delete/', views.leave_type_delete, name='leave_type_delete'),
    path('leave-types/<int:pk>/toggle/', views.leave_type_toggle, name='leave_type_toggle'),

    # الإجازات
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/request/', views.leave_request, name='leave_request'),
    path('leaves/<int:pk>/', views.leave_detail, name='leave_detail'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:pk>/reject/', views.leave_reject, name='leave_reject'),
    path('leaves/<int:pk>/cancel/', views.leave_cancel, name='leave_cancel'),
    path('leaves/<int:pk>/update-multiplier/', views.leave_update_multiplier, name='leave_update_multiplier'),
    path('api/employee/<int:employee_id>/leave-info/', views.employee_leave_info_api, name='employee_leave_info_api'),

    # Bulk operations for leaves (Issue #32-35)
    path('leaves/bulk/approve/', views.bulk_approve_leaves, name='bulk_approve_leaves'),
    path('leaves/bulk/reject/', views.bulk_reject_leaves, name='bulk_reject_leaves'),
    
    # الجزاءات والمكافآت
    path('penalties-rewards/', views.penalty_reward_list, name='penalty_reward_list'),
    path('penalties-rewards/create/', views.penalty_reward_create, name='penalty_reward_create'),
    path('penalties-rewards/<int:pk>/', views.penalty_reward_detail, name='penalty_reward_detail'),
    path('penalties-rewards/<int:pk>/edit/', views.penalty_reward_edit, name='penalty_reward_edit'),
    path('penalties-rewards/<int:pk>/delete/', views.penalty_reward_delete, name='penalty_reward_delete'),
    path('penalties-rewards/<int:pk>/approve/', views.penalty_reward_approve, name='penalty_reward_approve'),
    path('penalties-rewards/<int:pk>/reject/', views.penalty_reward_reject, name='penalty_reward_reject'),

    # الأذونات
    path('permissions/', views.permission_list, name='permission_list'),
    path('permissions/request/', views.permission_request, name='permission_request'),
    path('permissions/ajax/quota/', views.get_permission_quota_ajax, name='permission_quota_ajax'),
    path('permissions/<int:pk>/', views.permission_detail, name='permission_detail'),
    path('permissions/<int:pk>/approve/', views.permission_approve, name='permission_approve'),
    path('permissions/<int:pk>/reject/', views.permission_reject, name='permission_reject'),
    path('permission-types/', views.permission_type_list, name='permission_type_list'),
    path('permission-types/add/', views.permission_type_form, name='permission_type_form'),
    path('permission-types/<int:pk>/get/', views.permission_type_form, name='permission_type_get'),
    path('permission-types/<int:pk>/edit/', views.permission_type_form, name='permission_type_edit'),
    path('permission-types/<int:pk>/delete/', views.permission_type_delete, name='permission_type_delete'),
    
    # أرصدة الإجازات
    path('leave-balances/', views.leave_balance_list, name='leave_balance_list'),
    path('leave-balances/employee/<int:employee_id>/', views.leave_balance_employee, name='leave_balance_employee'),
    path('leave-balances/accrual-status/<int:employee_id>/', views.leave_balance_accrual_status, name='leave_balance_accrual_status'),
    path('leave-balances/update/', views.leave_balance_update, name='leave_balance_update'),
    path('leave-balances/get-balance/', views.leave_balance_get_api, name='leave_balance_get_api'),
    path('leave-balances/update-all/', views.leave_balance_update_all, name='leave_balance_update_all'),
    path('leave-balances/rollover/', views.leave_balance_rollover, name='leave_balance_rollover'),
    path('leave-balances/encashment/', views.leave_encashment_process, name='leave_encashment_process'),
    
    # الرواتب
    path('payroll/', views.payroll_list, name='payroll_list'),
    path('payroll/export/', views.payroll_export, name='payroll_export'),
    path('payroll/<int:pk>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/<int:pk>/approve/', views.payroll_approve, name='payroll_approve'),
    path('payroll/<int:pk>/unapprove/', views.payroll_unapprove, name='payroll_unapprove'),
    path('payroll/<int:pk>/delete/', views.payroll_delete, name='payroll_delete'),
    path('payroll/<int:pk>/recalculate/', views.payroll_recalculate, name='payroll_recalculate'),
    # AJAX endpoints for inline line editing
    path('payroll/line/<int:line_pk>/update/', views.payroll_line_update, name='payroll_line_update'),
    path('payroll/line/<int:line_pk>/delete/', views.payroll_line_delete, name='payroll_line_delete'),
    path('payroll/<int:pk>/line/add/', views.payroll_line_add, name='payroll_line_add'),
    # ✨ مسارات الدفع الجديدة
    path('payroll/<int:pk>/pay/', views.payroll_pay, name='payroll_pay'),
    
    # السلف
    path('advances/', views.advance_list, name='advance_list'),
    path('advances/request/', views.advance_request, name='advance_request'),
    path('advances/<int:pk>/', views.advance_detail, name='advance_detail'),
    path('advances/<int:pk>/approve/', views.advance_approve, name='advance_approve'),
    path('advances/<int:pk>/reject/', views.advance_reject, name='advance_reject'),
    path('advances/<int:pk>/pay/', views.advance_pay, name='advance_pay'),
    
    # معالجة الرواتب المتكاملة
    path('payroll/integrated/', views.integrated_payroll_dashboard, name='integrated_payroll_dashboard'),
    path('payroll/integrated/calculate-summaries/', views.calculate_attendance_summaries, name='calculate_attendance_summaries'),
    path('payroll/integrated/process/', views.process_monthly_payrolls, name='process_monthly_payrolls'),
    path('payroll/integrated/calculate/<int:employee_id>/', views.calculate_single_payroll, name='calculate_single_payroll'),
    
    # ملخصات الحضور
    path('attendance/summaries/<int:pk>/', views.attendance_summary_detail, name='attendance_summary_detail'),
    path('attendance/summaries/<int:pk>/approve/', views.approve_attendance_summary, name='approve_attendance_summary'),
    path('attendance/summaries/<int:pk>/recalculate/', views.recalculate_attendance_summary, name='recalculate_attendance_summary'),
    path('attendance/summaries/calculate-exempt/', views.calculate_exempt_summaries, name='calculate_exempt_summaries'),
    
    # تحديث معامل الغياب
    path('attendance/<int:pk>/update-absence-multiplier/', views.update_absence_multiplier, name='update_absence_multiplier'),
    
    # طباعة قسيمة الراتب
    path('payroll/<int:pk>/print/', views.payroll_print, name='payroll_print'),
    
    # العقود
    path('contracts/import/', views.contract_import, name='contract_import'),
    path('contracts/import/template/', views.contract_import_template, name='contract_import_template'),
    path('contracts/', views.contract_list, name='contract_list'),
    path('contracts/<int:pk>/', views.contract_detail, name='contract_detail'),
    # نموذج موحد
    path('contracts/form/', views.contract_form, name='contract_form'),
    path('contracts/<int:pk>/form/', views.contract_form, name='contract_form_edit'),
    
    # النظام الموحد للعقود (تم الدمج في contract_views)
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
    path('api/employees/<int:pk>/shift/', views.employee_shift_api, name='employee_shift_api'),
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
