# -*- coding: utf-8 -*-
"""
Service Views - شاشات وعمليات محاضر التسليم وخدمات الضمان والصيانة بعد التسليم
MWHEBA ERP — Real Estate Handover Protocols, IFRS 15 Revenue Recognition & Warranty Claims
"""
from decimal import Decimal
from datetime import datetime, date
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from users.mixins import SmartPermissionRequiredMixin
from real_estate.models import (
    PropertyHandoverReceipt,
    WarrantyTicket,
    PropertyContract,
    PropertyUnit,
    RealEstateProject,
    LegalNotice,
    ContractorProgressCertificate,
)
from real_estate.services.handover_service import HandoverExecutionService
from real_estate.services.warranty_service import WarrantyDefectService
from real_estate.services.snagging_service import OfflineSnaggingSyncService
from supplier.models import Supplier
from financial.models import ChartOfAccounts

User = get_user_model()


# ==============================================================================
# 1. محاضر استلام وتسليم الوحدات العقارية (Unit Handover Protocols)
# ==============================================================================

class HandoverReceiptListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    قائمة محاضر استلام وتسليم الوحدات العقارية الرسمية (الفعلي والحُكمي)
    """
    permission_required = 'real_estate.view_propertyhandoverreceipt'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        type_filter = request.GET.get('type', '').strip()
        project_id = request.GET.get('project', '').strip()

        qs = PropertyHandoverReceipt.objects.select_related(
            'contract__customer', 'contract__unit__project', 'site_engineer', 'executed_by'
        ).order_by('-handover_date', '-id')

        if search_query:
            qs = qs.filter(
                Q(receipt_number__icontains=search_query) |
                Q(contract__customer__name__icontains=search_query) |
                Q(contract__unit__unit_code__icontains=search_query) |
                Q(client_signatory_name__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if type_filter:
            qs = qs.filter(handover_type=type_filter)

        if project_id:
            qs = qs.filter(contract__unit__project_id=project_id)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_handovers = PropertyHandoverReceipt.objects.count()
        executed_count = PropertyHandoverReceipt.objects.filter(
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
        ).count()
        pending_count = PropertyHandoverReceipt.objects.filter(
            status=PropertyHandoverReceipt.HandoverStatus.PENDING_INSPECTION
        ).count()
        deemed_count = PropertyHandoverReceipt.objects.filter(
            handover_type=PropertyHandoverReceipt.HandoverType.DEEMED
        ).count()

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('محاضر تسليم الوحدات'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_propertyhandoverreceipt') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:handover_create'),
                'label': _('محضر تسليم جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        context = {
            'page_obj': page_obj,
            'receipts': page_obj.object_list,
            'projects': projects,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_type': type_filter,
            'selected_project': project_id,
            'status_choices': PropertyHandoverReceipt.HandoverStatus.choices,
            'type_choices': PropertyHandoverReceipt.HandoverType.choices,
            'total_handovers': total_handovers,
            'executed_count': executed_count,
            'pending_count': pending_count,
            'deemed_count': deemed_count,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_service',
            'active_submenu': 'handovers',
        }
        return render(request, 'real_estate/handover_list.html', context)


class HandoverReceiptCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إنشاء محضر استلام وتسليم رسمي جديد للوحدة العقارية
    """
    permission_required = 'real_estate.add_propertyhandoverreceipt'

    def get(self, request):
        contracts = PropertyContract.objects.filter(
            status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.COMPLETED
            ]
        ).exclude(
            unit__status__in=[
                PropertyUnit.UnitStatus.DELIVERED,
                PropertyUnit.UnitStatus.DELIVERED_DEEMED
            ]
        ).select_related('customer', 'unit__project').order_by('-contract_date')

        site_engineers = User.objects.filter(is_active=True).order_by('username')
        legal_notices = LegalNotice.objects.filter(status='SERVED').select_related('customer', 'contract')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('محاضر تسليم الوحدات'), 'url': reverse('real_estate:handover_list')},
            {'title': _('محضر تسليم جديد'), 'active': True}
        ]

        selected_contract_id = request.GET.get('contract_id')
        context = {
            'contracts': contracts,
            'site_engineers': site_engineers,
            'legal_notices': legal_notices,
            'handover_types': PropertyHandoverReceipt.HandoverType.choices,
            'selected_contract_id': int(selected_contract_id) if selected_contract_id and selected_contract_id.isdigit() else None,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'handovers',
        }
        return render(request, 'real_estate/handover_form.html', context)

    def post(self, request):
        contract_id = request.POST.get('contract')
        contract = get_object_or_404(PropertyContract.objects.select_related('unit'), pk=contract_id)

        handover_type = request.POST.get('handover_type', PropertyHandoverReceipt.HandoverType.PHYSICAL)
        handover_date_str = request.POST.get('handover_date')
        handover_date = None
        if handover_date_str:
            try:
                handover_date = datetime.strptime(handover_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        site_engineer_id = request.POST.get('site_engineer')
        site_engineer = User.objects.filter(pk=site_engineer_id).first() if site_engineer_id else None

        legal_notice_id = request.POST.get('legal_notice')
        legal_notice = LegalNotice.objects.filter(pk=legal_notice_id).first() if legal_notice_id else None

        client_signatory_name = request.POST.get('client_signatory_name', '').strip()
        client_signatory_national_id = request.POST.get('client_signatory_national_id', '').strip()
        power_of_attorney_number = request.POST.get('power_of_attorney_number', '').strip()

        try:
            electric_meter_reading = Decimal(request.POST.get('electric_meter_reading', '0') or '0')
            water_meter_reading = Decimal(request.POST.get('water_meter_reading', '0') or '0')
            gas_meter_reading = Decimal(request.POST.get('gas_meter_reading', '0') or '0')
            keys_handed_over_count = int(request.POST.get('keys_handed_over_count', '0') or '0')
            access_cards_count = int(request.POST.get('access_cards_count', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التأكد من صحة أرقام العدادات وعدد المفاتيح المسلمة.'))
            return redirect('real_estate:handover_create')

        notes = request.POST.get('notes', '').strip()

        try:
            receipt = HandoverExecutionService.create_handover_receipt(
                contract=contract,
                handover_type=handover_type,
                created_by=request.user,
                site_engineer=site_engineer,
                handover_date=handover_date,
                legal_notice=legal_notice,
                client_signatory_name=client_signatory_name,
                client_signatory_national_id=client_signatory_national_id,
                power_of_attorney_number=power_of_attorney_number,
                electric_meter_reading=electric_meter_reading,
                water_meter_reading=water_meter_reading,
                gas_meter_reading=gas_meter_reading,
                keys_handed_over_count=keys_handed_over_count,
                access_cards_count=access_cards_count,
                notes=notes
            )
            messages.success(request, _(f'تم إنشاء محضر التسليم {receipt.receipt_number} بنجاح.'))
            return redirect('real_estate:handover_detail', pk=receipt.pk)
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
            contracts = PropertyContract.objects.filter(
                status__in=[
                    PropertyContract.ContractStatus.ACTIVE,
                    PropertyContract.ContractStatus.COMPLETED
                ]
            ).exclude(
                unit__status__in=[
                    PropertyUnit.UnitStatus.DELIVERED,
                    PropertyUnit.UnitStatus.DELIVERED_DEEMED
                ]
            ).select_related('customer', 'unit__project').order_by('-contract_date')

            site_engineers = User.objects.filter(is_active=True).order_by('username')
            legal_notices = LegalNotice.objects.filter(status='SERVED').select_related('customer', 'contract')

            context = {
                'contracts': contracts,
                'site_engineers': site_engineers,
                'legal_notices': legal_notices,
                'handover_types': PropertyHandoverReceipt.HandoverType.choices,
                'form_data': request.POST,
                'breadcrumb_items': [
                    {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
                    {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
                    {'title': _('محاضر تسليم الوحدات'), 'url': reverse('real_estate:handover_list')},
                    {'title': _('محضر تسليم جديد'), 'active': True}
                ],
                'active_menu': 're_service',
                'active_submenu': 'handovers',
            }
            return render(request, 'real_estate/handover_form.html', context)


class HandoverReceiptUpdateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تعديل بيانات محضر استلام وتسليم قبل تنفيذه واعتماده نهائياً
    """
    permission_required = 'real_estate.change_propertyhandoverreceipt'

    def get(self, request, pk):
        receipt = get_object_or_404(
            PropertyHandoverReceipt.objects.select_related('contract__customer', 'contract__unit__project'),
            pk=pk
        )
        if receipt.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED:
            messages.error(request, _('لا يمكن تعديل محضر تسليم تم تنفيذه واعتماده رسمياً.'))
            return redirect('real_estate:handover_detail', pk=receipt.pk)

        site_engineers = User.objects.filter(is_active=True).order_by('username')
        legal_notices = LegalNotice.objects.filter(status='SERVED').select_related('customer', 'contract')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('محاضر تسليم الوحدات'), 'url': reverse('real_estate:handover_list')},
            {'title': receipt.receipt_number, 'url': reverse('real_estate:handover_detail', kwargs={'pk': receipt.pk})},
            {'title': _('تعديل المحضر'), 'active': True}
        ]

        context = {
            'receipt': receipt,
            'site_engineers': site_engineers,
            'legal_notices': legal_notices,
            'handover_types': PropertyHandoverReceipt.HandoverType.choices,
            'is_edit': True,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'handovers',
        }
        return render(request, 'real_estate/handover_form.html', context)

    def post(self, request, pk):
        receipt = get_object_or_404(PropertyHandoverReceipt, pk=pk)
        if receipt.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED:
            messages.error(request, _('لا يمكن تعديل محضر تسليم تم تنفيذه واعتماده رسمياً.'))
            return redirect('real_estate:handover_detail', pk=receipt.pk)

        handover_date_str = request.POST.get('handover_date')
        if handover_date_str:
            try:
                receipt.handover_date = datetime.strptime(handover_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        site_engineer_id = request.POST.get('site_engineer')
        receipt.site_engineer = User.objects.filter(pk=site_engineer_id).first() if site_engineer_id else None

        receipt.client_signatory_name = request.POST.get('client_signatory_name', '').strip()
        receipt.client_signatory_national_id = request.POST.get('client_signatory_national_id', '').strip()
        receipt.power_of_attorney_number = request.POST.get('power_of_attorney_number', '').strip()

        try:
            receipt.electric_meter_reading = Decimal(request.POST.get('electric_meter_reading', '0') or '0')
            receipt.water_meter_reading = Decimal(request.POST.get('water_meter_reading', '0') or '0')
            receipt.gas_meter_reading = Decimal(request.POST.get('gas_meter_reading', '0') or '0')
            receipt.keys_handed_over_count = int(request.POST.get('keys_handed_over_count', '0') or '0')
            receipt.access_cards_count = int(request.POST.get('access_cards_count', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التحقق من أرقام العدادات والمفاتيح.'))
            return redirect('real_estate:handover_update', pk=receipt.pk)

        receipt.notes = request.POST.get('notes', '').strip()
        receipt.full_clean()
        receipt.save()

        messages.success(request, _('تم تحديث محضر التسليم بنجاح.'))
        return redirect('real_estate:handover_detail', pk=receipt.pk)


class HandoverReceiptDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل محضر استلام وتسليم الوحدة ومطابقة العيوب الحرجة وبصمة التوثيق الرقمية
    """
    permission_required = 'real_estate.view_propertyhandoverreceipt'

    def get(self, request, pk):
        receipt = get_object_or_404(
            PropertyHandoverReceipt.objects.select_related(
                'contract__customer',
                'contract__unit__project',
                'site_engineer',
                'executed_by',
                'legal_notice',
                'revenue_journal_entry',
                'cogs_journal_entry'
            ),
            pk=pk
        )

        # فحص جاهزية الوحدة وخلوها من الملاحظات الفنية الحرجة (Snagging Blocker Check)
        readiness = OfflineSnaggingSyncService.check_unit_handover_readiness(receipt.unit)

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('محاضر تسليم الوحدات'), 'url': reverse('real_estate:handover_list')},
            {'title': receipt.receipt_number, 'active': True}
        ]

        context = {
            'receipt': receipt,
            'readiness': readiness,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'handovers',
        }
        return render(request, 'real_estate/handover_detail.html', context)


class HandoverReceiptExecuteView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    اعتماد وتنفيذ التسليم النهائي (فعلي أو حُكمي) وتوليد البصمة الرقمية وترحيل قيود IFRS 15
    """
    permission_required = 'real_estate.change_propertyhandoverreceipt'

    def post(self, request, pk):
        receipt = get_object_or_404(
            PropertyHandoverReceipt.objects.select_related('contract', 'unit'),
            pk=pk
        )
        try:
            if receipt.handover_type == PropertyHandoverReceipt.HandoverType.PHYSICAL:
                HandoverExecutionService.execute_physical_handover(
                    receipt=receipt,
                    executed_by=request.user
                )
                messages.success(
                    request,
                    _(f'تم تنفيذ واعتماد التسليم الفعلي للوحدة {receipt.unit.unit_code} رسمياً '
                      f'وترحيل قيود الإيراد المعترف به وفق معيار IFRS 15.')
                )
            else:
                HandoverExecutionService.execute_deemed_handover(
                    receipt=receipt,
                    executed_by=request.user
                )
                messages.success(
                    request,
                    _(f'تم تنفيذ واعتماد التسليم الحُكمي بقوة العقد والإنذار الرسمي للوحدة {receipt.unit.unit_code} بنجاح.')
                )
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:handover_detail', pk=receipt.pk)


class HandoverReceiptPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    طباعة محضر استلام وتسليم الوحدة الرسمي المعتمد للتوقيع والأرشفة
    """
    permission_required = 'real_estate.view_propertyhandoverreceipt'

    def get(self, request, pk):
        receipt = get_object_or_404(
            PropertyHandoverReceipt.objects.select_related(
                'contract__customer',
                'contract__unit__project',
                'site_engineer',
                'executed_by'
            ),
            pk=pk
        )
        context = {
            'receipt': receipt,
            'today': timezone.localdate(),
        }
        return render(request, 'real_estate/handover_print.html', context)


# ==============================================================================
# 2. تذاكر الضمان وخدمات الصيانة بعد التسليم (Warranty Claims & Retentions)
# ==============================================================================

class WarrantyTicketListView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تذاكر الضمان وخدمات الصيانة ومتابعة مسؤولية مقاولي الباطن
    """
    permission_required = 'real_estate.view_warrantyticket'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        priority_filter = request.GET.get('priority', '').strip()
        category_filter = request.GET.get('category', '').strip()
        project_id = request.GET.get('project', '').strip()

        qs = WarrantyTicket.objects.select_related(
            'unit__project', 'customer', 'contract', 'responsible_contractor'
        ).order_by('-created_at', '-id')

        if search_query:
            qs = qs.filter(
                Q(ticket_number__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        if status_filter:
            qs = qs.filter(status=status_filter)

        if priority_filter:
            qs = qs.filter(priority=priority_filter)

        if category_filter:
            qs = qs.filter(category=category_filter)

        if project_id:
            qs = qs.filter(unit__project_id=project_id)

        paginator = Paginator(qs, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        total_tickets = WarrantyTicket.objects.count()
        open_tickets = WarrantyTicket.objects.filter(
            status__in=[
                WarrantyTicket.TicketStatus.REPORTED,
                WarrantyTicket.TicketStatus.INSPECTED,
                WarrantyTicket.TicketStatus.CONTRACTOR_NOTIFIED,
                WarrantyTicket.TicketStatus.DEFAULTED_TO_DEVELOPER
            ]
        ).count()
        resolved_tickets = WarrantyTicket.objects.filter(
            status=WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR
        ).count()
        debited_tickets = WarrantyTicket.objects.filter(
            status=WarrantyTicket.TicketStatus.CLOSED_DEBITED
        ).count()
        total_debited_amount = WarrantyTicket.objects.filter(
            status=WarrantyTicket.TicketStatus.CLOSED_DEBITED
        ).aggregate(s=Sum('actual_repair_cost'))['s'] or Decimal('0.00')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('تذاكر الضمان والصيانة'), 'active': True}
        ]

        header_buttons = []
        if request.user.has_perm('real_estate.add_warrantyticket') or request.user.is_superuser:
            header_buttons.append({
                'url': reverse('real_estate:warranty_create'),
                'label': _('بلاغ ضمان جديد'),
                'icon': 'fa-plus',
                'class': 'btn-primary'
            })

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        context = {
            'page_obj': page_obj,
            'tickets': page_obj.object_list,
            'projects': projects,
            'search_query': search_query,
            'selected_status': status_filter,
            'selected_priority': priority_filter,
            'selected_category': category_filter,
            'selected_project': project_id,
            'status_choices': WarrantyTicket.TicketStatus.choices,
            'priority_choices': WarrantyTicket.TicketPriority.choices,
            'category_choices': WarrantyTicket.TicketCategory.choices,
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'resolved_tickets': resolved_tickets,
            'debited_tickets': debited_tickets,
            'total_debited_amount': total_debited_amount,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_service',
            'active_submenu': 'warranties',
        }
        return render(request, 'real_estate/warranty_list.html', context)


class WarrantyTicketCreateView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تسجيل بلاغ ضمان وصيانة جديد لوحدة عقارية مسلمة
    """
    permission_required = 'real_estate.add_warrantyticket'

    def get(self, request):
        delivered_units = PropertyUnit.objects.filter(
            status__in=[
                PropertyUnit.UnitStatus.DELIVERED,
                PropertyUnit.UnitStatus.DELIVERED_DEEMED
            ]
        ).select_related('project').order_by('project__name', 'unit_code')

        contractors = Supplier.objects.filter(is_active=True).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('تذاكر الضمان والصيانة'), 'url': reverse('real_estate:warranty_list')},
            {'title': _('بلاغ ضمان جديد'), 'active': True}
        ]

        context = {
            'units': delivered_units,
            'contractors': contractors,
            'category_choices': WarrantyTicket.TicketCategory.choices,
            'priority_choices': WarrantyTicket.TicketPriority.choices,
            'warranty_type_choices': WarrantyTicket.WarrantyType.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'warranties',
        }
        return render(request, 'real_estate/warranty_form.html', context)

    def post(self, request):
        unit_id = request.POST.get('unit')
        unit = get_object_or_404(PropertyUnit, pk=unit_id)

        contract = PropertyContract.objects.filter(
            unit=unit,
            status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.COMPLETED
            ]
        ).select_related('customer').first()

        if not contract:
            messages.error(request, _('لا يوجد عقد عقاري سارٍ مرتبط بهذه الوحدة المسلمة.'))
            return redirect('real_estate:warranty_create')

        category = request.POST.get('category')
        priority = request.POST.get('priority', WarrantyTicket.TicketPriority.MEDIUM)
        warranty_type = request.POST.get('warranty_type', WarrantyTicket.WarrantyType.FINISHING_ONE_YEAR)
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

        contractor_id = request.POST.get('responsible_contractor')
        contractor = Supplier.objects.filter(pk=contractor_id).first() if contractor_id else None
        if not contractor and unit and category:
            from real_estate.services.site_progress_service import ProjectProgressCalculationService
            contractor = ProjectProgressCalculationService.resolve_trade_contractor(unit=unit, warranty_category=category)

        try:
            ticket = WarrantyDefectService.create_warranty_ticket(
                unit=unit,
                contract=contract,
                customer=contract.customer,
                category=category,
                priority=priority,
                warranty_type=warranty_type,
                title=title,
                description=description,
                responsible_contractor=contractor,
                created_by=request.user
            )
            messages.success(request, _(f'تم تسجيل بلاغ الضمان {ticket.ticket_number} بنجاح.'))
            return redirect('real_estate:warranty_detail', pk=ticket.pk)
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
            delivered_units = PropertyUnit.objects.filter(
                status__in=[
                    PropertyUnit.UnitStatus.DELIVERED,
                    PropertyUnit.UnitStatus.DELIVERED_DEEMED
                ]
            ).select_related('project').order_by('project__name', 'unit_code')
            contractors = Supplier.objects.filter(is_active=True).order_by('name')

            context = {
                'units': delivered_units,
                'contractors': contractors,
                'category_choices': WarrantyTicket.TicketCategory.choices,
                'priority_choices': WarrantyTicket.TicketPriority.choices,
                'warranty_type_choices': WarrantyTicket.WarrantyType.choices,
                'form_data': request.POST,
                'breadcrumb_items': [
                    {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
                    {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
                    {'title': _('تذاكر الضمان والصيانة'), 'url': reverse('real_estate:warranty_list')},
                    {'title': _('بلاغ ضمان جديد'), 'active': True}
                ],
                'active_menu': 're_service',
                'active_submenu': 'warranties',
            }
            return render(request, 'real_estate/warranty_form.html', context)


class WarrantyTicketDetailView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تفاصيل تذكرة الضمان وتحديد مسؤولية المقاول واحتساب رصيد التأمين والخصم المالي
    """
    permission_required = 'real_estate.view_warrantyticket'

    def get(self, request, pk):
        ticket = get_object_or_404(
            WarrantyTicket.objects.select_related(
                'unit__project',
                'customer',
                'contract',
                'responsible_contractor',
                'inspected_by',
                'closed_by',
                'retention_journal_entry',
                'settlement_account'
            ),
            pk=pk
        )

        # احتساب رصيد تأمين أعمال المقاول في المشروع
        contractor_retention_balance = Decimal('0.00')
        if ticket.responsible_contractor:
            contractor_retention_balance = WarrantyDefectService.get_contractor_retention_balance(
                contractor=ticket.responsible_contractor,
                project=ticket.unit.project
            )

        # حساب الأيام المنقضية من التسليم
        last_handover = ticket.unit.handover_receipts.filter(status='EXECUTED').order_by('-handover_date').first()
        days_since_handover = None
        if last_handover:
            days_since_handover = (timezone.localdate() - last_handover.handover_date).days

        # حساب مهلة الـ SLA المتبقية
        sla_days_remaining = None
        if ticket.contractor_sla_deadline:
            sla_days_remaining = (ticket.contractor_sla_deadline - timezone.localdate()).days

        contractors = Supplier.objects.filter(is_active=True).order_by('name')
        settlement_accounts = ChartOfAccounts.objects.filter(
            is_active=True
        ).exclude(children__isnull=False).order_by('code')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('خدمة العملاء والتسليمات'), 'url': reverse('real_estate:dashboard'), 'icon': 'fa-key'},
            {'title': _('تذاكر الضمان والصيانة'), 'url': reverse('real_estate:warranty_list')},
            {'title': ticket.ticket_number, 'active': True}
        ]

        context = {
            'ticket': ticket,
            'contractor_retention_balance': contractor_retention_balance,
            'last_handover': last_handover,
            'days_since_handover': days_since_handover,
            'sla_days_remaining': sla_days_remaining,
            'contractors': contractors,
            'settlement_accounts': settlement_accounts,
            'priority_choices': WarrantyTicket.TicketPriority.choices,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_service',
            'active_submenu': 'warranties',
        }
        return render(request, 'real_estate/warranty_detail.html', context)


class WarrantyTicketAssignView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    معاينة العيب وإسناد المسؤولية لمقاول الباطن وتحديد مهلة الـ SLA للإصلاح
    """
    permission_required = 'real_estate.change_warrantyticket'

    def post(self, request, pk):
        ticket = get_object_or_404(WarrantyTicket, pk=pk)
        contractor_id = request.POST.get('responsible_contractor')
        contractor = get_object_or_404(Supplier, pk=contractor_id)
        priority = request.POST.get('priority')
        engineer_notes = request.POST.get('engineer_notes', '').strip()

        try:
            sla_days = int(request.POST.get('sla_days', '7') or '7')
        except ValueError:
            sla_days = 7

        try:
            WarrantyDefectService.inspect_and_assign_contractor(
                ticket=ticket,
                responsible_contractor=contractor,
                priority=priority,
                engineer_notes=engineer_notes,
                sla_days=sla_days,
                inspected_by=request.user
            )
            messages.success(request, _(f'تم إسناد التذكرة للمقاول {contractor.name} وإخطاره بمهلة SLA قدرها {sla_days} يوم.'))
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)

        return redirect('real_estate:warranty_detail', pk=ticket.pk)


class WarrantyTicketResolveView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إغلاق تذكرة الضمان بعد قيام المقاول المنفذ بالإصلاح على نفقته الخاصة (Zero Cost)
    """
    permission_required = 'real_estate.change_warrantyticket'

    def post(self, request, pk):
        ticket = get_object_or_404(WarrantyTicket, pk=pk)
        resolution_notes = request.POST.get('resolution_notes', '').strip()

        try:
            WarrantyDefectService.resolve_by_contractor(
                ticket=ticket,
                resolution_notes=resolution_notes,
                user=request.user
            )
            messages.success(request, _(f'تم إغلاق التذكرة {ticket.ticket_number} بنجاح بعد إتمام إصلاح المقاول دون تحميل أي تكاليف.'))
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)

        return redirect('real_estate:warranty_detail', pk=ticket.pk)


class WarrantyTicketDebitRetentionView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    إثبات تقاعس المقاول وتنفيذ الإصلاح المباشر وخصم التكلفة آلياً من تأمين المقاول (Contractor Retention)
    """
    permission_required = 'real_estate.change_warrantyticket'

    def post(self, request, pk):
        ticket = get_object_or_404(
            WarrantyTicket.objects.select_related('responsible_contractor', 'unit__project', 'contract__currency'),
            pk=pk
        )
        try:
            repair_cost = Decimal(request.POST.get('repair_cost', '0') or '0')
        except Exception:
            messages.error(request, _('يرجى التحقق من صحة مبلغ تكلفة الإصلاح.'))
            return redirect('real_estate:warranty_detail', pk=ticket.pk)

        settlement_account_id = request.POST.get('settlement_account')
        settlement_account = get_object_or_404(ChartOfAccounts, pk=settlement_account_id)
        closure_notes = request.POST.get('closure_notes', '').strip()

        try:
            WarrantyDefectService.execute_contractor_default_and_debit_retention(
                ticket=ticket,
                repair_cost=repair_cost,
                settlement_account=settlement_account,
                user=request.user,
                closure_notes=closure_notes
            )
            messages.success(
                request,
                _(f'تم تنفيذ الإصلاح المباشر وخصم مبلغ {repair_cost:,.2f} ج.م من رصيد تأمين المقاول '
                  f'{ticket.responsible_contractor.name} بنجاح وترحيل القيد المحاسبي.')
            )
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, error_msg)
        except Exception as e:
            messages.error(request, str(e))

        return redirect('real_estate:warranty_detail', pk=ticket.pk)
