from django.core.management.base import BaseCommand
from product.models import StockMovement, Stock
import re


class Command(BaseCommand):
    help = 'تنظيف حركات المخزون المكررة وإعادة حساب كميات المخزون'

    def handle(self, *args, **options):
        # البحث عن حركات المخزون المكررة
        all_movements = StockMovement.objects.all()
        movements_to_delete = []
        unique_references = set()

        # حذف الحركات المكررة التي لا تحتوي على رقم البند
        for movement in all_movements:
            if movement.reference_number and movement.reference_number.startswith("PURCHASE-"):
                # تحقق مما إذا كانت حركة بدون رقم بند
                if not re.search(r'-ITEM\d+$', movement.reference_number):
                    self.stdout.write(f'حركة مكررة: {movement.reference_number}')
                    movements_to_delete.append(movement.id)
                else:
                    # إذا كانت تحتوي على رقم بند، احتفظ بها
                    unique_references.add(movement.reference_number)

        # حذف الحركات المكررة
        duplicate_count = StockMovement.objects.filter(id__in=movements_to_delete).count()
        StockMovement.objects.filter(id__in=movements_to_delete).delete()
        
        # إعادة حساب أرصدة المخزون
        stocks = Stock.objects.all()
        for stock in stocks:
            # إعادة ضبط الكمية إلى صفر
            stock.quantity = 0
            stock.save()
        
        # إعادة حساب الكميات بناءً على حركات المخزون المتبقية
        for movement in StockMovement.objects.all():
            movement.update_stock()
        
        self.stdout.write(self.style.SUCCESS(f'تم حذف {duplicate_count} حركة مكررة وإعادة حساب أرصدة المخزون بنجاح')) 