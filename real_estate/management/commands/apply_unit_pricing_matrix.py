# -*- coding: utf-8 -*-
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock
from real_estate.services.pricing_service import BulkPricingGeneratorService


class Command(BaseCommand):
    help = 'تطبيق مصفوفة التسعير الآلي على وحدات مشروع أو عمارة عقارية (Wave 2 Phase 4)'

    def add_arguments(self, parser):
        parser.add_argument('--project-code', type=str, required=True, help='كود المشروع العقاري')
        parser.add_argument('--block-code', type=str, default=None, help='كود العمارة/المبنى (اختياري)')
        parser.add_argument('--dry-run', action='store_true', help='تشغيل تجريبي للمعاينة دون حفظ التعديلات في قاعدة البيانات')

    def handle(self, *args, **options):
        project_code = options['project_code']
        block_code = options['block_code']
        dry_run = options['dry_run']

        project = RealEstateProject.objects.filter(code=project_code).first()
        if not project:
            raise CommandError(f"المشروع بكود '{project_code}' غير موجود.")

        block = None
        if block_code:
            block = PropertyBlock.objects.filter(project=project, code=block_code).first()
            if not block:
                raise CommandError(f"العمارة بكود '{block_code}' غير موجودة بالمشروع '{project_code}'.")

        self.stdout.write(self.style.NOTICE(
            f"بدء تطبيق مصفوفة التسعير للمشروع: {project.name} {'(تشغيل تجريبي)' if dry_run else ''}..."
        ))

        try:
            report = BulkPricingGeneratorService.bulk_generate_pricing(
                project=project,
                block=block,
                dry_run=dry_run
            )

            self.stdout.write(self.style.SUCCESS(
                f"تمت العملية بنجاح! لائحة التسعير: {report['config_name']}\n"
                f"إجمالي الوحدات المفحوصة: {report['total_units_evaluated']}\n"
                f"إجمالي الوحدات المحدثة: {report['total_units_updated']}\n"
                f"الوحدات المباعة المستبعدة: {report['skipped_contracted_units']}\n"
                f"القيمة الإجمالية للمحفظة قبل: {report['total_portfolio_value_before']:,.2f} ج.م\n"
                f"القيمة الإجمالية للمحفظة بعد: {report['total_portfolio_value_after']:,.2f} ج.م\n"
                f"فارق القيمة السوقية: {report['portfolio_value_difference']:,.2f} ج.م"
            ))
        except Exception as e:
            raise CommandError(f"حدث خطأ أثناء تطبيق مصفوفة التسعير: {str(e)}")
