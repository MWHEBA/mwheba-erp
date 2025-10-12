from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    # الصفحة الرئيسية للخدمات
    path("", views.services_home, name="services_home"),
    # تفاصيل نوع خدمة معين
    path("<slug:slug>/", views.category_detail, name="category_detail"),
]
