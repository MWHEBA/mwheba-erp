from django.urls import path
from . import api
from .views import (
    # Main views
    dashboard, company_settings, system_settings, get_current_time,
    system_reset, notifications_list, notification_settings, whatsapp_settings,
    whatsapp_webhook,
    # Logs views
    view_error_logs, clear_error_logs,
    # Backup views
    backup_management, create_backup, download_backup, restore_backup,
    restore_backup_from_upload,
    list_backups, delete_backup, get_backup_settings, update_backup_settings,
    cleanup_old_backups
)
from .views.module_management import module_management

app_name = "core"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    
    # ✅ Security endpoints - نقاط الأمان (معطلة مؤقتاً)
    # path("api/csp-report/", security_views.csp_report_handler, name="csp_report"),
    # path("api/security-log/", security_views.SecurityLogView.as_view(), name="security_log"),
    # path("api/security-dashboard/", security_views.security_dashboard, name="security_dashboard"),
    # path("api/security-report/", security_views.security_report, name="security_report"),
    # path("api/security-incident/", security_views.security_incident_report, name="security_incident"),
    
    # مسارات الإعدادات
    path("settings/company/", company_settings, name="company_settings"),
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
    path("settings/whatsapp/", whatsapp_settings, name="whatsapp_settings"),
    path("webhooks/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),
    
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
    path('api/system-info/', api.get_system_info, name='get_system_info'),
    path('api/upload-company-logo/', api.upload_company_logo, name='upload_company_logo'),
]
