# -*- coding: utf-8 -*-
"""
FIN-CORE-025: Cash Transfer Endpoints and Views
واجهات برمجة التطبيقات والمناظر لسندات التحويل المالي المركزية بين الخزن والبنوك والعهد
"""
import json
import logging
from decimal import Decimal
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _

from financial.models.cash_transfer import CashTransfer, TransferType, TransferStatus
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency
from financial.services.cash_transfer_service import CashTransferService
from financial.services.treasury_security_service import TreasurySecurityService

logger = logging.getLogger("financial.views.cash_transfer_views")


@login_required
@require_http_methods(["GET", "POST"])
def transfer_preview_api(request):
    """
    API endpoint لمعاينة ومحاكاة التحويل المالي المباشر والمتعدد العملات في الوقت الفعلي
    """
    try:
        data = request.POST if request.method == "POST" else request.GET

        from_account_id = data.get("from_account") or data.get("from_account_id")
        to_account_id = data.get("to_account") or data.get("to_account_id")
        source_amount_raw = data.get("amount") or data.get("source_amount")
        exchange_rate_raw = data.get("exchange_rate") or data.get("custom_exchange_rate")
        bank_fee_raw = data.get("bank_fee") or data.get("transfer_fee", "0")
        vat_on_fee_raw = data.get("vat_on_fee") or data.get("fee_vat_amount", "0")
        transfer_type = data.get("transfer_type", TransferType.DIRECT)
        transfer_date_str = data.get("transfer_date")

        if not from_account_id or not to_account_id:
            return JsonResponse({
                "success": False,
                "error": "يجب تحديد الخزينة / الحساب المصدر والحساب المستلم للمعاينة."
            }, status=400)

        if str(from_account_id) == str(to_account_id):
            return JsonResponse({
                "success": False,
                "error": "لا يمكن التحويل لنفس الحساب المصدر."
            }, status=400)

        try:
            source_amount = Decimal(str(source_amount_raw or 0))
            if source_amount <= Decimal("0.00"):
                return JsonResponse({
                    "success": False,
                    "error": "مبلغ التحويل يجب أن يكون أكبر من صفر."
                }, status=400)
        except (ValueError, TypeError):
            return JsonResponse({
                "success": False,
                "error": "صيغة المبلغ غير صحيحة."
            }, status=400)

        exchange_rate = None
        if exchange_rate_raw:
            try:
                rate_val = Decimal(str(exchange_rate_raw))
                if rate_val > Decimal("0.00"):
                    exchange_rate = rate_val
            except (ValueError, TypeError):
                pass

        try:
            bank_fee = Decimal(str(bank_fee_raw or 0))
        except (ValueError, TypeError):
            bank_fee = Decimal("0.00")

        try:
            vat_on_fee = Decimal(str(vat_on_fee_raw or 0))
        except (ValueError, TypeError):
            vat_on_fee = Decimal("0.00")

        transfer_date = None
        if transfer_date_str:
            try:
                transfer_date = datetime.strptime(transfer_date_str, "%Y-%m-%d").date()
            except ValueError:
                transfer_date = timezone.now().date()

        preview = CashTransferService.calculate_transfer_preview(
            from_account=int(from_account_id),
            to_account=int(to_account_id),
            source_amount=source_amount,
            exchange_rate=exchange_rate,
            bank_fee=bank_fee,
            vat_on_fee=vat_on_fee,
            transfer_type=transfer_type,
            transfer_date=transfer_date
        )

        return JsonResponse({
            "success": True,
            "preview": {
                "source_amount": float(preview["source_amount"]),
                "source_currency": preview["source_currency"],
                "source_rate": float(preview["source_rate"]),
                "source_base_amount": float(preview["source_base_amount"]),
                "destination_amount": float(preview["destination_amount"]),
                "destination_currency": preview["destination_currency"],
                "destination_rate": float(preview["destination_rate"]),
                "dest_base_amount": float(preview["dest_base_amount"]),
                "effective_exchange_rate": float(preview["effective_exchange_rate"]),
                "fx_gain_loss": float(preview["fx_gain_loss"]),
                "fx_type": preview["fx_type"],
                "penny_difference": float(preview["penny_difference"]),
                "bank_fee": float(preview["bank_fee"]),
                "vat_on_fee": float(preview["vat_on_fee"]),
                "total_fee": float(preview["total_fee"]),
                "total_source_deduction": float(preview["total_source_deduction"]),
                "amount_in_words": preview["amount_in_words"],
                "simulated_lines": [
                    {
                        "account_code": line["account_code"],
                        "account_name": line["account_name"],
                        "debit": float(line["debit"]),
                        "credit": float(line["credit"]),
                        "currency": line["currency"],
                        "description": line["description"]
                    }
                    for line in preview["simulated_lines"]
                ]
            }
        })

    except ValidationError as e:
        msg = e.messages[0] if hasattr(e, "messages") else str(e)
        return JsonResponse({"success": False, "error": msg}, status=400)
    except Exception as e:
        logger.error(f"Error in transfer_preview_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def transfer_create_api(request):
    """
    API endpoint لتسجيل سند تحويل مالي جديد (مباشر أو مرحلي)
    """
    try:
        from_account_id = request.POST.get("from_account") or request.POST.get("from_account_id")
        to_account_id = request.POST.get("to_account") or request.POST.get("to_account_id")
        source_amount_raw = request.POST.get("amount") or request.POST.get("source_amount")
        transfer_type = request.POST.get("transfer_type", TransferType.DIRECT)
        transfer_date_str = request.POST.get("transfer_date")
        exchange_rate_raw = request.POST.get("exchange_rate") or request.POST.get("custom_exchange_rate")
        
        bank_fee_raw = request.POST.get("bank_fee") or request.POST.get("transfer_fee", "0")
        is_fee_vat_inclusive = request.POST.get("is_fee_vat_inclusive") in ["true", "True", "1", True]
        fee_vat_amount_raw = request.POST.get("vat_on_fee") or request.POST.get("fee_vat_amount")
        
        bank_name = request.POST.get("bank_name", "").strip()
        account_number = request.POST.get("account_number", "").strip()
        iban = request.POST.get("iban", "").strip()
        swift_code = request.POST.get("swift_code", "").strip()
        bank_reference = request.POST.get("bank_reference", "").strip()
        bank_slip_attachment = request.FILES.get("bank_slip_attachment")

        courier_name = request.POST.get("courier_name", "").strip()
        courier_id_number = request.POST.get("courier_id_number", "").strip()
        courier_phone = request.POST.get("courier_phone", "").strip()

        from_work_location_id = request.POST.get("from_work_location_id") or request.POST.get("from_work_location")
        to_work_location_id = request.POST.get("to_work_location_id") or request.POST.get("to_work_location")
        from_cost_center_id = request.POST.get("from_cost_center_id")
        to_cost_center_id = request.POST.get("to_cost_center_id")
        fee_cost_center_id = request.POST.get("fee_cost_center_id")
        financial_category_id = request.POST.get("financial_category_id")
        notes = request.POST.get("notes") or request.POST.get("description", "").strip()

        # قراءة فئات النقدية إن وجدت
        denominations_raw = request.POST.get("denominations_breakdown")
        denominations_breakdown = {}
        if denominations_raw:
            try:
                if isinstance(denominations_raw, str):
                    denominations_breakdown = json.loads(denominations_raw)
                elif isinstance(denominations_raw, dict):
                    denominations_breakdown = denominations_raw
            except Exception:
                pass

        if not from_account_id or not to_account_id:
            return JsonResponse({"success": False, "error": "يجب اختيار الخزينة المحول منها والخزينة المستلمة."}, status=400)
        if str(from_account_id) == str(to_account_id):
            return JsonResponse({"success": False, "error": "لا يمكن التحويل لنفس الحساب المصدر."}, status=400)
        if not source_amount_raw:
            return JsonResponse({"success": False, "error": "مبلغ التحويل مطلوب."}, status=400)

        try:
            source_amount = Decimal(str(source_amount_raw))
            if source_amount <= Decimal("0.00"):
                return JsonResponse({"success": False, "error": "مبلغ التحويل يجب أن يكون أكبر من صفر."}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "صيغة المبلغ غير صحيحة."}, status=400)

        transfer_date = None
        if transfer_date_str:
            try:
                transfer_date = datetime.strptime(transfer_date_str, "%Y-%m-%d").date()
            except ValueError:
                transfer_date = timezone.now().date()
        else:
            transfer_date = timezone.now().date()

        exchange_rate = None
        if exchange_rate_raw:
            try:
                r = Decimal(str(exchange_rate_raw))
                if r > Decimal("0.00"):
                    exchange_rate = r
            except (ValueError, TypeError):
                pass

        try:
            bank_fee = Decimal(str(bank_fee_raw or 0))
        except (ValueError, TypeError):
            bank_fee = Decimal("0.00")

        fee_vat_amount = None
        if fee_vat_amount_raw:
            try:
                v = Decimal(str(fee_vat_amount_raw))
                if v >= Decimal("0.00"):
                    fee_vat_amount = v
            except (ValueError, TypeError):
                pass

        transfer = CashTransferService.execute_transfer(
            from_account_id=int(from_account_id),
            to_account_id=int(to_account_id),
            source_amount=source_amount,
            user=request.user,
            transfer_type=transfer_type,
            transfer_date=transfer_date,
            exchange_rate=exchange_rate,
            bank_fee=bank_fee,
            is_fee_vat_inclusive=is_fee_vat_inclusive,
            fee_vat_amount=fee_vat_amount,
            bank_name=bank_name,
            account_number=account_number,
            iban=iban,
            swift_code=swift_code,
            bank_reference=bank_reference,
            bank_slip_attachment=bank_slip_attachment,
            denominations_breakdown=denominations_breakdown,
            courier_name=courier_name,
            courier_id_number=courier_id_number,
            courier_phone=courier_phone,
            from_work_location_id=int(from_work_location_id) if from_work_location_id else None,
            to_work_location_id=int(to_work_location_id) if to_work_location_id else None,
            from_cost_center_id=int(from_cost_center_id) if from_cost_center_id else None,
            to_cost_center_id=int(to_cost_center_id) if to_cost_center_id else None,
            fee_cost_center_id=int(fee_cost_center_id) if fee_cost_center_id else None,
            financial_category_id=int(financial_category_id) if financial_category_id else None,
            notes=notes
        )

        return JsonResponse({
            "success": True,
            "message": f"تم تسجيل سند التحويل المالي {transfer.transfer_number} بنجاح.",
            "transfer_id": transfer.id,
            "transfer_number": transfer.transfer_number,
            "status": transfer.status,
            "status_display": transfer.get_status_display(),
            "journal_entry_id": transfer.journal_entry_id,
            "redirect_url": reverse("financial:cash_transfers_list")
        })

    except ValidationError as e:
        msg = e.messages[0] if hasattr(e, "messages") else str(e)
        return JsonResponse({"success": False, "error": msg}, status=400)
    except Exception as e:
        logger.error(f"Error in transfer_create_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def transfer_between_accounts(request):
    """
    Adapter view متوافق 100% مع المسار القديم /api/transfer-between-accounts/
    يوجه العمليات آلياً لمحرك CashTransferService المركزي
    """
    return transfer_create_api(request)


@login_required
@require_http_methods(["POST"])
def transfer_receive_api(request, pk: int):
    """
    API endpoint لتأكيد استلام نقدية مرحلية في الطريق
    مع تطبيق مبدأ الفصل بين المهام (SoD)
    """
    try:
        receive_date_str = request.POST.get("receive_date")
        received_amount_raw = request.POST.get("received_amount")
        notes = request.POST.get("notes", "").strip()

        receive_date = None
        if receive_date_str:
            try:
                receive_date = datetime.strptime(receive_date_str, "%Y-%m-%d").date()
            except ValueError:
                receive_date = timezone.now().date()

        received_amount = None
        if received_amount_raw:
            try:
                ra = Decimal(str(received_amount_raw))
                if ra > Decimal("0.00"):
                    received_amount = ra
            except (ValueError, TypeError):
                pass

        transfer = CashTransferService.receive_transit_transfer(
            transfer_id=pk,
            user=request.user,
            receive_date=receive_date,
            received_amount=received_amount,
            notes=notes
        )

        return JsonResponse({
            "success": True,
            "message": f"تم تأكيد استلام سند التحويل {transfer.transfer_number} في الخزينة المستلمة بنجاح.",
            "transfer_id": transfer.id,
            "transfer_number": transfer.transfer_number,
            "status": transfer.status,
            "status_display": transfer.get_status_display()
        })

    except ValidationError as e:
        msg = e.messages[0] if hasattr(e, "messages") else str(e)
        return JsonResponse({"success": False, "error": msg}, status=400)
    except Exception as e:
        logger.error(f"Error in transfer_receive_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def transfer_recall_api(request, pk: int):
    """
    API endpoint لاسترجاع / إلغاء سند تحويل مرحلي في الطريق
    """
    try:
        reason = request.POST.get("reason", "").strip()
        transfer = CashTransferService.recall_transit_transfer(
            transfer_id=pk,
            user=request.user,
            reason=reason
        )

        return JsonResponse({
            "success": True,
            "message": f"تم استرجاع وإلغاء سند التحويل {transfer.transfer_number} وإعادة الرصيد للخزينة المصدر بنجاح.",
            "transfer_id": transfer.id,
            "transfer_number": transfer.transfer_number,
            "status": transfer.status,
            "status_display": transfer.get_status_display()
        })

    except ValidationError as e:
        msg = e.messages[0] if hasattr(e, "messages") else str(e)
        return JsonResponse({"success": False, "error": msg}, status=400)
    except Exception as e:
        logger.error(f"Error in transfer_recall_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def transfer_reverse_api(request, pk: int):
    """
    API endpoint لعكس سند تحويل مالي مكتمل محاسبياً
    """
    try:
        reason = request.POST.get("reason", "").strip()
        transfer = CashTransferService.reverse_transfer(
            transfer_id=pk,
            user=request.user,
            reason=reason
        )

        return JsonResponse({
            "success": True,
            "message": f"تم عكس سند التحويل المالي {transfer.transfer_number} وتوليد القيد العكسي بنجاح.",
            "transfer_id": transfer.id,
            "transfer_number": transfer.transfer_number,
            "status": transfer.status,
            "status_display": transfer.get_status_display()
        })

    except ValidationError as e:
        msg = e.messages[0] if hasattr(e, "messages") else str(e)
        return JsonResponse({"success": False, "error": msg}, status=400)
    except Exception as e:
        logger.error(f"Error in transfer_reverse_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def transfer_detail_api(request, pk: int):
    """
    API endpoint لإرجاع بيانات السند التفصيلية للمودال والمعاينة
    """
    try:
        transfer = get_object_or_404(
            CashTransfer.objects.select_related(
                "from_account", "to_account", "transit_account",
                "source_currency", "destination_currency",
                "created_by", "received_by", "reversed_by",
                "journal_entry", "receipt_journal_entry", "reversal_journal_entry"
            ),
            pk=pk
        )

        return JsonResponse({
            "success": True,
            "transfer": {
                "id": transfer.id,
                "transfer_number": transfer.transfer_number,
                "transfer_type": transfer.transfer_type,
                "transfer_type_display": transfer.get_transfer_type_display(),
                "status": transfer.status,
                "status_display": transfer.get_status_display(),
                "transfer_date": transfer.transfer_date.strftime("%Y-%m-%d"),
                "from_account": {
                    "id": transfer.from_account_id,
                    "code": transfer.from_account.code,
                    "name": transfer.from_account.name
                },
                "to_account": {
                    "id": transfer.to_account_id,
                    "code": transfer.to_account.code,
                    "name": transfer.to_account.name
                },
                "source_amount": float(transfer.source_amount),
                "source_currency": transfer.source_currency.code,
                "source_exchange_rate": float(transfer.source_exchange_rate),
                "destination_amount": float(transfer.destination_amount),
                "destination_currency": transfer.destination_currency.code,
                "destination_exchange_rate": float(transfer.destination_exchange_rate),
                "custom_exchange_rate": float(transfer.custom_exchange_rate) if transfer.custom_exchange_rate else None,
                "fx_gain_loss_amount": float(transfer.fx_gain_loss_amount),
                "rounding_difference": float(transfer.rounding_difference),
                "transfer_fee": float(transfer.transfer_fee),
                "fee_vat_amount": float(transfer.fee_vat_amount),
                "bank_name": transfer.bank_name,
                "account_number": transfer.account_number,
                "iban": transfer.iban,
                "swift_code": transfer.swift_code,
                "bank_reference": transfer.bank_reference,
                "amount_in_words": transfer.amount_in_words,
                "denominations_breakdown": transfer.denominations_breakdown,
                "courier_name": transfer.courier_name,
                "courier_phone": transfer.courier_phone,
                "received_amount": float(transfer.received_amount) if transfer.received_amount else None,
                "journal_entry_id": transfer.journal_entry_id,
                "receipt_journal_entry_id": transfer.receipt_journal_entry_id,
                "reversal_journal_entry_id": transfer.reversal_journal_entry_id,
                "created_by": transfer.created_by.get_full_name() or transfer.created_by.username,
                "created_at": transfer.created_at.strftime("%Y-%m-%d %H:%M"),
                "received_by": (transfer.received_by.get_full_name() or transfer.received_by.username) if transfer.received_by else None,
                "received_at": transfer.received_at.strftime("%Y-%m-%d %H:%M") if transfer.received_at else None,
                "verification_hash": transfer.verification_hash,
                "notes": transfer.notes
            }
        })

    except Exception as e:
        logger.error(f"Error in transfer_detail_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def cash_transfers_list_view(request):
    """
    عرض قائمة وسجل سندات التحويل المالي (المرحلة 6) مع الفلاتر والإحصائيات والبحث التفاعلي AJAX
    """
    from django.core.paginator import Paginator
    from django.db.models import Q, Sum
    from django.template.loader import render_to_string
    base_currency = Currency.objects.filter(is_functional=True).first()
    base_currency_symbol = base_currency.symbol if base_currency else "ج.م"

    qs_all = CashTransfer.objects.all()
    total_count = qs_all.count()
    in_transit_count = qs_all.filter(status=TransferStatus.IN_TRANSIT).count()
    completed_count = qs_all.filter(status=TransferStatus.COMPLETED).count()
    cancelled_count = qs_all.filter(status__in=[TransferStatus.RECALLED, TransferStatus.REVERSED, TransferStatus.REJECTED]).count()
    total_volume = qs_all.aggregate(total=Sum("source_amount"))["total"] or Decimal("0.00")

    qs = CashTransfer.objects.select_related(
        "from_account", "to_account", "source_currency", "destination_currency", "created_by", "received_by"
    ).order_by("-transfer_date", "-id")

    # Filters
    search_q = request.GET.get("q", "").strip()
    if search_q:
        qs = qs.filter(
            Q(transfer_number__icontains=search_q)
            | Q(from_account__name__icontains=search_q)
            | Q(from_account__code__icontains=search_q)
            | Q(to_account__name__icontains=search_q)
            | Q(to_account__code__icontains=search_q)
            | Q(bank_reference__icontains=search_q)
            | Q(courier_name__icontains=search_q)
            | Q(notes__icontains=search_q)
        )

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    transfer_type_filter = request.GET.get("transfer_type", "").strip()
    if transfer_type_filter:
        qs = qs.filter(transfer_type=transfer_type_filter)

    from_account_filter = request.GET.get("from_account", "").strip()
    if from_account_filter:
        qs = qs.filter(from_account_id=from_account_filter)

    to_account_filter = request.GET.get("to_account", "").strip()
    if to_account_filter:
        qs = qs.filter(to_account_id=to_account_filter)

    from_date = request.GET.get("from_date", "").strip()
    to_date = request.GET.get("to_date", "").strip()
    if from_date:
        qs = qs.filter(transfer_date__gte=from_date)
    if to_date:
        qs = qs.filter(transfer_date__lte=to_date)

    # Excel Export
    if request.GET.get("export") == "excel":
        from utils.export import export_queryset_to_excel

        return export_queryset_to_excel(
            qs,
            filename="cash_transfers_report.xlsx",
            fields=["transfer_number", "transfer_date", "transfer_type", "from_acc", "to_acc", "amount", "currency", "status", "created_by"],
            headers=["رقم السند", "تاريخ التحويل", "نوع التحويل", "من حساب", "إلى حساب", "المبلغ", "العملة", "الحالة", "المسؤول"],
            annotations={
                "transfer_number": lambda t: t.transfer_number,
                "transfer_date": lambda t: t.transfer_date.strftime("%Y-%m-%d"),
                "transfer_type": lambda t: t.get_transfer_type_display(),
                "from_acc": lambda t: f"{t.from_account.name} ({t.from_account.code})",
                "to_acc": lambda t: f"{t.to_account.name} ({t.to_account.code})",
                "amount": lambda t: float(t.source_amount),
                "currency": lambda t: t.source_currency.code if t.source_currency else "",
                "status": lambda t: t.get_status_display(),
                "created_by": lambda t: t.created_by.get_full_name() or t.created_by.username if t.created_by else "",
            }
        )

    per_page = request.GET.get("per_page", 25)
    try:
        per_page = int(per_page)
    except (ValueError, TypeError):
        per_page = 25

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    accessible_accounts = TreasurySecurityService.get_user_accessible_treasuries(request.user, action="any")

    context = {
        "transfers": page_obj,
        "page_obj": page_obj,
        "accounts": accessible_accounts,
        "transfer_types": TransferType.choices,
        "transfer_statuses": TransferStatus.choices,
        "total_count": total_count,
        "in_transit_count": in_transit_count,
        "completed_count": completed_count,
        "cancelled_count": cancelled_count,
        "total_volume": total_volume,
        "base_currency_symbol": base_currency_symbol,
        "page_title": _("سندات التحويل المالي بين الخزن والبنوك"),
        "page_subtitle": _("سجل وتدقيق التحويلات النقدية والبنكية والمرحلية في الطريق"),
        "page_icon": "fas fa-exchange-alt",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            {"title": _("الإدارة المالية"), "url": reverse("financial:chart_of_accounts_list"), "icon": "fa-calculator"},
            {"title": _("الخزن والحسابات البنكية"), "url": reverse("financial:cash_and_bank_accounts_list"), "icon": "fa-vault"},
            {"title": _("سندات التحويل المالي"), "active": True}
        ],
        "header_buttons": [
            {
                "url": reverse("financial:cash_and_bank_accounts_list"),
                "icon": "fas fa-vault",
                "text": _("دليل الخزن والبنوك"),
                "class": "btn-outline-secondary me-2",
            },
            {
                "onclick": "openSmartTransferModalFor('')",
                "icon": "fas fa-plus",
                "text": _("سند تحويل جديد"),
                "class": "btn-primary",
            }
        ]
    }

    # Handle AJAX Requests
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("ajax") == "1":
        table_html = render_to_string(
            "financial/banking/partials/transfers_table.html",
            {"transfers": page_obj, "page_obj": page_obj, "base_currency_symbol": base_currency_symbol},
            request=request
        )
        pagination_html = render_to_string(
            "partials/pagination.html",
            {"page_obj": page_obj},
            request=request
        )
        return JsonResponse({
            "success": True,
            "table_html": table_html,
            "pagination_html": pagination_html,
            "total_count": paginator.count
        })

    return render(request, "financial/banking/transfer_list.html", context)


@login_required
def cash_transfer_create_view(request):
    """
    عرض صفحة / نموذج إنشاء سند تحويل مالي
    """
    if request.method == "POST":
        return transfer_create_api(request)

    accessible_accounts = TreasurySecurityService.get_user_accessible_treasuries(request.user, action="any")
    context = {
        "accounts": accessible_accounts,
        "transfer_types": TransferType.choices,
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            {"title": _("الإدارة المالية"), "url": reverse("financial:chart_of_accounts_list"), "icon": "fa-calculator"},
            {"title": _("سندات التحويل المالي"), "url": reverse("financial:cash_transfers_list"), "icon": "fa-exchange-alt"},
            {"title": _("إنشاء سند تحويل"), "active": True}
        ]
    }
    return render(request, "financial/banking/transfer_create.html", context)


@login_required
def cash_transfer_detail_view(request, pk: int):
    """
    عرض صفحة تفاصيل سند تحويل مالي وسجل القيود المحاسبية وتتبع النقل
    """
    transfer = get_object_or_404(
        CashTransfer.objects.select_related(
            "from_account", "to_account", "transit_account",
            "source_currency", "destination_currency",
            "created_by", "received_by", "reversed_by",
            "from_work_location", "to_work_location",
            "from_cost_center", "to_cost_center",
            "journal_entry", "receipt_journal_entry", "reversal_journal_entry"
        ).prefetch_related(
            "journal_entry__lines__account",
            "receipt_journal_entry__lines__account",
            "reversal_journal_entry__lines__account"
        ),
        pk=pk
    )
    base_currency = Currency.objects.filter(is_functional=True).first()
    base_currency_symbol = base_currency.symbol if base_currency else "ج.م"

    header_buttons = [
        {
            "url": reverse("financial:cash_transfers_list"),
            "icon": "fas fa-arrow-right",
            "text": _("سجل التحويلات"),
            "class": "btn-outline-secondary me-2",
        },
        {
            "url": f"{reverse('financial:cash_transfer_print', kwargs={'pk': transfer.id})}?format=a4",
            "icon": "fas fa-print",
            "text": _("طباعة A4"),
            "class": "btn-outline-primary me-2",
            "target": "_blank",
        },
        {
            "url": f"{reverse('financial:cash_transfer_print', kwargs={'pk': transfer.id})}?format=thermal",
            "icon": "fas fa-receipt",
            "text": _("طباعة إيصال حراري (80mm)"),
            "class": "btn-outline-dark me-2",
            "target": "_blank",
        }
    ]

    context = {
        "transfer": transfer,
        "base_currency_symbol": base_currency_symbol,
        "page_title": f"{_('سند تحويل مالي')} #{transfer.transfer_number}",
        "page_subtitle": f"{transfer.get_transfer_type_display()} - {transfer.get_status_display()}",
        "page_icon": "fas fa-file-invoice-dollar",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            {"title": _("الإدارة المالية"), "url": reverse("financial:chart_of_accounts_list"), "icon": "fa-calculator"},
            {"title": _("سندات التحويل المالي"), "url": reverse("financial:cash_transfers_list"), "icon": "fa-exchange-alt"},
            {"title": transfer.transfer_number, "active": True}
        ],
        "header_buttons": header_buttons
    }
    return render(request, "financial/banking/transfer_detail.html", context)


@login_required
def transfer_voucher_print_view(request, pk: int):
    """
    عرض وطباعة سند التحويل المالي (A4 و 80mm POS Slip)
    """
    transfer = get_object_or_404(
        CashTransfer.objects.select_related(
            "from_account", "to_account", "transit_account",
            "source_currency", "destination_currency",
            "created_by", "received_by", "reversed_by",
            "journal_entry"
        ).prefetch_related(
            "journal_entry__lines__account"
        ),
        pk=pk
    )
    print_format = request.GET.get("format", "a4").lower()
    base_currency = Currency.objects.filter(is_functional=True).first()

    context = {
        "transfer": transfer,
        "print_format": print_format,
        "printed_at": timezone.now(),
        "printed_by": request.user,
        "base_currency": base_currency,
        "base_currency_symbol": base_currency.symbol if base_currency else "ج.م",
        "journal_lines": transfer.journal_entry.lines.all() if transfer.journal_entry else []
    }
    return render(request, "financial/banking/transfer_voucher_print.html", context)


