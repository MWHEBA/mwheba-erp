from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator

from financial.models.tax import TaxCode, TaxJurisdiction, TaxDeterminationAudit


@login_required
def tax_code_list(request):
    """عرض السجل والرموز الضريبية"""
    tax_codes = TaxCode.objects.all().order_by('code')
    paginator = Paginator(tax_codes, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'financial/tax_code_list.html', {
        'page_obj': page_obj,
        'tax_codes': page_obj.object_list,
        'page_title': _("أكواد وضرائب المخرجات والمدخلات"),
        'page_subtitle': _("إدارة الأكواد الضريبية المعرفات والضرائب المحوكمة"),
        'page_icon': "fas fa-percent",
    })
