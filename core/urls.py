from django.urls import path
from . import views, api, views_logs

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # مسارات الإعدادات
    path("settings/company/", views.company_settings, name="company_settings"),
    path("settings/system/", views.system_settings, name="system_settings"),
    path("system/reset/", views.system_reset, name="system_reset"),
    # مسارات الأخطاء والـ Logs (للـ Admin فقط)
    path("logs/errors/", views_logs.view_error_logs, name="view_error_logs"),
    path("logs/errors/clear/", views_logs.clear_error_logs, name="clear_error_logs"),
    # صفحة عرض كل الإشعارات
    path("notifications/", views.notifications_list, name="notifications_list"),
    path("notifications/settings/", views.notification_settings, name="notification_settings"),
    
    # مسارات API الإشعارات - مفعلة ✅
    path('api/notifications/mark-read/<int:notification_id>/', api.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/mark-unread/<int:notification_id>/', api.mark_notification_unread, name='mark_notification_unread'),
    path('api/notifications/mark-all-read/', api.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('api/notifications/count/', api.get_notifications_count, name='notifications_count'),
    
    # مسارات API الأساسية
    path('api/dashboard-stats/', api.DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
    path('api/system-health/', api.SystemHealthAPIView.as_view(), name='api_system_health'),
    path('api/dashboard/stats/', api.get_dashboard_stats, name='dashboard_stats'),
    path('api/dashboard/activity/', api.get_recent_activity, name='recent_activity'),
    path('api/test-email/', api.test_email_settings, name='test_email_settings'),
    path('api/system-info/', api.get_system_info, name='get_system_info'),
    path('api/upload-company-logo/', api.upload_company_logo, name='upload_company_logo'),
]
