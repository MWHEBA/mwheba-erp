from django.core.management.base import BaseCommand
from pricing.models import PieceSize, PaperSize


class Command(BaseCommand):
    help = 'إضافة مقاسات القطع الأولية مع ربطها بمقاسات الورق المناسبة'

    def handle(self, *args, **options):
        # جلب مقاسات الورق المتاحة
        paper_70x100 = PaperSize.objects.filter(name__icontains='70').first()
        paper_a4 = PaperSize.objects.filter(name__icontains='A4').first()
        
        # إنشاء مقاسات قطع أساسية مع ربطها بمقاسات الورق المناسبة
        piece_sizes_data = [
            # مقاسات الفرخ الشائعة - مرتبطة بورق 70×100
            {"name": "فرخ كامل 70×100", "width": 70.0, "height": 100.0, "paper_type": paper_70x100, "is_default": True},
            {"name": "فرخ نصف 50×70", "width": 50.0, "height": 70.0, "paper_type": paper_70x100},
            {"name": "فرخ ربع 35×50", "width": 35.0, "height": 50.0, "paper_type": paper_70x100},
            {"name": "فرخ ثمن 25×35", "width": 25.0, "height": 35.0, "paper_type": paper_70x100},
            
            # مقاسات A الشائعة - مرتبطة بورق A4 إذا وُجد
            {"name": "A4 - 21×29.7", "width": 21.0, "height": 29.7, "paper_type": paper_a4},
            {"name": "A5 - 14.8×21", "width": 14.8, "height": 21.0, "paper_type": paper_a4},
            {"name": "A3 - 29.7×42", "width": 29.7, "height": 42.0, "paper_type": paper_a4},
            
            # مقاسات عامة شائعة - بدون ربط محدد
            {"name": "30×40", "width": 30.0, "height": 40.0},
            {"name": "20×30", "width": 20.0, "height": 30.0},
            {"name": "15×20", "width": 15.0, "height": 20.0},
            {"name": "10×15", "width": 10.0, "height": 15.0},
            {"name": "9×13", "width": 9.0, "height": 13.0},
        ]

        created_count = 0
        for piece_data in piece_sizes_data:
            # إعداد البيانات الافتراضية
            defaults = {
                "width": piece_data["width"],
                "height": piece_data["height"],
                "is_active": True,
                "is_default": piece_data.get("is_default", False),
            }
            
            # إضافة نوع الورق إذا وُجد
            if piece_data.get("paper_type"):
                defaults["paper_type"] = piece_data["paper_type"]
            
            piece_size, created = PieceSize.objects.get_or_create(
                name=piece_data["name"],
                defaults=defaults
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'تم إنشاء مقاس القطع: {piece_size.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'مقاس القطع موجود بالفعل: {piece_size.name}')
                )

        # تعيين أول مقاس كافتراضي إذا لم يكن هناك افتراضي
        if not PieceSize.objects.filter(is_default=True).exists():
            first_piece = PieceSize.objects.first()
            if first_piece:
                first_piece.is_default = True
                first_piece.save()
                self.stdout.write(
                    self.style.SUCCESS(f'تم تعيين {first_piece.name} كمقاس افتراضي')
                )

        self.stdout.write(
            self.style.SUCCESS(f'تم إنشاء {created_count} مقاس قطع جديد')
        )
