"""
أمر Django لاستيراد البيانات من ملف JSON
Usage: python manage.py import_pricing_data --input-file backup.json
"""

import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.apps import apps
from printing_pricing.models.settings_models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    PrintDirection, PrintSide, CoatingType, FinishingType,
    ProductType, ProductSize, PieceSize,
    OffsetMachineType, OffsetSheetSize,
    DigitalMachineType, DigitalSheetSize,
    PlateSize, SystemSetting
)


class Command(BaseCommand):
    help = 'استيراد البيانات من ملف JSON'

    def add_arguments(self, parser):
        parser.add_argument(
            '--input-file',
            type=str,
            help='مسار ملف البيانات المراد استيراده',
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
            help='مسح البيانات الموجودة قبل الاستيراد'
        )

    def handle(self, *args, **options):
        input_file = options['input_file']
        dry_run = options['dry_run']
        clear_existing = options['clear_existing']

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'الملف غير موجود: {input_file}')
        except json.JSONDecodeError as e:
            raise CommandError(f'خطأ في تنسيق JSON: {str(e)}')

        self.stdout.write(f'بدء استيراد البيانات من: {input_file}')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('تشغيل تجريبي - لن يتم حفظ البيانات')
            )

        # التحقق من بنية البيانات
        if 'data' not in data:
            raise CommandError('بنية البيانات غير صحيحة - مفتاح "data" مفقود')

        # عرض معلومات النسخة الاحتياطية
        if 'metadata' in data:
            metadata = data['metadata']
            self.stdout.write(f"تاريخ التصدير: {metadata.get('export_date', 'غير محدد')}")
            self.stdout.write(f"إجمالي السجلات: {metadata.get('total_records', 'غير محدد')}")

        # خريطة النماذج
        model_map = {
            'papertype': PaperType,
            'papersize': PaperSize,
            'paperweight': PaperWeight,
            'paperorigin': PaperOrigin,
            'printdirection': PrintDirection,
            'printside': PrintSide,
            'coatingtype': CoatingType,
            'finishingtype': FinishingType,
            'producttype': ProductType,
            'productsize': ProductSize,
            'piecesize': PieceSize,
            'offsetmachinetype': OffsetMachineType,
            'offsetsheetsize': OffsetSheetSize,
            'digitalmachinetype': DigitalMachineType,
            'digitalsheetsize': DigitalSheetSize,
            'platesize': PlateSize,
            'systemsetting': SystemSetting,
        }

        try:
            with transaction.atomic():
                if clear_existing and not dry_run:
                    self._clear_existing_data(model_map)

                # استيراد البيانات
                for model_name, model_data in data['data'].items():
                    if model_name in model_map:
                        self._import_model_data(
                            model_map[model_name],
                            model_data,
                            dry_run
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'نموذج غير معروف: {model_name}')
                        )

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS('انتهى التشغيل التجريبي بنجاح')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('تم استيراد البيانات بنجاح!')
                )

        except Exception as e:
            raise CommandError(f'خطأ أثناء استيراد البيانات: {str(e)}')

    def _clear_existing_data(self, model_map):
        """مسح البيانات الموجودة"""
        # ترتيب النماذج حسب التبعيات (العكسي)
        models_order = [
            'systemsetting', 'platesize', 'digitalsheetsize', 'digitalmachinetype',
            'offsetsheetsize', 'offsetmachinetype', 'piecesize', 'productsize',
            'producttype', 'finishingtype', 'coatingtype', 'printside',
            'printdirection', 'paperorigin', 'paperweight', 'papersize', 'papertype'
        ]

        for model_name in models_order:
            if model_name in model_map:
                model_class = model_map[model_name]
                count = model_class.objects.count()
                if count > 0:
                    model_class.objects.all().delete()
                    self.stdout.write(f'تم مسح {count} عنصر من {model_class._meta.verbose_name_plural}')

    def _import_model_data(self, model_class, model_data, dry_run):
        """استيراد بيانات نموذج محدد"""
        model_name = model_data.get('name', model_class._meta.verbose_name_plural)
        records = model_data.get('records', [])
        
        imported_count = 0
        skipped_count = 0

        for record_data in records:
            fields = record_data.get('fields', {})
            
            try:
                if not dry_run:
                    # البحث عن السجل الموجود أو إنشاء جديد
                    obj, created = self._get_or_create_object(model_class, fields)
                    if created:
                        imported_count += 1
                    else:
                        skipped_count += 1
                else:
                    imported_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'خطأ في استيراد سجل من {model_name}: {str(e)}')
                )
                skipped_count += 1

        self.stdout.write(
            f'{model_name}: تم استيراد {imported_count} عنصر، تم تخطي {skipped_count} عنصر'
        )

    def _get_or_create_object(self, model_class, fields):
        """إنشاء أو الحصول على كائن"""
        # تحديد الحقول الفريدة للبحث
        unique_fields = self._get_unique_fields(model_class)
        
        # إعداد معايير البحث
        lookup_kwargs = {}
        for field_name in unique_fields:
            if field_name in fields:
                lookup_kwargs[field_name] = fields[field_name]

        # محاولة العثور على السجل الموجود
        if lookup_kwargs:
            try:
                obj = model_class.objects.get(**lookup_kwargs)
                return obj, False
            except model_class.DoesNotExist:
                pass
            except model_class.MultipleObjectsReturned:
                # في حالة وجود عدة سجلات، نأخذ الأول
                obj = model_class.objects.filter(**lookup_kwargs).first()
                return obj, False

        # إنشاء سجل جديد
        # معالجة الحقول الخاصة
        processed_fields = self._process_fields(model_class, fields)
        
        obj = model_class.objects.create(**processed_fields)
        return obj, True

    def _get_unique_fields(self, model_class):
        """الحصول على الحقول الفريدة للنموذج"""
        unique_fields = []
        
        # البحث عن الحقول الفريدة
        for field in model_class._meta.fields:
            if field.unique or field.primary_key:
                unique_fields.append(field.name)
        
        # إضافة حقول افتراضية للبحث
        if 'name' in [f.name for f in model_class._meta.fields] and 'name' not in unique_fields:
            unique_fields.append('name')
        
        if 'key' in [f.name for f in model_class._meta.fields] and 'key' not in unique_fields:
            unique_fields.append('key')

        return unique_fields

    def _process_fields(self, model_class, fields):
        """معالجة الحقول قبل الحفظ"""
        processed_fields = {}
        
        for field_name, value in fields.items():
            # تخطي الحقول التي لا تنتمي للنموذج
            try:
                field = model_class._meta.get_field(field_name)
            except:
                continue
            
            # معالجة الحقول المرتبطة (ForeignKey)
            if hasattr(field, 'related_model') and field.related_model:
                if value:
                    try:
                        related_obj = field.related_model.objects.get(pk=value)
                        processed_fields[field_name] = related_obj
                    except field.related_model.DoesNotExist:
                        # تخطي الحقل إذا لم يوجد الكائن المرتبط
                        continue
                else:
                    processed_fields[field_name] = None
            else:
                processed_fields[field_name] = value

        return processed_fields
