from django.urls import path
from . import views
from . import daftra_views

app_name = "utils"

urlpatterns = [
    # المسارات الحالية
    path("inventory-check/", views.inventory_check, name="inventory_check"),
    path("system-help/", views.system_help, name="system_help"),
    path("backup/", views.backup_system, name="backup_system"),
    path("restore/", views.restore_database, name="restore_database"),
    # سجلات النظام
    path("system-logs/", views.SystemLogView.as_view(), name="system_logs"),
    
    # Daftra Sync
    path("daftra/sync-clients/", daftra_views.sync_clients, name="daftra_sync_clients"),
    path("daftra/sync-suppliers/", daftra_views.sync_suppliers, name="daftra_sync_suppliers"),
]
