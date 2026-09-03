"""
أمر إدارة مركزي لتثبيت وبذر كافة جداول وإعدادات ومصفوفة تسعير المطبوعات
Management command to seed printing pricing lookup data and supplier environment
"""
from django.core.management.base import BaseCommand
from printing_pricing.services.pricing_lookup_seeder_service import PricingLookupSeederService
from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService


class Command(BaseCommand):
    help = "بذر وتثبيت كافة بيانات وإعدادات تسعير المطبوعات وبيئة الموردين ذات الصلة"

    def add_arguments(self, parser):
        parser.add_argument(
            '--lookups-only',
            action='store_true',
            help='بذر جداول التسعير فقط دون بيئة الموردين',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> بدء بذر وتحديث جداول وإعدادات تسعير المطبوعات..."))
        
        # 1. بذر جداول التسعير المركزية
        lookup_result = PricingLookupSeederService.seed_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] تم الانتهاء من جداول التسعير: {lookup_result['summary']}"
            )
        )

        # 2. بذر بيئة الموردين المتخصصة بالطباعة إن لم يتم استثناؤها
        if not options.get('lookups_only'):
            self.stdout.write(self.style.NOTICE(">> بدء بذر ومزامنة بيئة الموردين المرتبطة بالتسعير..."))
            supplier_result = PricingSupplierSeederService.seed_all()
            supp_count = supplier_result["supplier_types_created"]
            serv_count = supplier_result["service_types_created"]
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] تم بذر بيئة الموردين: {supp_count} أنواع موردين جديدة، {serv_count} خدمات تسعير."
                )
            )

        self.stdout.write(self.style.SUCCESS("[DONE] اكتملت تهيئة موديول تسعير الطباعة بنجاح بنسبة 100%!"))
