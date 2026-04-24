from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'governance'

urlpatterns = [
    # Governance Settings Hub
    path('settings/', views.GovernanceSettingsView.as_view(), name='governance_settings'),
    
    # Audit Management
    path('audit/', views.AuditManagementView.as_view(), name='audit_management'),
    path('audit/delete-old/', views.delete_old_audit_logs, name='delete_old_audit_logs'),
    
    # Exception Management
    path('exception/<int:audit_id>/resolve/', views.mark_exception_resolved, name='mark_exception_resolved'),
    path('exception/<int:audit_id>/ignore/', views.mark_exception_ignored, name='mark_exception_ignored'),
    path('exception/<int:audit_id>/recheck/', views.recheck_exception, name='recheck_exception'),
    
    # System Health
    path('health/', views.SystemHealthView.as_view(), name='system_health'),
    
    # Security Center
    path('security/', views.SecurityCenterView.as_view(), name='security_center'),
    path('security/incident/<int:incident_id>/', views.get_incident_details, name='get_incident_details'),
    path('security/incident/<int:incident_id>/resolve/', views.resolve_incident, name='resolve_incident'),
    path('security/ip/<str:ip_address>/block/', views.block_ip_address, name='block_ip'),
    path('security/ip/<int:blocked_ip_id>/unblock/', views.unblock_ip_address, name='unblock_ip'),
    path('security/session/<int:session_id>/terminate/', views.terminate_session, name='terminate_session'),
    
    # Redirect old backup URL to new location
    path('backup/', RedirectView.as_view(url='/settings/backup/', permanent=True), name='backup_management'),
    
    # Security Policies
    path('policies/', views.SecurityPoliciesView.as_view(), name='security_policies'),
    path('policies/key/<int:key_id>/rotate/', views.rotate_encryption_key, name='rotate_encryption_key'),
    path('policies/key/create/', views.create_encryption_key, name='create_encryption_key'),
    path('policies/scan/', views.run_security_scan, name='run_security_scan'),
    path('policies/keys/rotate-all/', views.rotate_all_keys, name='rotate_all_keys'),
    path('policies/report/export/', views.export_security_report, name='export_security_report'),
    
    # Signals Management
    path('signals/', views.SignalsManagementView.as_view(), name='signals_management'),
    
    # Permissions Matrix - Redirected to new unified system
    path('permissions/', RedirectView.as_view(url='/users/permissions/dashboard/', permanent=True), name='permissions_matrix_redirect'),
    
    # Reports Builder
    path('reports/', views.ReportsBuilderView.as_view(), name='reports_builder'),
    
    # Reports API
    path('api/reports/fields/', views.GetAvailableFieldsAPI.as_view(), name='api_get_fields'),
    path('api/reports/generate/', views.GenerateReportAPI.as_view(), name='api_generate_report'),
    path('api/reports/save/', views.SaveReportAPI.as_view(), name='api_save_report'),
    path('api/reports/<int:report_id>/run/', views.RunSavedReportAPI.as_view(), name='api_run_report'),
    path('api/reports/<int:report_id>/download/', views.DownloadReportAPI.as_view(), name='api_download_report'),
    path('api/reports/<int:report_id>/delete/', views.DeleteReportAPI.as_view(), name='api_delete_report'),
    path('api/reports/schedule/create/', views.CreateScheduleAPI.as_view(), name='api_create_schedule'),
    path('api/reports/schedule/<int:schedule_id>/pause/', views.PauseScheduleAPI.as_view(), name='api_pause_schedule'),
    path('api/reports/schedule/<int:schedule_id>/resume/', views.ResumeScheduleAPI.as_view(), name='api_resume_schedule'),
    
    # Health Monitoring - Redirect to System Health
    path('monitoring/', RedirectView.as_view(url='/governance/health/', permanent=True), name='health_monitoring'),
]