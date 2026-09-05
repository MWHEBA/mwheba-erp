"""
أمر تسوية وترقية بيانات خدمات الموردين وزنكات CTP
supplier/management/commands/heal_and_backfill_services.py
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "تسوية زنكات CTP التائهة وترقية بيانات خدمات الموردين السابقة"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("بدء تسوية بيانات الزنكات وخدمات الموردين..."))

        # 1. تسوية زنكات CTP
        from printing_pricing.models import PrintingMachine, MachineDimension
        
        plates_map = {
            'plate_sm52': 'sm52',
            'plate_sm74': 'sm74',
            'plate_cd102': 'cd102',
        }

        healed_plates = 0
        with transaction.atomic():
            for plate_code, machine_code in plates_map.items():
                plate = MachineDimension.objects.filter(dimension_type='plate', code=plate_code).first()
                machine = PrintingMachine.objects.filter(code=machine_code).first()
                if plate and machine:
                    if plate.machine_id != machine.pk:
                        plate.machine = machine
                        plate.save(update_fields=['machine'])
                        healed_plates += 1
                        self.stdout.write(self.style.SUCCESS(f"تم ربط الزنكة {plate.name} بالماكينة {machine.name}"))

        self.stdout.write(self.style.SUCCESS(f"تم الانتهاء من تسوية الزنكات بنجاح (تم تحديث {healed_plates} زنكة)"))

        # 2. ترقية خدمات الموردين السابقة (إن وجدت)
        from supplier.models import SupplierService
        from printing_pricing.models import (
            CoatingType, FinishingType, PackagingType,
            PaperSize, PaperOrigin, PaperWeight
        )

        services = SupplierService.objects.all()
        backfilled_count = 0
        with transaction.atomic():
            for svc in services:
                updated = False
                attrs = svc.attributes if isinstance(svc.attributes, dict) else {}

                # سلوفان
                if svc.service_type and svc.service_type.code == 'coating' and not svc.coating_type:
                    ctype_name = attrs.get('coating_type')
                    if ctype_name:
                        c_obj = CoatingType.objects.filter(name=ctype_name, is_active=True).first()
                        if c_obj:
                            svc.coating_type = c_obj
                            updated = True

                # تشطيب
                if svc.service_type and svc.service_type.code == 'finishing' and not svc.finishing_type:
                    ftype_name = attrs.get('finishing_type')
                    if ftype_name:
                        f_obj = FinishingType.objects.filter(name=ftype_name, is_active=True).first()
                        if f_obj:
                            svc.finishing_type = f_obj
                            updated = True

                # تقفيل
                if svc.service_type and svc.service_type.code == 'packaging' and not svc.packaging_type:
                    ptype_name = attrs.get('packaging_type')
                    if ptype_name:
                        p_obj = PackagingType.objects.filter(name=ptype_name, is_active=True).first()
                        if p_obj:
                            svc.packaging_type = p_obj
                            updated = True

                # زنكات
                if svc.service_type and svc.service_type.code == 'ctp_plates' and not svc.plate_size:
                    psize_val = attrs.get('plate_size')
                    if psize_val:
                        pl_obj = MachineDimension.objects.filter(dimension_type='plate', name=psize_val, is_active=True).first()
                        if pl_obj:
                            svc.plate_size = pl_obj
                            updated = True

                # ورق
                if svc.service_type and svc.service_type.code == 'paper':
                    if not svc.paper_size:
                        psize_name = attrs.get('sheet_size') or attrs.get('parent_sheet_size')
                        if psize_name:
                            ps_obj = PaperSize.objects.filter(name=psize_name, is_active=True).first()
                            if ps_obj:
                                svc.paper_size = ps_obj
                                updated = True
                    if not svc.paper_origin:
                        origin_name = attrs.get('origin')
                        if origin_name:
                            po_obj = PaperOrigin.objects.filter(name=origin_name, is_active=True).first()
                            if po_obj:
                                svc.paper_origin = po_obj
                                updated = True
                    if not svc.gsm and attrs.get('gsm'):
                        try:
                            svc.gsm = int(attrs['gsm'])
                            updated = True
                        except Exception:
                            pass

                if updated:
                    svc.save()
                    backfilled_count += 1

        self.stdout.write(self.style.SUCCESS(f"تم الانتهاء من ترقية خدمات الموردين (تم تحديث {backfilled_count} خدمة)"))
