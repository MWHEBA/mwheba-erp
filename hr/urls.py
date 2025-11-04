"""
URLs لوحدة الموارد البشرية
"""
from django.urls import path, include
from . import views

app_name = 'hr'

urlpatterns = [
    # API URLs
    path('api/', include('hr.api_urls')),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # الموظفين
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    path('employees/check-email/', views.check_employee_email, name='check_employee_email'),
    path('employees/check-mobile/', views.check_employee_mobile, name='check_employee_mobile'),
    path('employees/check-national-id/', views.check_employee_national_id, name='check_employee_national_id'),
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
    
    # مسيرات الرواتب
    path('payroll-runs/', views.payroll_run_list, name='payroll_run_list'),
    path('payroll-runs/process/', views.payroll_run_process, name='payroll_run_process'),
    path('payroll-runs/<str:month>/', views.payroll_run_detail, name='payroll_run_detail'),
    
    # السلف
    path('advances/', views.advance_list, name='advance_list'),
    path('advances/request/', views.advance_request, name='advance_request'),
    path('advances/<int:pk>/', views.advance_detail, name='advance_detail'),
    path('advances/<int:pk>/approve/', views.advance_approve, name='advance_approve'),
    path('advances/<int:pk>/reject/', views.advance_reject, name='advance_reject'),
    
    # إعدادات الرواتب
    path('salary-settings/', views.salary_settings, name='salary_settings'),
    
    # العقود
    path('contracts/', views.contract_list, name='contract_list'),
    path('contracts/<int:pk>/', views.contract_detail, name='contract_detail'),
    path('contracts/<int:pk>/renew/', views.contract_renew, name='contract_renew'),
    path('contracts/<int:pk>/terminate/', views.contract_terminate, name='contract_terminate'),
    path('contracts/expiring/', views.contract_expiring, name='contract_expiring'),
    # نموذج موحد
    path('contracts/form/', views.contract_form, name='contract_form'),
    path('contracts/<int:pk>/form/', views.contract_form, name='contract_form_edit'),
    
    # API قوالب مكونات الراتب
    path('api/salary-templates/', views.get_salary_component_templates, name='salary_templates_api'),
    
    # قوالب مكونات الراتب
    path('salary-component-templates/', views.salary_component_templates_list, name='salary_component_templates_list'),
    path('salary-component-templates/form/', views.salary_component_template_form, name='salary_component_template_form'),
    path('salary-component-templates/<int:pk>/form/', views.salary_component_template_form, name='salary_component_template_form_edit'),
    path('salary-component-templates/<int:pk>/delete/', views.salary_component_template_delete, name='salary_component_template_delete'),
    
    # التقارير
    path('reports/', include([
        path('', views.reports_home, name='reports_home'),
        path('attendance/', views.attendance_report, name='attendance_report'),
        path('leave/', views.leave_report, name='leave_report'),
        path('payroll-report/', views.payroll_report, name='payroll_report'),
        path('employee/', views.employee_report, name='employee_report'),
    ])),
]
