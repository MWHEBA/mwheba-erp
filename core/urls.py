from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # مسارات الإعدادات
    path("settings/company/", views.company_settings, name="company_settings"),
    path("settings/system/", views.system_settings, name="system_settings"),
    # صفحة عرض كل الإشعارات
    path("notifications/", views.notifications_list, name="notifications_list"),
    # إعادة تهيئة النظام
    path("reset-system-progress/", views.reset_system_with_progress, name="reset_system_with_progress"),
    path("reset-progress/<str:operation_id>/", views.get_reset_progress, name="get_reset_progress"),
    # مسارات API الأساسية - معلقة مؤقتاً
    # path('api/dashboard-stats/', api.DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
    # path('api/system-health/', api.SystemHealthAPIView.as_view(), name='api_system_health'),
    # مسارات API الإشعارات - معلقة مؤقتاً
    # path('api/notifications/mark-read/<int:notification_id>/', api.mark_notification_read, name='mark_notification_read'),
    # path('api/notifications/mark-all-read/', api.mark_all_notifications_read, name='mark_all_notifications_read'),
    # path('api/notifications/count/', api.get_notifications_count, name='notifications_count'),
    # path('api/dashboard/stats/', api.get_dashboard_stats, name='dashboard_stats'),
    # path('api/dashboard/activity/', api.get_recent_activity, name='recent_activity'),
    # صفحة عرض كل الإشعارات - معلقة مؤقتاً
    # path('notifications/', views.notifications_list, name='notifications_list'),
]
