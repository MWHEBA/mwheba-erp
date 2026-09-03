"""
أمر إدارة يدوي لتثبيت أنواع الموردين وخدمات التسعير لموديول الطباعة
Management command to seed printing supplier types and service types
"""
from django.core.management.base import BaseCommand
from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService


class Command(BaseCommand):
    help = "تثبيت ومزامنة أنواع الموردين المتخصصة بالطباعة وأنواع خدمات التسعير"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("بدء تثبيت بيئة الموردين لموديول تسعير الطباعة..."))
        
        result = PricingSupplierSeederService.seed_all()
        
        supp_count = result["supplier_types_created"]
        serv_count = result["service_types_created"]
        
        self.stdout.write(
            self.style.SUCCESS(
                f"تم الانتهاء بنجاح! تم إنشاء {supp_count} نوع مورد جديد، و {serv_count} نوع خدمة جديد."
            )
        )
