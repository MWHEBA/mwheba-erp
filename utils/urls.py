from django.urls import path
from . import views

app_name = 'utils'

urlpatterns = [
    # المسارات الحالية
    path('inventory-check/', views.inventory_check, name='inventory_check'),
    path('system-help/', views.system_help, name='system_help'),
    path('backup/', views.backup_system, name='backup_system'),
    path('restore/', views.restore_database, name='restore_database'),
    
    # سجلات النظام
    path('system-logs/', views.SystemLogView.as_view(), name='system_logs'),
] 