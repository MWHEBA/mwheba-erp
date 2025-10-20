"""
أمر Django لنقل البيانات من جداول النظام القديم إلى الجديد داخل نفس قاعدة البيانات
Usage: python manage.py migrate_internal_pricing_data
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.utils import timezone
from printing_pricing.models.settings_models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    PrintDirection, PrintSide, CoatingType, FinishingType,
    ProductType, ProductSize, PieceSize,
    OffsetMachineType, OffsetSheetSize,
    DigitalMachineType, DigitalSheetSize,
    PlateSize
)
from decimal import Decimal


class Command(BaseCommand):
    help = 'نقل البيانات من جداول النظام القديم إلى الجديد'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تشغيل تجريبي بدون حفظ البيانات'
        )
        parser.add_argument(
            '--clear-new',
            action='store_true',
            help='مسح البيانات من الجداول الجديدة قبل النقل'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clear_new = options['clear_new']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('تشغيل تجريبي - لن يتم حفظ البيانات')
            )

        self.stdout.write('بدء نقل البيانات من النظام القديم إلى الجديد...')

        try:
            with transaction.atomic():
                if clear_new and not dry_run:
                    self._clear_new_tables()

                # نقل البيانات
                self._migrate_paper_types(dry_run)
                self._migrate_paper_sizes(dry_run)
                self._migrate_paper_weights(dry_run)
                self._migrate_paper_origins(dry_run)
                self._migrate_print_directions(dry_run)
                self._migrate_print_sides(dry_run)
                self._migrate_coating_types(dry_run)
                self._migrate_finishing_types(dry_run)
                self._migrate_product_types(dry_run)
                self._migrate_product_sizes(dry_run)
                self._migrate_piece_sizes(dry_run)
                self._migrate_offset_machine_types(dry_run)
                self._migrate_offset_sheet_sizes(dry_run)
                self._migrate_digital_machine_types(dry_run)
                self._migrate_digital_sheet_sizes(dry_run)
                self._migrate_plate_sizes(dry_run)

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS('انتهى التشغيل التجريبي بنجاح')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('تم نقل البيانات بنجاح!')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'خطأ أثناء نقل البيانات: {str(e)}')
            )

    def _clear_new_tables(self):
        """مسح البيانات من الجداول الجديدة"""
        models_to_clear = [
            PlateSize, DigitalSheetSize, DigitalMachineType,
            OffsetSheetSize, OffsetMachineType, PieceSize, ProductSize,
            ProductType, FinishingType, CoatingType, PrintSide,
            PrintDirection, PaperOrigin, PaperWeight, PaperSize, PaperType
        ]

        for model in models_to_clear:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(f'تم مسح {count} عنصر من {model._meta.verbose_name_plural}')

    def _execute_query(self, query):
        """تنفيذ استعلام SQL والحصول على النتائج"""
        with connection.cursor() as cursor:
            try:
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'خطأ في الاستعلام: {query} - {str(e)}')
                )
                return []

    def _migrate_paper_types(self, dry_run):
        """نقل أنواع الورق"""
        old_data = self._execute_query("SELECT * FROM pricing_papertype")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                # التحقق من وجود السجل
                existing = self._execute_query(
                    f"SELECT id FROM printing_pricing_papertype WHERE name = '{row['name']}'"
                )
                
                if not existing:
                    # إدراج السجل مباشرة بـ SQL
                    now = timezone.now().isoformat()
                    insert_query = f"""
                    INSERT INTO printing_pricing_papertype 
                    (name, description, is_active, is_default, created_at, updated_at, notes)
                    VALUES (
                        '{row['name']}',
                        '{row.get('description', '')}',
                        {1 if row.get('is_active', True) else 0},
                        {1 if row.get('is_default', False) else 0},
                        '{now}',
                        '{now}',
                        ''
                    )
                    """
                    with connection.cursor() as cursor:
                        cursor.execute(insert_query)
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أنواع الورق: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_paper_sizes(self, dry_run):
        """نقل مقاسات الورق"""
        old_data = self._execute_query("SELECT * FROM pricing_papersize")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = PaperSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مقاسات الورق: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_paper_weights(self, dry_run):
        """نقل أوزان الورق"""
        old_data = self._execute_query("SELECT * FROM pricing_paperweight")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = PaperWeight.objects.get_or_create(
                    gsm=int(row.get('gsm', 80)),
                    defaults={
                        'name': row['name'],
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أوزان الورق: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_paper_origins(self, dry_run):
        """نقل مناشئ الورق"""
        old_data = self._execute_query("SELECT * FROM pricing_paper_origin")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                code = row.get('code', row['name'][:3].upper())
                obj, created = PaperOrigin.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': row['name'],
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مناشئ الورق: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_print_directions(self, dry_run):
        """نقل اتجاهات الطباعة"""
        old_data = self._execute_query("SELECT * FROM pricing_printdirection")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = PrintDirection.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'اتجاهات الطباعة: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_print_sides(self, dry_run):
        """نقل جوانب الطباعة"""
        old_data = self._execute_query("SELECT * FROM pricing_printside")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = PrintSide.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'جوانب الطباعة: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_coating_types(self, dry_run):
        """نقل أنواع التغطية"""
        old_data = self._execute_query("SELECT * FROM pricing_coatingtype")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = CoatingType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أنواع التغطية: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_finishing_types(self, dry_run):
        """نقل أنواع التشطيب"""
        old_data = self._execute_query("SELECT * FROM pricing_finishingtype")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = FinishingType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أنواع التشطيب: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_product_types(self, dry_run):
        """نقل أنواع المنتجات"""
        old_data = self._execute_query("SELECT * FROM pricing_product_type")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = ProductType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أنواع المنتجات: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_product_sizes(self, dry_run):
        """نقل مقاسات المنتجات"""
        old_data = self._execute_query("SELECT * FROM pricing_product_size")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = ProductSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مقاسات المنتجات: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_piece_sizes(self, dry_run):
        """نقل مقاسات القطع"""
        old_data = self._execute_query("SELECT * FROM pricing_piecesize")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                # البحث عن نوع الورق المرتبط
                paper_type = None
                if row.get('paper_type_id'):
                    try:
                        paper_type = PaperType.objects.get(id=row['paper_type_id'])
                    except PaperType.DoesNotExist:
                        pass

                obj, created = PieceSize.objects.get_or_create(
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
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مقاسات القطع: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_offset_machine_types(self, dry_run):
        """نقل أنواع ماكينات الأوفست"""
        old_data = self._execute_query("SELECT * FROM pricing_offsetmachinetype")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = OffsetMachineType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'code': row.get('code', ''),
                        'manufacturer': row.get('manufacturer', ''),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أنواع ماكينات الأوفست: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_offset_sheet_sizes(self, dry_run):
        """نقل مقاسات ماكينات الأوفست"""
        old_data = self._execute_query("SELECT * FROM pricing_offsetsheetsize")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = OffsetSheetSize.objects.get_or_create(
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
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مقاسات ماكينات الأوفست: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_digital_machine_types(self, dry_run):
        """نقل أنواع ماكينات الديجيتال"""
        old_data = self._execute_query("SELECT * FROM pricing_digitalmachinetype")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = DigitalMachineType.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'code': row.get('code', ''),
                        'manufacturer': row.get('manufacturer', ''),
                        'description': row.get('description', ''),
                        'is_active': bool(row.get('is_active', True)),
                        'is_default': bool(row.get('is_default', False))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'أنواع ماكينات الديجيتال: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_digital_sheet_sizes(self, dry_run):
        """نقل مقاسات ماكينات الديجيتال"""
        old_data = self._execute_query("SELECT * FROM pricing_digitalsheetsize")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = DigitalSheetSize.objects.get_or_create(
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
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مقاسات ماكينات الديجيتال: تم نقل {migrated_count} من {len(old_data)} عنصر')

    def _migrate_plate_sizes(self, dry_run):
        """نقل مقاسات الزنكات"""
        old_data = self._execute_query("SELECT * FROM pricing_platesize")
        
        migrated_count = 0
        for row in old_data:
            if not dry_run:
                obj, created = PlateSize.objects.get_or_create(
                    name=row['name'],
                    defaults={
                        'width': Decimal(str(row.get('width', 0))),
                        'height': Decimal(str(row.get('height', 0))),
                        'is_active': bool(row.get('is_active', True))
                    }
                )
                if created:
                    migrated_count += 1
            else:
                migrated_count += 1
        
        self.stdout.write(f'مقاسات الزنكات: تم نقل {migrated_count} من {len(old_data)} عنصر')
