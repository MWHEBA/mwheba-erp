from django.core.management.base import BaseCommand
from pricing.models import PieceSize, PaperSize


class Command(BaseCommand):
    help = 'ربط مقاسات القطع بمقاسات الورق بشكل ديناميكي'

    def handle(self, *args, **options):
        """ربط مقاسات القطع بمقاسات الورق المناسبة بناءً على الأسماء والأبعاد"""
        
        # جلب جميع مقاسات القطع ومقاسات الورق
        piece_sizes = PieceSize.objects.all()
        paper_sizes = PaperSize.objects.filter(is_active=True)
        
        if not paper_sizes.exists():
            self.stdout.write(
                self.style.WARNING('لا توجد مقاسات ورق نشطة للربط')
            )
            return
        
        linked_count = 0
        
        for piece_size in piece_sizes:
            initial_count = piece_size.paper_types.count()
            
            # ربط ذكي بناءً على الأسماء
            for paper_size in paper_sizes:
                should_link = False
                
                # قواعد الربط الذكي
                if self._should_link_by_name(piece_size.name, paper_size.name):
                    should_link = True
                elif self._should_link_by_dimensions(piece_size, paper_size):
                    should_link = True
                
                if should_link and not piece_size.paper_types.filter(id=paper_size.id).exists():
                    piece_size.paper_types.add(paper_size)
            
            new_count = piece_size.paper_types.count()
            if new_count > initial_count:
                linked_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'تم ربط {piece_size.name} بـ {new_count} مقاس ورق'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'تم تحديث {linked_count} مقاس قطع بنجاح')
        )
    
    def _should_link_by_name(self, piece_name, paper_name):
        """تحديد ما إذا كان يجب ربط المقاسات بناءً على الأسماء"""
        piece_name = piece_name.lower()
        paper_name = paper_name.lower()
        
        # ربط مقاسات الفرخ
        if 'فرخ' in piece_name and 'فرخ' in paper_name:
            return True
        
        # ربط مقاسات A
        if any(x in piece_name for x in ['a4', 'a3', 'a5']) and any(x in paper_name for x in ['a4', 'a3', 'a5']):
            return True
        
        # ربط بناءً على الأبعاد المذكورة في الاسم
        if '70' in piece_name and '100' in piece_name and '70' in paper_name and '100' in paper_name:
            return True
        
        return False
    
    def _should_link_by_dimensions(self, piece_size, paper_size):
        """تحديد ما إذا كان يجب ربط المقاسات بناءً على الأبعاد"""
        # ربط إذا كان مقاس القطع يناسب مقاس الورق (أصغر أو مساوي)
        if (piece_size.width <= paper_size.width and piece_size.height <= paper_size.height) or \
           (piece_size.width <= paper_size.height and piece_size.height <= paper_size.width):
            return True
        
        # ربط إذا كان مقاس القطع هو نصف أو ربع مقاس الورق
        if (abs(piece_size.width - paper_size.width/2) < 1 and abs(piece_size.height - paper_size.height) < 1) or \
           (abs(piece_size.width - paper_size.width) < 1 and abs(piece_size.height - paper_size.height/2) < 1):
            return True
        
        return False
