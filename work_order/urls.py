from django.urls import path
from . import views

app_name = "work_order"

urlpatterns = [
    path("", views.work_order_list, name="work_order_list"),
    path("create/", views.work_order_create, name="work_order_create"),
    path("<int:pk>/", views.work_order_detail, name="work_order_detail"),
    path("<int:pk>/edit/", views.work_order_edit, name="work_order_edit"),
    path("<int:pk>/delete/", views.work_order_delete, name="work_order_delete"),
    path("<int:pk>/record-deposit/", views.work_order_record_deposit, name="work_order_record_deposit"),
]
