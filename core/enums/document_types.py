# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Document Types Enum
Defines central enterprise document type choices for the sequence engine.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentType(models.TextChoices):
    # Financial Core Documents
    JOURNAL_ENTRY = "JOURNAL_ENTRY", _("قيد يومية عامة")
    ADJUSTMENT_JOURNAL = "ADJUSTMENT_JOURNAL", _("قيد تسوية")
    REVERSAL_JOURNAL = "REVERSAL_JOURNAL", _("قيد عكسي")
    SALES_INVOICE = "SALES_INVOICE", _("فاتورة مبيعات")
    CREDIT_NOTE = "CREDIT_NOTE", _("إشعار دائن (مبيعات)")
    PURCHASE_INVOICE = "PURCHASE_INVOICE", _("فاتورة مشتريات")
    DEBIT_NOTE = "DEBIT_NOTE", _("إشعار مدين (مشتريات)")
    CUSTOMER_RECEIPT = "CUSTOMER_RECEIPT", _("سند مقبوضات عميل")
    VENDOR_PAYMENT = "VENDOR_PAYMENT", _("سند مدفوعات مورد")
    FIXED_ASSET_ENTRY = "FIXED_ASSET_ENTRY", _("قيد أصول ثابتة")
    OPENING_BALANCE = "OPENING_BALANCE", _("دفعة أرصدة افتتاحية")
    BANK_RECONCILIATION = "BANK_RECONCILIATION", _("دفعة تسوية بنكية")

    # Inventory & Operations Documents
    DELIVERY_NOTE = "DELIVERY_NOTE", _("إذن تسليم وشحن")
    GOODS_RECEIPT_NOTE = "GOODS_RECEIPT_NOTE", _("إذن استلام مشتريات")
    PURCHASE_ORDER = "PURCHASE_ORDER", _("أمر شراء")
    SALES_ORDER = "SALES_ORDER", _("أمر مبيعات")
    STOCK_RECEIPT = "STOCK_RECEIPT", _("إذن استلام مخزني")
    STOCK_ISSUE = "STOCK_ISSUE", _("إذن صرف مخزني")
    STOCK_TRANSFER = "STOCK_TRANSFER", _("إذن تحويل مخزني")
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT", _("تسوية مخزنية")
    WORK_ORDER = "WORK_ORDER", _("أمر شغل")
    PRINTING_REQUEST = "PRINTING_REQUEST", _("طلب تسعير مطبوعات")

    # Custody & Route Settlement Documents
    CUSTODY_ADVANCE = "CUSTODY_ADVANCE", _("سند صرف عهدة مؤقتة")
    CUSTODY_SETTLEMENT = "CUSTODY_SETTLEMENT", _("سند تسوية عهدة")
    CUSTODY_TRANSFER = "CUSTODY_TRANSFER", _("سند تحويل ومناقلة عهدة")
    CUSTODY_COUNT = "CUSTODY_COUNT", _("محضر جرد عهدة نقدية")
    CUSTODY_ASSET_RECEIPT = "CUSTODY_ASSET_RECEIPT", _("إقرار استلام عهدة عينية")
    CUSTODY_ASSET_TRANSFER = "CUSTODY_ASSET_TRANSFER", _("محضر مناقلة عهدة عينية")
    CUSTODY_ROUTE_SETTLEMENT = "CUSTODY_ROUTE_SETTLEMENT", _("سند تقفيل خط سير مندوب")
