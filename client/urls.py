from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    path('', views.customer_list, name='customer_list'),
    path('add/', views.customer_add, name='customer_add'),
    path('<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('<int:pk>/detail/', views.customer_detail, name='customer_detail'),
    path('<int:pk>/change-account/', views.customer_change_account, name='customer_change_account'),
] 