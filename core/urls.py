from django.urls import path
from . import api
from .views import (
    # Main views
    dashboard, company_settings, operations_settings, system_settings, get_current_time,
    system_reset, notifications_list, notification_settings,
    # Logs views
    view_error_logs, clear_error_logs,
    # WhatsApp views
    whatsapp_settings_view, whatsapp_webhook_view,
    whatsapp_test_connection_api, whatsapp_send_test_message_api, whatsapp_sync_templates_api,
    whatsapp_create_templates_api,
    whatsapp_prepare_send, whatsapp_send_document, whatsapp_document_status,
    whatsapp_partner_logs, whatsapp_logs_list, whatsapp_resend_message_api,
    whatsapp_log_detail_api, whatsapp_template_preview_api,
    whatsapp_toggle_trigger_api, whatsapp_readiness_metrics_api,
    # Backup views
    backup_management, create_backup, download_backup, restore_backup,
    restore_backup_from_upload,
    list_backups, delete_backup, get_backup_settings, update_backup_settings,
    cleanup_old_backups
)
from .views.module_management import module_management

from .views import security_views
from .views.attachment_views import secure_attachment_download_view, secure_attachment_delete_view

app_name = "core"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("attachments/<int:pk>/download/", secure_attachment_download_view, name="secure_attachment_download"),
    path("attachments/<int:pk>/delete/", secure_attachment_delete_view, name="secure_attachment_delete"),
    
    # ✅ Security endpoints - نقاط الأمان
    path("api/csp-report/", security_views.csp_report_handler, name="csp_report"),
    # path("api/security-log/", security_views.SecurityLogView.as_view(), name="security_log"),
    # path("api/security-dashboard/", security_views.security_dashboard, name="security_dashboard"),
    # path("api/security-report/", security_views.security_report, name="security_report"),
    # path("api/security-incident/", security_views.security_incident_report, name="security_incident"),
    
    # مسارات الإعدادات
    path("settings/company/", company_settings, name="company_settings"),
    path("settings/operations/", operations_settings, name="operations_settings"),
    path("settings/system/", system_settings, name="system_settings"),
    path("settings/modules/", module_management, name="module_management"),
    
    # Unified Backup Management
    path('settings/backup/', backup_management, name='backup_management'),
    path('settings/backup/create/', create_backup, name='backup_create'),
    path('settings/backup/download/<str:backup_id>/', download_backup, name='backup_download'),
    path('settings/backup/restore/', restore_backup, name='backup_restore'),
    path('settings/backup/restore/upload/', restore_backup_from_upload, name='backup_restore_upload'),
    path('settings/backup/list/', list_backups, name='backup_list'),
    path('settings/backup/delete/<str:backup_id>/', delete_backup, name='backup_delete'),
    path('settings/backup/settings/', get_backup_settings, name='backup_settings'),
    path('settings/backup/settings/update/', update_backup_settings, name='backup_settings_update'),
    path('settings/backup/cleanup/', cleanup_old_backups, name='backup_cleanup'),
    
    path("api/current-time/", get_current_time, name="get_current_time"),
    path("system/reset/", system_reset, name="system_reset"),
    # مسارات الأخطاء والـ Logs (للـ Admin فقط)
    path("logs/errors/", view_error_logs, name="view_error_logs"),
    path("logs/errors/clear/", clear_error_logs, name="clear_error_logs"),
    # صفحة عرض كل الإشعارات
    path("notifications/", notifications_list, name="notifications_list"),
    path("notifications/settings/", notification_settings, name="notification_settings"),
    # مسارات WhatsApp Business Cloud API (الإعدادات والـ Webhook والمودال والسجلات) ✅
    path("settings/whatsapp/", whatsapp_settings_view, name="whatsapp_settings"),
    path("logs/whatsapp/", whatsapp_logs_list, name="whatsapp_logs"),
    path("webhooks/whatsapp/", whatsapp_webhook_view, name="whatsapp_webhook"),
    path("api/whatsapp/test-connection/", whatsapp_test_connection_api, name="whatsapp_test_connection"),
    path("api/whatsapp/send-test/", whatsapp_send_test_message_api, name="whatsapp_send_test"),
    path("api/whatsapp/sync-templates/", whatsapp_sync_templates_api, name="whatsapp_sync_templates"),
    path("api/whatsapp/create-templates/", whatsapp_create_templates_api, name="whatsapp_create_templates"),
    path("api/whatsapp/prepare/", whatsapp_prepare_send, name="whatsapp_prepare_send"),
    path("api/whatsapp/send/", whatsapp_send_document, name="whatsapp_send_document"),
    path("api/whatsapp/status/", whatsapp_document_status, name="whatsapp_document_status"),
    path("api/whatsapp/resend/<int:log_id>/", whatsapp_resend_message_api, name="whatsapp_resend_message"),
    path("api/whatsapp/logs/<int:log_id>/", whatsapp_log_detail_api, name="whatsapp_log_detail"),
    path("api/whatsapp/partner/<str:partner_type>/<int:partner_id>/", whatsapp_partner_logs, name="whatsapp_partner_logs"),
    path("api/whatsapp/template-preview/", whatsapp_template_preview_api, name="whatsapp_template_preview"),
    path("api/whatsapp/toggle-trigger/", whatsapp_toggle_trigger_api, name="whatsapp_toggle_trigger"),
    path("api/whatsapp/readiness-metrics/", whatsapp_readiness_metrics_api, name="whatsapp_readiness_metrics"),
    
    # مسارات API الإشعارات - مفعلة ✅
    path('api/notifications/mark-read/<int:notification_id>/', api.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/mark-unread/<int:notification_id>/', api.mark_notification_unread, name='mark_notification_unread'),
    path('api/notifications/mark-all-read/', api.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('api/notifications/count/', api.get_notifications_count, name='notifications_count'),
    path('api/notifications/delete-old-read/', api.delete_old_read_notifications, name='delete_old_read_notifications'),
    
    # مسارات API الأساسية
    path('api/dashboard-stats/', api.DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
    path('api/system-health/', api.SystemHealthAPIView.as_view(), name='api_system_health'),
    path('api/dashboard/stats/', api.get_dashboard_stats, name='dashboard_stats'),
    path('api/dashboard/activity/', api.get_recent_activity, name='recent_activity'),
    path('api/test-email/', api.test_email_settings, name='test_email_settings'),
    path('api/upload-company-logo/', api.upload_company_logo, name='upload_company_logo'),
]
