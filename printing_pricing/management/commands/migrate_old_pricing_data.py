"""
أمر Django لنقل البيانات من النظام القديم للتسعير إلى النظام الجديد
Usage: python manage.py migrate_old_pricing_data --old-db-path path/to/old/database
"""

import os
import sqlite3
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from printing_pricing.models.settings_models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    PrintDirection, PrintSide, CoatingType, FinishingType,
    ProductType, ProductSize, PieceSize,
    OffsetMachineType, OffsetSheetSize,
    DigitalMachineType, DigitalSheetSize,
    PlateSize, SystemSetting
)


class Command(BaseCommand):
    help = 'نقل البيانات من النظام القديم للتسعير إلى النظام الجديد'

    def add_arguments(self, parser):
        parser.add_argument(
            '--old-db-path',
            type=str,
            help='مسار قاعدة البيانات القديمة',
            required=True
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تشغيل تجريبي بدون حفظ البيانات'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='مسح البيانات الموجودة قبل النقل'
        )

    def handle(self, *args, **options):
        old_db_path = options['old_db_path']
        dry_run = options['dry_run']
        clear_existing = options['clear_existing']

        # التحقق من وجود قاعدة البيانات القديمة
        if not os.path.exists(old_db_path):
            raise CommandError(f'قاعدة البيانات القديمة غير موجودة: {old_db_path}')

        self.stdout.write(
            self.style.SUCCESS(f'بدء نقل البيانات من: {old_db_path}')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('تشغيل تجريبي - لن يتم حفظ البيانات')
            )

        try:
            # الاتصال بقاعدة البيانات القديمة
            old_conn = sqlite3.connect(old_db_path)
            old_conn.row_factory = sqlite3.Row  # للوصول للأعمدة بالاسم

            with transaction.atomic():
                if clear_existing and not dry_run:
                    self._clear_existing_data()

                # نقل البيانات حسب الأولوية
                self._migrate_paper_types(old_conn, dry_run)
                self._migrate_paper_sizes(old_conn, dry_run)
                self._migrate_paper_weights(old_conn, dry_run)
                self._migrate_paper_origins(old_conn, dry_run)
                self._migrate_print_directions(old_conn, dry_run)
                self._migrate_print_sides(old_conn, dry_run)
                self._migrate_coating_types(old_conn, dry_run)
                self._migrate_finishing_types(old_conn, dry_run)
                self._migrate_product_types(old_conn, dry_run)
                self._migrate_product_sizes(old_conn, dry_run)
                self._migrate_piece_sizes(old_conn, dry_run)
                self._migrate_offset_machine_types(old_conn, dry_run)
                self._migrate_offset_sheet_sizes(old_conn, dry_run)
                self._migrate_digital_machine_types(old_conn, dry_run)
                self._migrate_digital_sheet_sizes(old_conn, dry_run)
                self._migrate_plate_sizes(old_conn, dry_run)
                self._migrate_system_settings(old_conn, dry_run)

            old_conn.close()

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS('انتهى التشغيل التجريبي بنجاح')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('تم نقل البيانات بنجاح!')
                )

        except Exception as e:
            raise CommandError(f'خطأ أثناء نقل البيانات: {str(e)}')

    def _clear_existing_data(self):
        """مسح البيانات الموجودة"""
        models_to_clear = [
            SystemSetting, PlateSize, DigitalSheetSize, DigitalMachineType,
            OffsetSheetSize, OffsetMachineType, PieceSize, ProductSize,
            ProductType, FinishingType, CoatingType, PrintSide,
            PrintDirection, PaperOrigin, PaperWeight, PaperSize, PaperType
        ]

        for model in models_to_clear:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(f'تم مسح {count} عنصر من {model._meta.verbose_name_plural}')

    def _get_table_data(self, conn, table_name):
        """الحصول على البيانات من جدول في قاعدة البيانات القديمة"""
        try:
            cursor = conn.execute(f"SELECT * FROM {table_name}")
            return cursor.fetchall()
        except sqlite3.OperationalError:
            self.stdout.write(
                self.style.WARNING(f'الجدول {table_name} غير موجود في قاعدة البيانات القديمة')
            )
            return []

    def _migrate_paper_types(self, old_conn, dry_run):
        """نقل أنواع الورق"""
        old_data = self._get_table_data(old_conn, 'paper_types')
        
        for row in old_data:
            if not dry_run:
                PaperType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} نوع ورق')

    def _migrate_paper_sizes(self, old_conn, dry_run):
        """نقل مقاسات الورق"""
        old_data = self._get_table_data(old_conn, 'paper_sizes')
        
        for row in old_data:
            if not dry_run:
                PaperSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} مقاس ورق')

    def _migrate_paper_weights(self, old_conn, dry_run):
        """نقل أوزان الورق"""
        old_data = self._get_table_data(old_conn, 'paper_weights')
        
        for row in old_data:
            if not dry_run:
                PaperWeight.objects.get_or_create(
                    gsm=int(row.get('gsm', 80)),
                    defaults={
                        'name': row['name'],
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} وزن ورق')

    def _migrate_paper_origins(self, old_conn, dry_run):
        """نقل مناشئ الورق"""
        old_data = self._get_table_data(old_conn, 'paper_origins')
        
        for row in old_data:
            if not dry_run:
                PaperOrigin.objects.get_or_create(
                    code=row.get('code', row['name'][:3].upper()),
                    defaults={
                        'name': row['name'],
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} منشأ ورق')

    def _migrate_print_directions(self, old_conn, dry_run):
        """نقل اتجاهات الطباعة"""
        old_data = self._get_table_data(old_conn, 'print_directions')
        
        for row in old_data:
            if not dry_run:
                PrintDirection.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} اتجاه طباعة')

    def _migrate_print_sides(self, old_conn, dry_run):
        """نقل جوانب الطباعة"""
        old_data = self._get_table_data(old_conn, 'print_sides')
        
        for row in old_data:
            if not dry_run:
                PrintSide.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} جانب طباعة')

    def _migrate_coating_types(self, old_conn, dry_run):
        """نقل أنواع التغطية"""
        old_data = self._get_table_data(old_conn, 'coating_types')
        
        for row in old_data:
            if not dry_run:
                CoatingType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} نوع تغطية')

    def _migrate_finishing_types(self, old_conn, dry_run):
        """نقل أنواع خدمات الطباعة"""
        old_data = self._get_table_data(old_conn, 'finishing_types')
        
        for row in old_data:
            if not dry_run:
                FinishingType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} نوع تشطيب')

    def _migrate_product_types(self, old_conn, dry_run):
        """نقل أنواع المنتجات"""
        old_data = self._get_table_data(old_conn, 'product_types')
        
        for row in old_data:
            if not dry_run:
                ProductType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} نوع منتج')

    def _migrate_product_sizes(self, old_conn, dry_run):
        """نقل مقاسات المنتجات"""
        old_data = self._get_table_data(old_conn, 'product_sizes')
        
        for row in old_data:
            if not dry_run:
                ProductSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} مقاس منتج')

    def _migrate_piece_sizes(self, old_conn, dry_run):
        """نقل مقاسات القطع"""
        old_data = self._get_table_data(old_conn, 'piece_sizes')
        
        for row in old_data:
            if not dry_run:
                # البحث عن نوع الورق المرتبط
                paper_type = None
                if row.get('paper_type_id'):
                    try:
                        paper_type = PaperType.objects.get(id=row['paper_type_id'])
                    except PaperType.DoesNotExist:
                        pass

                PieceSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'paper_type': paper_type,
                        'pieces_per_sheet': int(row.get('pieces_per_sheet', 1)),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} مقاس قطعة')

    def _migrate_offset_machine_types(self, old_conn, dry_run):
        """نقل أنواع ماكينات الأوفست"""
        old_data = self._get_table_data(old_conn, 'offset_machine_types')
        
        for row in old_data:
            if not dry_run:
                OffsetMachineType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'code': row.get('code', ''),
                        'manufacturer': row.get('manufacturer', ''),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} نوع ماكينة أوفست')

    def _migrate_offset_sheet_sizes(self, old_conn, dry_run):
        """نقل مقاسات ماكينات الأوفست"""
        old_data = self._get_table_data(old_conn, 'offset_sheet_sizes')
        
        for row in old_data:
            if not dry_run:
                OffsetSheetSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'code': row.get('code', ''),
                        'width_cm': Decimal(str(row.get('width_cm', 0))),
                        'height_cm': Decimal(str(row.get('height_cm', 0))),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False)),
                        'is_custom_size': bool(row.get('is_custom_size', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} مقاس ماكينة أوفست')

    def _migrate_digital_machine_types(self, old_conn, dry_run):
        """نقل أنواع ماكينات الديجيتال"""
        old_data = self._get_table_data(old_conn, 'digital_machine_types')
        
        for row in old_data:
            if not dry_run:
                DigitalMachineType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'code': row.get('code', ''),
                        'manufacturer': row.get('manufacturer', ''),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} نوع ماكينة ديجيتال')

    def _migrate_digital_sheet_sizes(self, old_conn, dry_run):
        """نقل مقاسات ماكينات الديجيتال"""
        old_data = self._get_table_data(old_conn, 'digital_sheet_sizes')
        
        for row in old_data:
            if not dry_run:
                DigitalSheetSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'code': row.get('code', ''),
                        'width_cm': Decimal(str(row.get('width_cm', 0))),
                        'height_cm': Decimal(str(row.get('height_cm', 0))),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False)),
                        'is_custom_size': bool(row.get('is_custom_size', False))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} مقاس ماكينة ديجيتال')

    def _migrate_plate_sizes(self, old_conn, dry_run):
        """نقل مقاسات الزنكات"""
        old_data = self._get_table_data(old_conn, 'plate_sizes')
        
        for row in old_data:
            if not dry_run:
                PlateSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'is_active': bool(row.get('is_active', True))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} مقاس زنك')

    def _migrate_system_settings(self, old_conn, dry_run):
        """نقل إعدادات النظام"""
        old_data = self._get_table_data(old_conn, 'system_settings')
        
        for row in old_data:
            if not dry_run:
                SystemSetting.objects.get_or_create(
                    key=row['key'],
                    defaults={
                        'value': row.get('value', ''),
                        'description': row.get('description', ''),
                        'category': row.get('category', 'عام'),
                        'is_active': bool(row.get('is_active', True))
                    }
                )
        
        self.stdout.write(f'تم نقل {len(old_data)} إعداد نظام')
