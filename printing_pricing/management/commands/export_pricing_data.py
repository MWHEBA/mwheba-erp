"""
أمر Django لتصدير البيانات الحالية كنسخة احتياطية
Usage: python manage.py export_pricing_data --output-file backup.json
"""

import json
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.serializers import serialize
from printing_pricing.models.settings_models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    PrintDirection, PrintSide, CoatingType, FinishingType,
    ProductType, ProductSize, PieceSize,
    OffsetMachineType, OffsetSheetSize,
    DigitalMachineType, DigitalSheetSize,
    PlateSize, SystemSetting
)


class Command(BaseCommand):
    help = 'تصدير البيانات الحالية كنسخة احتياطية'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-file',
            type=str,
            default=f'pricing_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
            help='اسم ملف النسخة الاحتياطية'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'csv'],
            default='json',
            help='تنسيق الملف المصدر'
        )

    def handle(self, *args, **options):
        output_file = options['output_file']
        format_type = options['format']

        self.stdout.write(f'بدء تصدير البيانات إلى: {output_file}')

        # قائمة النماذج المراد تصديرها
        models_to_export = [
            ('أنواع الورق', PaperType),
            ('مقاسات الورق', PaperSize),
            ('أوزان الورق', PaperWeight),
            ('مناشئ الورق', PaperOrigin),
            ('اتجاهات الطباعة', PrintDirection),
            ('جوانب الطباعة', PrintSide),
            ('أنواع التغطية', CoatingType),
            ('أنواع التشطيب', FinishingType),
            ('أنواع المنتجات', ProductType),
            ('مقاسات المنتجات', ProductSize),
            ('مقاسات القطع', PieceSize),
            ('أنواع ماكينات الأوفست', OffsetMachineType),
            ('مقاسات ماكينات الأوفست', OffsetSheetSize),
            ('أنواع ماكينات الديجيتال', DigitalMachineType),
            ('مقاسات ماكينات الديجيتال', DigitalSheetSize),
            ('مقاسات الزنكات', PlateSize),
            ('إعدادات النظام', SystemSetting),
        ]

        if format_type == 'json':
            self._export_json(models_to_export, output_file)
        elif format_type == 'csv':
            self._export_csv(models_to_export, output_file)

        self.stdout.write(
            self.style.SUCCESS(f'تم تصدير البيانات بنجاح إلى: {output_file}')
        )

    def _export_json(self, models_to_export, output_file):
        """تصدير البيانات بتنسيق JSON"""
        export_data = {
            'metadata': {
                'export_date': datetime.now().isoformat(),
                'version': '1.0',
                'description': 'نسخة احتياطية من بيانات نظام التسعير'
            },
            'data': {}
        }

        total_records = 0

        for model_name, model_class in models_to_export:
            queryset = model_class.objects.all()
            count = queryset.count()
            
            if count > 0:
                # تحويل البيانات إلى JSON
                serialized_data = serialize('json', queryset)
                export_data['data'][model_class._meta.model_name] = {
                    'name': model_name,
                    'count': count,
                    'records': json.loads(serialized_data)
                }
                total_records += count
                
                self.stdout.write(f'تم تصدير {count} عنصر من {model_name}')

        export_data['metadata']['total_records'] = total_records

        # حفظ الملف
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def _export_csv(self, models_to_export, output_file):
        """تصدير البيانات بتنسيق CSV"""
        import csv
        
        # إنشاء ملف CSV منفصل لكل نموذج
        base_name = output_file.replace('.csv', '')
        
        for model_name, model_class in models_to_export:
            queryset = model_class.objects.all()
            count = queryset.count()
            
            if count > 0:
                csv_file = f"{base_name}_{model_class._meta.model_name}.csv"
                
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # كتابة رؤوس الأعمدة
                    field_names = [field.name for field in model_class._meta.fields]
                    writer.writerow(field_names)
                    
                    # كتابة البيانات
                    for obj in queryset:
                        row = []
                        for field_name in field_names:
                            value = getattr(obj, field_name)
                            row.append(str(value) if value is not None else '')
                        writer.writerow(row)
                
                self.stdout.write(f'تم تصدير {count} عنصر من {model_name} إلى {csv_file}')
