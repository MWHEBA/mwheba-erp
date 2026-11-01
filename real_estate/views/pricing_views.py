# -*- coding: utf-8 -*-
from decimal import Decimal
import json

from django.shortcuts import get_object_or_404, render
from django.views import View
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from users.mixins import SmartPermissionRequiredMixin
from utils.logs import create_log
from real_estate.models.project import RealEstateProject
from real_estate.models.pricing import UnitPricingMatrixConfig
from real_estate.services.pricing_service import BulkPricingGeneratorService


class ProjectPricingView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    شاشة إدارة وضبط مصفوفة التسعير الآلي للوحدات العقارية
    تلتزم بالقواعد الصارمة: متغيرات :root، ألوان مسطحة، وبطاقات إحصائية قياسية
    """
    permission_required = 'real_estate.change_unitpricingmatrixconfig'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, id=project_id)
        config = UnitPricingMatrixConfig.objects.filter(project=project, is_active=True).first()

        units = project.units.filter(is_active=True)
        total_units_count = units.count()
        available_units_count = units.filter(status='AVAILABLE').count()
        total_portfolio_value = sum((u.total_price for u in units), Decimal('0.00'))
        avg_meter_price = (sum((u.meter_price for u in units), Decimal('0.00')) / total_units_count) if total_units_count > 0 else Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('القطاع العقاري'), 'url': '#', 'icon': 'fa-building'},
            {'title': project.name, 'url': reverse('real_estate:project_matrix', kwargs={'project_id': project.id})},
            {'title': _('مصفوفة التسعير الآلي'), 'active': True}
        ]

        context = {
            'project': project,
            'config': config,
            'total_units_count': total_units_count,
            'available_units_count': available_units_count,
            'total_portfolio_value': total_portfolio_value,
            'avg_meter_price': avg_meter_price.quantize(Decimal('0.01')),
            'breadcrumb_items': breadcrumb_items,
        }
        return render(request, 'real_estate/pricing_matrix.html', context)

    def post(self, request, project_id):
        """
        حفظ أو تحديث إعدادات مصفوفة التسعير للمشروع
        """
        project = get_object_or_404(RealEstateProject, id=project_id)

        try:
            base_meter_price = Decimal(request.POST.get('base_meter_price', '0'))
            if base_meter_price <= Decimal('0.00'):
                return JsonResponse({'success': False, 'message': 'سعر المتر الأساسي يجب أن يكون أكبر من الصفر.'}, status=400)

            name = request.POST.get('name', f"لائحة تسعير {project.name}")
            base_floor = int(request.POST.get('base_floor_number', 1))
            floor_rise = Decimal(request.POST.get('floor_rise_rate', '1.50'))
            north_prem = Decimal(request.POST.get('north_orientation_premium', '5.00'))
            main_st_prem = Decimal(request.POST.get('main_street_view_premium', '6.00'))
            garden_prem = Decimal(request.POST.get('garden_park_view_premium', '5.00'))
            pool_prem = Decimal(request.POST.get('pool_water_view_premium', '7.00'))
            internal_disc = Decimal(request.POST.get('internal_court_discount', '5.00'))
            corner_prem = Decimal(request.POST.get('corner_unit_premium', '4.00'))
            parking_price = Decimal(request.POST.get('parking_slot_price', '150000.00'))
            finished_addon = Decimal(request.POST.get('fully_finished_meter_addon', '4000.00'))
            maint_rate = Decimal(request.POST.get('maintenance_deposit_rate', '8.00'))

            config, _ = UnitPricingMatrixConfig.objects.update_or_create(
                project=project,
                block__isnull=True,
                is_active=True,
                defaults={
                    'name': name,
                    'base_meter_price': base_meter_price,
                    'base_floor_number': base_floor,
                    'floor_rise_rate': floor_rise,
                    'north_orientation_premium': north_prem,
                    'main_street_view_premium': main_st_prem,
                    'garden_park_view_premium': garden_prem,
                    'pool_water_view_premium': pool_prem,
                    'internal_court_discount': internal_disc,
                    'corner_unit_premium': corner_prem,
                    'parking_slot_price': parking_price,
                    'fully_finished_meter_addon': finished_addon,
                    'maintenance_deposit_rate': maint_rate,
                    'created_by': request.user,
                }
            )

            # توثيق الإجراء وتعديل التسعير في سجل النظام
            create_log(
                user=request.user,
                action='UPDATE_PRICING_CONFIG',
                model_name='UnitPricingMatrixConfig',
                object_id=str(config.id),
                details={
                    'project_id': project.id,
                    'project_name': project.name,
                    'base_meter_price': str(base_meter_price)
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return JsonResponse({
                'success': True,
                'message': 'تم حفظ وتفعيل لائحة التسعير بنجاح.',
                'config_id': config.id
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)


class ApiPreviewPricingView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    معاينة أثر تطبيق مصفوفة التسعير على الوحدات تجريبياً (Dry Run)
    """
    permission_required = 'real_estate.change_unitpricingmatrixconfig'

    def get(self, request, project_id):
        project = get_object_or_404(RealEstateProject, id=project_id)
        try:
            report = BulkPricingGeneratorService.bulk_generate_pricing(
                project=project,
                dry_run=True,
                user=request.user
            )
            return JsonResponse({'success': True, 'report': report})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)


class ApiApplyBulkPricingView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تطبيق مصفوفة التسعير فعلياً على قاعدة البيانات وتحديث أسعار الوحدات
    """
    permission_required = 'real_estate.change_unitpricingmatrixconfig'

    def post(self, request, project_id):
        project = get_object_or_404(RealEstateProject, id=project_id)
        try:
            report = BulkPricingGeneratorService.bulk_generate_pricing(
                project=project,
                dry_run=False,
                user=request.user
            )

            create_log(
                user=request.user,
                action='APPLY_BULK_PRICING',
                model_name='RealEstateProject',
                object_id=str(project.id),
                details={
                    'project_name': project.name,
                    'total_units_updated': report.get('total_units_updated', 0)
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return JsonResponse({
                'success': True,
                'message': f"تم بنجاح تحديث أسعار {report['total_units_updated']} وحدة عقارية.",
                'report': report
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
