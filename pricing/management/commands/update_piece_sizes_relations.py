from django.core.management.base import BaseCommand
from pricing.models import PieceSize, PaperSize


class Command(BaseCommand):
    help = 'تحديث علاقات مقاسات القطع مع مقاسات الورق'

    def handle(self, *args, **options):
        # جلب مقاسات الورق الموجودة
        try:
            paper_70x100 = PaperSize.objects.filter(name__icontains="70").first()
            paper_a4 = PaperSize.objects.filter(name__icontains="A4").first()
            paper_a3 = PaperSize.objects.filter(name__icontains="A3").first()
            all_frakh_papers = PaperSize.objects.filter(name__icontains="فرخ", is_active=True)
            all_a_papers = PaperSize.objects.filter(name__iregex=r'A[0-9]', is_active=True)
        except:
            self.stdout.write(self.style.ERROR('خطأ في جلب مقاسات الورق'))
            return

        updated_count = 0

        # تحديث مقاسات الفرخ
        frakh_pieces = PieceSize.objects.filter(name__icontains="فرخ")
        for piece in frakh_pieces:
            if paper_70x100:
                piece.paper_types.add(paper_70x100)
            if all_frakh_papers.exists():
                piece.paper_types.add(*all_frakh_papers)
            updated_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'تم تحديث {piece.name} - مرتبط بـ {piece.paper_types.count()} مقاس ورق')
            )

        # تحديث مقاسات A
        a_pieces = PieceSize.objects.filter(name__icontains="A")
        for piece in a_pieces:
            if "A4" in piece.name and paper_a4:
                piece.paper_types.add(paper_a4)
            elif "A3" in piece.name and paper_a3:
                piece.paper_types.add(paper_a3)
            
            if all_a_papers.exists():
                piece.paper_types.add(*all_a_papers)
            updated_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'تم تحديث {piece.name} - مرتبط بـ {piece.paper_types.count()} مقاس ورق')
            )

        # تحديث المقاسات العامة - ربطها بجميع مقاسات الورق
        general_pieces = PieceSize.objects.filter(
            name__in=["30×40", "20×30", "15×20", "10×15", "9×13"]
        )
        all_papers = PaperSize.objects.filter(is_active=True)
        for piece in general_pieces:
            if all_papers.exists():
                piece.paper_types.add(*all_papers)
            updated_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'تم تحديث {piece.name} - مرتبط بـ {piece.paper_types.count()} مقاس ورق (عام)')
            )

        self.stdout.write(
            self.style.SUCCESS(f'تم تحديث {updated_count} مقاس قطع بنجاح')
        )
