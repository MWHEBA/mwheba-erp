# -*- coding: utf-8 -*-
"""
Management Command to Initialize Site Progress Inspection Stages for Real Estate Projects
MWHEBA ERP — Track 3
Usage:
    python manage.py init_site_stages [--project-code CODE] [--all]
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _

from real_estate.models import RealEstateProject
from real_estate.services.site_progress_service import SiteProgressInitializationService


class Command(BaseCommand):
    help = _('تهيئة وتوليد مراحل المتابعة الميدانية للوحدات العقارية (Track 3 Site Stages Seeder)')

    def add_arguments(self, parser):
        parser.add_argument(
            '--project-code',
            type=str,
            help=_('كود المشروع المستهدف لتهيئة وحداته'),
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help=_('تهيئة كافة مشاريع المنظومة العقارية النشطة'),
        )

    def handle(self, *args, **options):
        project_code = options.get('project_code')
        run_all = options.get('all')

        if not project_code and not run_all:
            raise CommandError(_('يرجى تحديد إما --project-code كود المشروع أو --all لكافة المشاريع.'))

        if project_code:
            projects = RealEstateProject.objects.filter(code=project_code)
            if not projects.exists():
                raise CommandError(_('المشروع ذو الكود "%(code)s" غير موجود.') % {'code': project_code})
        else:
            projects = RealEstateProject.objects.filter(is_archived=False)

        self.stdout.write(self.style.SUCCESS(_('بدء تهيئة مراحل المتابعة الميدانية...')))

        total_units_seeded = 0
        total_records_created = 0

        for proj in projects:
            self.stdout.write(_('معالجة المشروع: %(name)s (%(code)s)...') % {'name': proj.name, 'code': proj.code})
            units_count, records_created = SiteProgressInitializationService.seed_project_units(proj)
            total_units_seeded += units_count
            total_records_created += records_created
            self.stdout.write(self.style.SUCCESS(
                _('  -> تم فحص %(units)s وحدة، وإنشاء %(records)s سجل بنود تنفيذ.') % {
                    'units': units_count,
                    'records': records_created
                }
            ))

        self.stdout.write(self.style.SUCCESS(
            _('اكتملت العملية بنجاح! إجمالي الوحدات: %(units)s، إجمالي السجلات المنشأة: %(records)s.') % {
                'units': total_units_seeded,
                'records': total_records_created
            }
        ))
