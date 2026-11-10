# -*- coding: utf-8 -*-
"""
Real Estate Analytics & Financial Reporting Views
MWHEBA ERP — Real Estate Wave 6 (Phase 6.1: Dual-Perspective Subledger, Cash Flow Radar, WIP & IFRS 15, Broker Radar)
"""
from datetime import datetime
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.paginator import Paginator

from users.mixins import SmartPermissionRequiredMixin
from customer.models import Customer
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyContract,
    RealEstateBroker,
    BrokerCommission,
)
from real_estate.services.reporting_service import RealEstateReportingService


class DualSubledgerReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير كشف الحساب المزدوج للعقود والعملاء (المنظور التعاقدي مقابل المنظور المالي والشيكات وIFRS 15)
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request):
        search_query = request.GET.get('q', '').strip()
        project_id = request.GET.get('project', '').strip()
        customer_id = request.GET.get('customer', '').strip()
        status_filter = request.GET.get('status', '').strip()
        clearance_filter = request.GET.get('clearance', '').strip()

        report_data = RealEstateReportingService.get_dual_subledger_report(
            project_id=int(project_id) if project_id.isdigit() else None,
            customer_id=int(customer_id) if customer_id.isdigit() else None,
            status=status_filter or None,
            clearance_filter=clearance_filter or None,
            search_query=search_query,
        )

        paginator = Paginator(report_data['rows'], 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        customers = Customer.objects.filter(property_contracts__isnull=False).distinct().order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('كشف الحساب المزدوج (تعاقدي / مالي)'), 'active': True},
        ]

        context = {
            **report_data,
            'page_obj': page_obj,
            'contract_rows': page_obj.object_list,
            'projects': projects,
            'customers': customers,
            'status_choices': PropertyContract.ContractStatus.choices,
            'search_query': search_query,
            'selected_project': project_id,
            'selected_customer': customer_id,
            'selected_status': status_filter,
            'selected_clearance': clearance_filter,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_dual_subledger',
        }
        return render(request, 'real_estate/reports/dual_subledger_report.html', context)


class CashFlowLiquidityReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    رادار التدفقات النقدية العقارية ومطابقة السيولة الشهرية
    """
    permission_required = 'real_estate.view_propertycontract'

    def get(self, request):
        project_id = request.GET.get('project', '').strip()
        date_from_str = request.GET.get('date_from', '').strip()
        date_to_str = request.GET.get('date_to', '').strip()

        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        report_data = RealEstateReportingService.get_cash_flow_liquidity_report(
            project_id=int(project_id) if project_id.isdigit() else None,
            date_from=date_from,
            date_to=date_to,
        )

        paginator = Paginator(report_data['installment_rows'], 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('رادار التدفقات النقدية والسيولة'), 'active': True},
        ]

        context = {
            **report_data,
            'page_obj': page_obj,
            'installments_page': page_obj.object_list,
            'projects': projects,
            'selected_project': project_id,
            'date_from': date_from_str,
            'date_to': date_to_str,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_cash_flow',
        }
        return render(request, 'real_estate/reports/cash_flow_report.html', context)


class ProjectWIPRevenueReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير تكلفة المشروعات تحت التنفيذ (WIP Costing) والاعتراف بالإيراد وفق معيار IFRS 15
    """
    permission_required = 'real_estate.view_realestateproject'

    def get(self, request):
        project_id = request.GET.get('project', '').strip()
        status_filter = request.GET.get('status', '').strip()

        report_data = RealEstateReportingService.get_project_wip_revenue_report(
            project_id=int(project_id) if project_id.isdigit() else None,
            status=status_filter or None,
        )

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('تكاليف المشروعات وإيرادات IFRS 15'), 'active': True},
        ]

        context = {
            **report_data,
            'projects': projects,
            'status_choices': RealEstateProject.ProjectStatus.choices,
            'selected_project': project_id,
            'selected_status': status_filter,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_wip_revenue',
        }
        return render(request, 'real_estate/reports/wip_revenue_report.html', context)


class BrokerCommissionReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير أداء الوسطاء العقاريين واستحقاقات العمولات المرحلية
    """
    permission_required = 'real_estate.view_brokercommission'

    def get(self, request):
        broker_id = request.GET.get('broker', '').strip()
        project_id = request.GET.get('project', '').strip()
        tranche_status = request.GET.get('tranche_status', '').strip()

        report_data = RealEstateReportingService.get_broker_commission_report(
            broker_id=int(broker_id) if broker_id.isdigit() else None,
            project_id=int(project_id) if project_id.isdigit() else None,
            tranche_status=tranche_status or None,
        )

        brokers = RealEstateBroker.objects.filter(is_active=True).order_by('name')
        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('تقرير أداء الوسطاء والعمولات'), 'active': True},
        ]

        context = {
            **report_data,
            'brokers': brokers,
            'projects': projects,
            'tranche_status_choices': BrokerCommission.TrancheStatus.choices,
            'selected_broker': broker_id,
            'selected_project': project_id,
            'selected_tranche_status': tranche_status,
            'breadcrumb_items': breadcrumb_items,
            'active_menu': 're_reports',
            'active_submenu': 'report_broker_commissions',
        }
        return render(request, 'real_estate/reports/broker_commission_report.html', context)


class TowerSalesBriefReportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تقرير الموقف التنفيذي ومصفوفة مبيعات الأبراج (Tower Sales Brief Report)
    """
    permission_required = 'real_estate.view_executive_reports'
    raise_exception = True

    def has_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_admin', False):
            return True
        return user.has_perm('real_estate.view_executive_reports')

    def get(self, request):
        project_id = request.GET.get('project', '').strip()
        block_id = request.GET.get('block', '').strip()

        p_id = int(project_id) if project_id.isdigit() else None
        b_id = int(block_id) if block_id.isdigit() else None

        report_data = RealEstateReportingService.get_tower_sales_brief_report(
            block_id=b_id,
            project_id=p_id,
        )

        projects = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        blocks_qs = PropertyBlock.objects.select_related('project').all()
        if p_id:
            blocks_qs = blocks_qs.filter(project_id=p_id)
        blocks = blocks_qs.order_by('project__name', 'name')

        paginator = Paginator(report_data['unit_rows'], 50)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        export_url = reverse('real_estate:report_tower_sales_brief_export')
        print_url = reverse('real_estate:report_tower_sales_brief_print')
        query_params = []
        if p_id:
            query_params.append(f"project={p_id}")
        if b_id:
            query_params.append(f"block={b_id}")
        if query_params:
            export_url += "?" + "&".join(query_params)
            print_url += "?" + "&".join(query_params)

        header_buttons = [
            {
                'url': print_url,
                'label': _('طباعة الموقف التنفيذي'),
                'icon': 'fa-print',
                'class': 'btn-outline-primary',
                'target': '_blank'
            },
            {
                'url': export_url,
                'label': _('تصدير إكسيل'),
                'icon': 'fa-file-excel',
                'class': 'btn-success',
            }
        ]

        breadcrumb_items = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _('التقارير العقارية'), 'url': reverse('real_estate:report_dual_subledger'), 'icon': 'fa-chart-line'},
            {'title': _('الموقف التنفيذي ومبيعات الأبراج'), 'active': True},
        ]

        context = {
            **report_data,
            'page_obj': page_obj,
            'units_page': page_obj.object_list,
            'projects': projects,
            'blocks': blocks,
            'selected_project': project_id,
            'selected_block': block_id,
            'breadcrumb_items': breadcrumb_items,
            'header_buttons': header_buttons,
            'active_menu': 're_reports',
            'active_submenu': 'report_tower_sales_brief',
        }
        return render(request, 'real_estate/reports/tower_sales_brief.html', context)


