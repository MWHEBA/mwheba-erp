"""
أمر Django مبسط لنقل البيانات من جداول النظام القديم إلى الجديد
Usage: python manage.py migrate_pricing_simple
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = 'نقل البيانات من جداول النظام القديم إلى الجديد (مبسط)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تشغيل تجريبي بدون حفظ البيانات'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('تشغيل تجريبي - لن يتم حفظ البيانات')
            )

        self.stdout.write('بدء نقل البيانات من النظام القديم إلى الجديد...')

        try:
            # قائمة الجداول للنقل
            migrations = [
                {
                    'name': 'أنواع الورق',
                    'old_table': 'pricing_papertype',
                    'new_table': 'printing_pricing_papertype',
                    'columns': ['name', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'مقاسات الورق',
                    'old_table': 'pricing_papersize',
                    'new_table': 'printing_pricing_papersize',
                    'columns': ['name', 'width', 'height', 'is_active', 'is_default']
                },
                {
                    'name': 'أوزان الورق',
                    'old_table': 'pricing_paperweight',
                    'new_table': 'printing_pricing_paperweight',
                    'columns': ['name', 'gsm', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'مناشئ الورق',
                    'old_table': 'pricing_paper_origin',
                    'new_table': 'printing_pricing_paperorigin',
                    'columns': ['name', 'code', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'اتجاهات الطباعة',
                    'old_table': 'pricing_printdirection',
                    'new_table': 'printing_pricing_printdirection',
                    'columns': ['name', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'جوانب الطباعة',
                    'old_table': 'pricing_printside',
                    'new_table': 'printing_pricing_printside',
                    'columns': ['name', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'أنواع التغطية',
                    'old_table': 'pricing_coatingtype',
                    'new_table': 'printing_pricing_coatingtype',
                    'columns': ['name', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'أنواع خدمات الطباعة',
                    'old_table': 'pricing_finishingtype',
                    'new_table': 'printing_pricing_finishingtype',
                    'columns': ['name', 'description', 'is_active']
                },
                {
                    'name': 'أنواع المنتجات',
                    'old_table': 'pricing_product_type',
                    'new_table': 'printing_pricing_producttype',
                    'columns': ['name', 'description', 'is_active', 'is_default']
                },
                {
                    'name': 'مقاسات المنتجات',
                    'old_table': 'pricing_product_size',
                    'new_table': 'printing_pricing_productsize',
                    'columns': ['name', 'width', 'height', 'description', 'is_active', 'is_default']
                }
            ]

            for migration in migrations:
                self._migrate_table(migration, dry_run)

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
                self.style.ERROR('خطأ أثناء نقل البيانات: {}'.format(str(e)))
            )

    def _migrate_table(self, migration, dry_run):
        """نقل بيانات جدول محدد"""
        old_table = migration['old_table']
        new_table = migration['new_table']
        columns = migration['columns']
        name = migration['name']

        with connection.cursor() as cursor:
            # التحقق من وجود الجدول القديم
            try:
                cursor.execute("SELECT COUNT(*) FROM {}".format(old_table))
                old_count = cursor.fetchone()[0]
            except:
                self.stdout.write('{}: الجدول القديم {} غير موجود'.format(name, old_table))
                return

            if old_count == 0:
                self.stdout.write('{}: لا توجد بيانات في الجدول القديم'.format(name))
                return

            # الحصول على البيانات من الجدول القديم
            cursor.execute("SELECT * FROM {}".format(old_table))
            old_data = cursor.fetchall()
            
            # الحصول على أسماء الأعمدة
            cursor.execute("PRAGMA table_info({})".format(old_table))
            old_columns_info = cursor.fetchall()
            old_column_names = [col[1] for col in old_columns_info]

            migrated_count = 0
            
            for row in old_data:
                # تحويل البيانات إلى dictionary
                row_dict = dict(zip(old_column_names, row))
                
                if not dry_run:
                    # التحقق من وجود السجل في الجدول الجديد
                    check_query = "SELECT COUNT(*) FROM {} WHERE name = ?".format(new_table)
                    cursor.execute(check_query, [row_dict['name']])
                    exists = cursor.fetchone()[0] > 0
                    
                    if not exists:
                        # إعداد البيانات للإدراج
                        now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        # بناء استعلام الإدراج
                        insert_columns = []
                        insert_values = []
                        
                        # إضافة الأعمدة الموجودة في كلا الجدولين
                        for col in columns:
                            if col in row_dict:
                                insert_columns.append(col)
                                value = row_dict[col]
                                # معالجة القيم الفارغة
                                if value is None:
                                    if col in ['description']:
                                        value = ''
                                    elif col in ['is_active', 'is_default']:
                                        value = True if col == 'is_active' else False
                                insert_values.append(value)
                        
                        # إضافة الأعمدة المطلوبة
                        insert_columns.extend(['created_at', 'updated_at', 'notes'])
                        insert_values.extend([now, now, ''])
                        
                        # تنفيذ الإدراج
                        placeholders = ', '.join(['?' for _ in insert_values])
                        columns_str = ', '.join(insert_columns)
                        
                        insert_query = "INSERT INTO {} ({}) VALUES ({})".format(new_table, columns_str, placeholders)
                        
                        try:
                            cursor.execute(insert_query, insert_values)
                            migrated_count += 1
                        except Exception as e:
                            self.stdout.write('خطأ في إدراج {}: {}'.format(row_dict.get("name", ""), str(e)))
                else:
                    migrated_count += 1

            self.stdout.write('{}: تم نقل {} من {} عنصر'.format(name, migrated_count, len(old_data)))
