# -*- coding: utf-8 -*-
"""
BulkPricingGeneratorService - محرك توليد وتحديث أسعار الوحدات العقارية آلياً (Wave 2 Phase 4)
يحسب فروق الأدوار، النواصي، الواجهات، الفيو، والتشطيب وفق معادلات هندسية وتجارية موحدة.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.project import RealEstateProject
from real_estate.models.topology import PropertyBlock
from real_estate.models.unit import PropertyUnit
from real_estate.models.pricing import UnitPricingMatrixConfig

logger = logging.getLogger(__name__)


class BulkPricingGeneratorService:
    """
    الخدمة المركزية لإعداد وتطبيق مصفوفة تسعير الوحدات العقارية
    تتيح تسعير مئات الوحدات بضغطة زر واحدة بناءً على لائح التسعير المعتمدة للمشروع.
    """

    @classmethod
    def get_active_config(
        cls,
        project: RealEstateProject,
        block: Optional[PropertyBlock] = None
    ) -> UnitPricingMatrixConfig:
        """
        جلب لائحة التسعير النشطة الخاصة بالعمارة أو المشروع
        """
        if block:
            config = UnitPricingMatrixConfig.objects.filter(
                project=project,
                block=block,
                is_active=True
            ).first()
            if config:
                return config

        config = UnitPricingMatrixConfig.objects.filter(
            project=project,
            block__isnull=True,
            is_active=True
        ).first()

        if not config:
            raise ValidationError(
                _("لا توجد مصفوفة تسعير نشطة ومعتمدة للمشروع %(prj)s.") % {'prj': project.name}
            )
        return config

    @classmethod
    def calculate_unit_price(
        cls,
        unit: PropertyUnit,
        config: UnitPricingMatrixConfig
    ) -> Dict[str, Any]:
        """
        حساب تفصيلي لسعر المتر وسعر الوحدة الإجمالي بناءً على علاوات وخصومات المصفوفة
        """
        base_meter = Decimal(str(config.base_meter_price))

        # 1. علاوة تدرج الأدوار (Floor Rise Rate)
        floor_num = unit.floor.floor_number if unit.floor else 1
        floor_diff = max(0, floor_num - config.base_floor_number)
        floor_rise_rate = (Decimal(str(config.floor_rise_rate)) * Decimal(str(floor_diff))).quantize(Decimal('0.01'))

        # 2. علاوة اتجاه الواجهة (Orientation Premium)
        orientation_map = {
            PropertyUnit.Orientation.NORTH: config.north_orientation_premium,
            PropertyUnit.Orientation.NORTH_EAST: config.north_east_premium,
            PropertyUnit.Orientation.NORTH_WEST: config.north_west_premium,
            PropertyUnit.Orientation.EAST: config.east_orientation_premium,
            PropertyUnit.Orientation.WEST: config.west_orientation_premium,
            PropertyUnit.Orientation.SOUTH: config.south_orientation_premium,
            PropertyUnit.Orientation.SOUTH_EAST: Decimal('0.00'),
            PropertyUnit.Orientation.SOUTH_WEST: Decimal('0.00'),
        }
        orientation_rate = Decimal(str(orientation_map.get(unit.orientation, Decimal('0.00'))))

        # 3. علاوة أو خصم نوع الإطلالة والفيو (View Premium / Discount)
        view_map = {
            PropertyUnit.ViewType.MAIN_STREET: config.main_street_view_premium,
            PropertyUnit.ViewType.GARDEN_PARK: config.garden_park_view_premium,
            PropertyUnit.ViewType.POOL_VIEW: config.pool_water_view_premium,
            PropertyUnit.ViewType.OPEN_VIEW: config.open_view_premium,
            PropertyUnit.ViewType.SIDE_STREET: config.side_street_view_premium,
            PropertyUnit.ViewType.INTERNAL_COURT: -Decimal(str(config.internal_court_discount)),
        }
        view_rate = Decimal(str(view_map.get(unit.view_type, Decimal('0.00'))))

        # 4. علاوة الناصية (Corner Unit Premium)
        corner_rate = Decimal(str(config.corner_unit_premium)) if unit.is_corner else Decimal('0.00')

        # إجمالي نسبة علاوات التميز بالمتر
        total_premium_rate = floor_rise_rate + orientation_rate + view_rate + corner_rate

        # سعر المتر بعد علاوات التميز وقبل التشطيب
        adjusted_meter_price = (base_meter * (Decimal('1.00') + (total_premium_rate / Decimal('100.00')))).quantize(Decimal('0.01'))

        # 5. تكلفة مستوى التشطيب (Finishing Add-on)
        finishing_addon = Decimal('0.00')
        if unit.finishing_type == PropertyUnit.FinishingType.FULLY_FINISHED:
            finishing_addon = Decimal(str(config.fully_finished_meter_addon))
        elif unit.finishing_type == PropertyUnit.FinishingType.ULTRA_LUX:
            finishing_addon = Decimal(str(config.ultra_lux_meter_addon))

        final_meter_price = (adjusted_meter_price + finishing_addon).quantize(Decimal('0.01'))

        # 6. أسعار مساحات الوحدة
        gross_area = Decimal(str(unit.gross_area))
        base_unit_price = (gross_area * final_meter_price).quantize(Decimal('0.01'))

        # سعر الحديقة الخاصة
        garden_area = Decimal(str(unit.garden_area or Decimal('0.00')))
        garden_meter_price = Decimal(str(config.garden_meter_price))
        garden_price = (garden_area * garden_meter_price).quantize(Decimal('0.01')) if garden_area > 0 else Decimal('0.00')

        # سعر باكيات الجراج
        parking_count = unit.parking_slots_count or 0
        parking_slot_price = Decimal(str(config.parking_slot_price))
        parking_price = (Decimal(str(parking_count)) * parking_slot_price).quantize(Decimal('0.01')) if parking_count > 0 else Decimal('0.00')

        # إجمالي سعر الوحدة النهائي
        total_unit_price = base_unit_price + garden_price + parking_price

        # 7. وديعة الصيانة القانونية
        maint_rate = Decimal(str(config.maintenance_deposit_rate))
        maintenance_deposit = (total_unit_price * (maint_rate / Decimal('100.00'))).quantize(Decimal('0.01'))

        return {
            'config_id': config.id,
            'config_name': config.name,
            'base_meter_price': str(base_meter),
            'floor_rise_rate': str(floor_rise_rate),
            'orientation_rate': str(orientation_rate),
            'view_rate': str(view_rate),
            'corner_rate': str(corner_rate),
            'total_premium_rate': str(total_premium_rate),
            'finishing_addon': str(finishing_addon),
            'final_meter_price': final_meter_price,
            'gross_area': str(gross_area),
            'base_unit_price': base_unit_price,
            'garden_area': str(garden_area),
            'garden_price': garden_price,
            'parking_slots_count': parking_count,
            'parking_price': parking_price,
            'total_unit_price': total_unit_price,
            'maintenance_deposit_rate': str(maint_rate),
            'maintenance_deposit': maintenance_deposit,
        }

    @classmethod
    def apply_pricing_to_unit(
        cls,
        unit: PropertyUnit,
        config: Optional[UnitPricingMatrixConfig] = None,
        save: bool = True,
        user = None
    ) -> PropertyUnit:
        """
        تطبيق وحفظ معادلة التسعير على وحدة فردية
        حماية صارمة: منع تعديل تسعير الوحدات المباعة تعاقدياً أو المسلمة، والتحقق من الصلاحيات
        """
        if user and not (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_admin', False) or
            user.has_perm('real_estate.change_unitpricingmatrixconfig') or
            user.has_perm('real_estate.change_propertyunit')
        ):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_("المستخدم لا يملك صلاحية تعديل وتسعير الوحدات العقارية."))

        if unit.status in [PropertyUnit.UnitStatus.CONTRACTED, PropertyUnit.UnitStatus.DELIVERED]:
            raise ValidationError(
                _("لا يمكن إعادة تسعير الوحدة %(code)s لأنها في حالة (%(stat)s) تعاقدية مبرمة.") % {
                    'code': unit.unit_code,
                    'stat': unit.get_status_display()
                }
            )

        if not config:
            config = cls.get_active_config(unit.project, unit.block)

        breakdown = cls.calculate_unit_price(unit, config)

        unit.meter_price = breakdown['final_meter_price']
        unit.base_price = breakdown['base_unit_price']
        unit.garden_price = breakdown['garden_price']
        unit.parking_price = breakdown['parking_price']
        unit.total_price = breakdown['total_unit_price']
        unit.maintenance_deposit = breakdown['maintenance_deposit']
        unit.pricing_breakdown = {
            'config_id': breakdown['config_id'],
            'config_name': breakdown['config_name'],
            'base_meter_price': breakdown['base_meter_price'],
            'floor_rise_rate': breakdown['floor_rise_rate'],
            'orientation_rate': breakdown['orientation_rate'],
            'view_rate': breakdown['view_rate'],
            'corner_rate': breakdown['corner_rate'],
            'total_premium_rate': breakdown['total_premium_rate'],
            'finishing_addon': breakdown['finishing_addon'],
            'maintenance_deposit_rate': breakdown['maintenance_deposit_rate'],
        }

        if save:
            unit.save(update_fields=[
                'meter_price',
                'base_price',
                'garden_price',
                'parking_price',
                'total_price',
                'maintenance_deposit',
                'pricing_breakdown',
                'updated_at'
            ])
            logger.info(f"Price updated for unit {unit.unit_code}: {unit.total_price} EGP")

        return unit

    @classmethod
    def bulk_generate_pricing(
        cls,
        project: RealEstateProject,
        block: Optional[PropertyBlock] = None,
        config: Optional[UnitPricingMatrixConfig] = None,
        filter_status: Optional[List[str]] = None,
        dry_run: bool = False,
        user = None
    ) -> Dict[str, Any]:
        """
        توليد وتحديث تسعير كافة الوحدات في المشروع أو العمارة دفعة واحدة
        """
        if user and not (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_admin', False) or
            user.has_perm('real_estate.change_unitpricingmatrixconfig') or
            user.has_perm('real_estate.change_propertyunit')
        ):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_("المستخدم لا يملك صلاحية تعديل وتسعير الوحدات العقارية."))

        if not config:
            config = cls.get_active_config(project, block)

        units_qs = PropertyUnit.objects.filter(
            project=project
        ).select_related('floor', 'block', 'project')

        if filter_status:
            units_qs = units_qs.filter(status__in=filter_status)

        if block:
            units_qs = units_qs.filter(block=block)

        total_evaluated = 0
        total_updated = 0
        skipped_contracted = 0
        portfolio_before = Decimal('0.00')
        portfolio_after = Decimal('0.00')
        units_report = []

        with transaction.atomic():
            for unit in units_qs:
                total_evaluated += 1
                portfolio_before += unit.total_price

                # الحماية ضد الوحدات المباعة
                if unit.status in [PropertyUnit.UnitStatus.CONTRACTED, PropertyUnit.UnitStatus.DELIVERED]:
                    skipped_contracted += 1
                    portfolio_after += unit.total_price
                    continue

                breakdown = cls.calculate_unit_price(unit, config)
                new_total = breakdown['total_unit_price']
                portfolio_after += new_total

                if not dry_run:
                    cls.apply_pricing_to_unit(unit, config=config, save=True)

                total_updated += 1
                units_report.append({
                    'unit_code': unit.unit_code,
                    'status': unit.status,
                    'floor': unit.floor.floor_number if unit.floor else 1,
                    'gross_area': str(unit.gross_area),
                    'old_meter_price': str(unit.meter_price),
                    'new_meter_price': str(breakdown['final_meter_price']),
                    'old_total_price': str(unit.total_price),
                    'new_total_price': str(new_total),
                    'maintenance_deposit': str(breakdown['maintenance_deposit'])
                })

            if dry_run:
                # إذا كان فحص تجريبي يتم التراجع عن أي تعديل
                transaction.set_rollback(True)
            elif user:
                from utils.logs import create_log
                create_log(
                    user=user,
                    action='APPLY_BULK_PRICING',
                    model_name='RealEstateProject',
                    object_id=str(project.id),
                    details={
                        'project_code': project.code,
                        'total_updated': total_updated,
                        'portfolio_after': str(portfolio_after)
                    }
                )

        logger.info(
            f"Bulk pricing completed for project {project.code}: {total_updated} updated, "
            f"{skipped_contracted} skipped. Total: {portfolio_after} EGP"
        )

        return {
            'project_code': project.code,
            'project_name': project.name,
            'block_code': block.code if block else None,
            'config_name': config.name,
            'dry_run': dry_run,
            'total_units_evaluated': total_evaluated,
            'total_units_updated': total_updated,
            'skipped_contracted_units': skipped_contracted,
            'total_portfolio_value_before': portfolio_before,
            'total_portfolio_value_after': portfolio_after,
            'portfolio_value_difference': portfolio_after - portfolio_before,
            'units': units_report
        }