class TowerSalesBriefPrintView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    نسخة الطباعة الرسمية لتقرير الموقف التنفيذي ومبيعات الأبراج
    """
    permission_required = 'real_estate.view_executive_reports'
    raise_exception = True

    def has_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_admin', False):
            return True
        return user.has_perm('real_estate.view_executive_reports')

    def get(self, request):
        project_id = request.GET.get('project', '').strip()
        block_id = request.GET.get('block', '').strip()

        p_id = int(project_id) if project_id.isdigit() else None
        b_id = int(block_id) if block_id.isdigit() else None

        report_data = RealEstateReportingService.get_tower_sales_brief_report(
            block_id=b_id,
            project_id=p_id,
        )

        context = {
            **report_data,
            'today': timezone.localdate(),
            'generated_by': request.user,
        }
        return render(request, 'real_estate/reports/tower_sales_brief_print.html', context)


class TowerSalesBriefExportView(LoginRequiredMixin, SmartPermissionRequiredMixin, View):
    """
    تصدير تقرير الموقف التنفيذي ومبيعات الأبراج إلى ملف إكسيل معتمد (openpyxl)
    مع الالتزام بالمعايير الحوكمية:
    - اتجاه RTL إجباري (rightToLeft = True).
    - الترويسة المؤسسية والبيانات الميدانية.
    - الأقسام الثلاثة: 1. الملخص الإنشائي والمخزون، 2. المحفظة المالية والعملات الأجنبية، 3. مصفوفة Closer وفريق البيع، 4. جرد الوحدات.
    """
    permission_required = 'real_estate.view_executive_reports'
    raise_exception = True

    def has_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_admin', False):
            return True
        return user.has_perm('real_estate.view_executive_reports')

    def get(self, request):
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from django.http import HttpResponse

        project_id = request.GET.get('project', '').strip()
        block_id = request.GET.get('block', '').strip()

        p_id = int(project_id) if project_id.isdigit() else None
        b_id = int(block_id) if block_id.isdigit() else None

        data = RealEstateReportingService.get_tower_sales_brief_report(
            block_id=b_id,
            project_id=p_id,
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tower_Sales_Brief"
        ws.views.sheetView[0].rightToLeft = True

        title_font = Font(name="Calibri", size=15, bold=True, color="1F2937")
        section_font = Font(name="Calibri", size=12, bold=True, color="111827")
        header_font = Font(name="Calibri", size=11, bold=True, color="1F2937")
        bold_font = Font(name="Calibri", size=10, bold=True)
        regular_font = Font(name="Calibri", size=10)

        header_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")

        center_align = Alignment(horizontal="center", vertical="center")
        right_align = Alignment(horizontal="right", vertical="center")

        thin_side = Side(style='thin', color='D1D5DB')
        thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        target_name = (
            f"برج: {data['target_block'].name} ({data['target_project'].name})"
            if data['target_block']
            else f"مشروع: {data['target_project'].name}"
            if data['target_project']
            else "محفظة المشروعات والأبراج العامة"
        )
        ws.merge_cells('A1:G1')
        ws['A1'] = f"تقرير الموقف التنفيذي ومبيعات الأبراج — {target_name}"
        ws['A1'].font = title_font
        ws['A1'].alignment = right_align

        ws['A2'] = f"تاريخ الاستخراج: {timezone.localdate().strftime('%Y-%m-%d')} | نسبة الإنجاز الإنشائي: {data['construction_progress']}%"
        ws['A2'].font = regular_font

        # 1. المخزون العقاري
        ws.cell(row=4, column=1, value="أولاً: الملخص التنفيذي وحركة استيعاب المخزون العقاري").font = section_font
        sec1_headers = ["إجمالي الوحدات", "المساحة الإجمالية (م²)", "الوحدات المباعة/التعاقدية", "نسبة الاستيعاب", "الوحدات المحجوزة", "نسبة الحجز", "الوحدات المتاحة", "نسبة المتاح"]
        ws.append([])
        ws.append(sec1_headers)
        for col_idx in range(1, len(sec1_headers) + 1):
            cell = ws.cell(row=6, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        sec1_row = [
            data['total_units_count'],
            float(data['total_units_area']),
            data['contracted_count'],
            f"{data['absorption_rate']}%",
            data['reserved_count'],
            f"{data['reservation_rate']}%",
            data['available_count'],
            f"{data['available_rate']}%",
        ]
        ws.append(sec1_row)
        for col_idx in range(1, len(sec1_row) + 1):
            cell = ws.cell(row=7, column=col_idx)
            cell.font = regular_font
            cell.alignment = center_align
            cell.border = thin_border

        # 2. الموقف المالي
        curr_row = 9
        ws.cell(row=curr_row, column=1, value=f"ثانياً: الموقف المالي والمحصلات بالعملة الوظيفية ({data['func_currency_code']})").font = section_font
        curr_row += 1
        sec2_headers = ["إجمالي المبيعات التعاقدية", "مقدمات الحجز والتعاقد", "أقساط محصلة فعلياً", "إجمالي السيولة المحصلة", "شيكات بالحافظة والتحصيل", "المتبقي للتحصيل", "كفاءة التحصيل"]
        for col_idx, h in enumerate(sec2_headers, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        curr_row += 1
        sec2_vals = [
            float(data['total_contracted_sales_func']),
            float(data['total_down_payments_collected_func'] + data['total_active_holding_deposits_func']),
            float(data['total_installments_collected_func']),
            float(data['total_collected_liquidity_func']),
            float(data['total_cheques_in_vault_func']),
            float(data['total_remaining_receivables_func']),
            f"{data['collection_efficiency_rate']}%",
        ]
        for col_idx, v in enumerate(sec2_vals, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=v)
            cell.font = bold_font
            cell.alignment = center_align
            cell.border = thin_border
            if isinstance(v, float):
                cell.number_format = '#,##0.00'

        # العملات الأجنبية إن وجدت
        if data['foreign_currencies']:
            curr_row += 2
            ws.cell(row=curr_row, column=1, value="جدول العملات الأجنبية المعزولة").font = section_font
            curr_row += 1
            fc_headers = ["العملة", "سعر الصرف", "العقود", "الحجوزات", "إجمالي المبيعات الأجنبية", "المحصل الأجنبي", "المتبقي الأجنبي", "المعادل الوظيفي"]
            for col_idx, h in enumerate(fc_headers, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center_align
                cell.border = thin_border

            for fc in data['foreign_currencies']:
                curr_row += 1
                fc_vals = [
                    f"{fc['currency_name']} ({fc['currency_code']})",
                    float(fc['exchange_rate']),
                    fc['contracts_count'],
                    fc['bookings_count'],
                    float(fc['foreign_contracted_amount']),
                    float(fc['foreign_collected_amount']),
                    float(fc['foreign_remaining_amount']),
                    float(fc['functional_equivalent_sales']),
                ]
                for col_idx, v in enumerate(fc_vals, start=1):
                    cell = ws.cell(row=curr_row, column=col_idx, value=v)
                    cell.font = regular_font
                    cell.alignment = center_align
                    cell.border = thin_border
                    if isinstance(v, float):
                        cell.number_format = '#,##0.00'

        # 3. مصفوفة Closer وفريق البيع
        curr_row += 2
        ws.cell(row=curr_row, column=1, value="ثالثاً: مصفوفة إغلاق صفقات فريق البيع (Closer Matrix)").font = section_font
        curr_row += 1
        closer_headers = ["مسئول البيع / Closer", "عدد العقود", "حجوزات نشطة", "حجم المبيعات (ج.م)", "المحصل الفعلي (ج.م)", "متوسط قيمة الصفقة", "نسبة المساهمة"]
        for col_idx, h in enumerate(closer_headers, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        for closer in data['closer_matrix']:
            curr_row += 1
            c_vals = [
                closer['name'],
                closer['contracts_count'],
                closer['active_bookings_count'],
                float(closer['total_sales_volume']),
                float(closer['total_collected']),
                float(closer['avg_deal_size']),
                f"{closer['contribution_percentage']}%",
            ]
            for col_idx, v in enumerate(c_vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=v)
                cell.font = regular_font
                cell.alignment = center_align
                cell.border = thin_border
                if isinstance(v, float):
                    cell.number_format = '#,##0.00'

        # 4. مصفوفة جرد الوحدات
        curr_row += 2
        ws.cell(row=curr_row, column=1, value="رابعاً: سجل جرد وموقف الوحدات التفصيلي").font = section_font
        curr_row += 1
        unit_headers = ["كود الوحدة", "العمارة / البرج", "الدور", "النوع", "المساحة الإجمالية", "الحالة الحالية", "العميل", "رقم العقد / الحجز", "القيمة", "المسئول"]
        for col_idx, h in enumerate(unit_headers, start=1):
            cell = ws.cell(row=curr_row, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border

        for u in data['unit_rows']:
            curr_row += 1
            u_vals = [
                u['unit_code'],
                u['block_name'],
                u['floor_name'],
                u['unit_type'],
                float(u['gross_area']),
                u['status_display'],
                u['customer_name'],
                u['doc_number'],
                float(u['deal_value']),
                u['closer_name'],
            ]
            for col_idx, v in enumerate(u_vals, start=1):
                cell = ws.cell(row=curr_row, column=col_idx, value=v)
                cell.font = regular_font
                cell.alignment = center_align
                cell.border = thin_border
                if isinstance(v, float):
                    cell.number_format = '#,##0.00'

        for col in ws.columns:
            max_len = 0
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

        target_slug = data['target_block'].code if data['target_block'] else (data['target_project'].code if data['target_project'] else "portfolio")
        filename = f"Tower_Sales_Brief_{target_slug}_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
