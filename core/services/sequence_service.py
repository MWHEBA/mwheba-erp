# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Main Sequence Service (Facade & Orchestrator)
Handles atomic, thread-safe, multi-tenant sequence number generation.
"""
from typing import Optional
from django.db import transaction, DatabaseError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.models import (
    DocumentSequenceRule,
    DocumentSequenceCounter,
    DocumentSequenceAudit,
)
from core.services.sequence_formatter import SequenceFormatter
from core.services.legacy_seed_service import LegacySequenceAnalyzer


class SequenceService:
    """
    الخدمة الموحدة الرئيسية للترقيم التسلسلي الذري
    """

    # البادئات القياسية المعتمدة افتراضياً
    DEFAULT_PREFIXES = {
        DocumentType.JOURNAL_ENTRY: "GL",
        DocumentType.ADJUSTMENT_JOURNAL: "JV",
        DocumentType.REVERSAL_JOURNAL: "REV",
        DocumentType.SALES_INVOICE: "INV",
        DocumentType.CREDIT_NOTE: "CN",
        DocumentType.PURCHASE_INVOICE: "AP",
        DocumentType.DEBIT_NOTE: "DBN",
        DocumentType.CUSTOMER_RECEIPT: "REC",
        DocumentType.VENDOR_PAYMENT: "VPY",
        DocumentType.FIXED_ASSET_ENTRY: "AST",
        DocumentType.OPENING_BALANCE: "OPB",
        DocumentType.BANK_RECONCILIATION: "BR",
        DocumentType.DELIVERY_NOTE: "DEL",
        DocumentType.GOODS_RECEIPT_NOTE: "GRN",
        DocumentType.PURCHASE_ORDER: "PO",
        DocumentType.SALES_ORDER: "SO",
        DocumentType.STOCK_RECEIPT: "SR",
        DocumentType.STOCK_ISSUE: "SI",
        DocumentType.STOCK_TRANSFER: "ST",
        DocumentType.INVENTORY_ADJUSTMENT: "IA",
        DocumentType.WORK_ORDER: "WO",
        DocumentType.PRINTING_REQUEST: "PR",
    }

    # خريطة الموديلات والحقول لتحديد الـ Seed الأولي للبيانات القديمة
    MODEL_MAPPINGS = {
        DocumentType.SALES_INVOICE: [("sale.Sale", "number"), ("sale.SalesInvoice", "invoice_number")],
        DocumentType.SALES_ORDER: [("sale.Quotation", "number"), ("sale.SalesOrder", "order_number")],
        DocumentType.CREDIT_NOTE: [("sale.SalesReturn", "number"), ("sale.CreditNote", "credit_note_number")],
        DocumentType.DELIVERY_NOTE: [("sale.DeliveryNote", "delivery_number")],
        DocumentType.PURCHASE_ORDER: [("purchase.Purchase", "number"), ("purchase.PurchaseOrder", "po_number")],
        DocumentType.PURCHASE_INVOICE: [("purchase.Purchase", "number"), ("purchase.SupplierBill", "bill_number")],
        DocumentType.DEBIT_NOTE: [("purchase.PurchaseReturn", "number")],
        DocumentType.GOODS_RECEIPT_NOTE: [("purchase.GoodsReceivedNote", "grn_number")],
        DocumentType.JOURNAL_ENTRY: [("financial.JournalEntry", "number")],
        DocumentType.OPENING_BALANCE: [("financial.OpeningBalanceBatch", "batch_number")],
        DocumentType.BANK_RECONCILIATION: [("financial.BankReconciliationBatch", "batch_number")],
        DocumentType.STOCK_TRANSFER: [("product.StockTransfer", "transfer_number")],
        DocumentType.STOCK_RECEIPT: [("product.StockMovement", "number"), ("product.InventoryMovement", "movement_number")],
        DocumentType.STOCK_ISSUE: [("product.StockMovement", "number"), ("product.InventoryMovement", "movement_number")],
        DocumentType.INVENTORY_ADJUSTMENT: [("product.InventoryAdjustment", "adjustment_number")],
        DocumentType.WORK_ORDER: [("work_order.WorkOrder", "number")],
        DocumentType.PRINTING_REQUEST: [("printing_pricing.PrintingOrder", "order_number")],
    }

    @classmethod
    def normalize_document_type(cls, document_type: str) -> str:
        """
        تطبيع نوع المستند لمنع أخطاء الحروف الصغيرة أو البادئات غير المعرفة
        """
        if not document_type:
            return DocumentType.JOURNAL_ENTRY

        raw = str(document_type).strip().upper()

        alias_map = {
            "SALE": DocumentType.SALES_INVOICE,
            "SALES": DocumentType.SALES_INVOICE,
            "SALES_INVOICE": DocumentType.SALES_INVOICE,
            "INVOICE": DocumentType.SALES_INVOICE,
            "QUOTATION": DocumentType.SALES_ORDER,
            "SALES_ORDER": DocumentType.SALES_ORDER,
            "PURCHASE": DocumentType.PURCHASE_ORDER,
            "PURCHASE_ORDER": DocumentType.PURCHASE_ORDER,
            "PURCHASE_INVOICE": DocumentType.PURCHASE_INVOICE,
            "SUPPLIER_BILL": DocumentType.PURCHASE_INVOICE,
            "BILL": DocumentType.PURCHASE_INVOICE,
            "JOURNAL_ENTRY": DocumentType.JOURNAL_ENTRY,
            "ADJUSTMENT_JOURNAL": DocumentType.ADJUSTMENT_JOURNAL,
            "REVERSAL_JOURNAL": DocumentType.REVERSAL_JOURNAL,
            "CREDIT_NOTE": DocumentType.CREDIT_NOTE,
            "DEBIT_NOTE": DocumentType.DEBIT_NOTE,
            "DELIVERY_NOTE": DocumentType.DELIVERY_NOTE,
            "GOODS_RECEIPT_NOTE": DocumentType.GOODS_RECEIPT_NOTE,
            "GRN": DocumentType.GOODS_RECEIPT_NOTE,
            "STOCK_RECEIPT": DocumentType.STOCK_RECEIPT,
            "STOCK_ISSUE": DocumentType.STOCK_ISSUE,
            "STOCK_TRANSFER": DocumentType.STOCK_TRANSFER,
            "INVENTORY_ADJUSTMENT": DocumentType.INVENTORY_ADJUSTMENT,
            "OPENING_BALANCE": DocumentType.OPENING_BALANCE,
            "BANK_RECONCILIATION": DocumentType.BANK_RECONCILIATION,
            "CUSTOMER_RECEIPT": DocumentType.CUSTOMER_RECEIPT,
            "VENDOR_PAYMENT": DocumentType.VENDOR_PAYMENT,
            "FIXED_ASSET_ENTRY": DocumentType.FIXED_ASSET_ENTRY,
            "WORK_ORDER": DocumentType.WORK_ORDER,
            "WO": DocumentType.WORK_ORDER,
            "PRINTING_ORDER": DocumentType.PRINTING_REQUEST,
            "PRINTING_REQUEST": DocumentType.PRINTING_REQUEST,
            "PR": DocumentType.PRINTING_REQUEST,
        }

        return alias_map.get(raw, raw)

    @classmethod
    def get_default_prefix(cls, document_type: str) -> str:
        document_type = cls.normalize_document_type(document_type)
        return cls.DEFAULT_PREFIXES.get(document_type, "DOC")

    @classmethod
    def peek_next_number(
        cls,
        document_type: str,
        warehouse=None,
        company_code: str = "DEFAULT",
        date=None,
    ) -> str:
        """
        معاينة الرقم التالي المتوقع دون أي حجز ودون تعديل في قاعدة البيانات (Read-Only Preview)
        """
        document_type = cls.normalize_document_type(document_type)
        if not date:
            date = timezone.now().date()

        year = date.year if hasattr(date, "year") else timezone.now().year
        company_code = str(company_code or "DEFAULT").strip().upper()

        rule = DocumentSequenceRule.objects.filter(
            company_code=company_code,
            warehouse=warehouse,
            document_type=document_type,
            version=1,
        ).first()

        prefix = rule.prefix if rule else cls.get_default_prefix(document_type)
        padding = rule.padding if rule else 4

        counter = DocumentSequenceCounter.objects.filter(
            company_code=company_code,
            warehouse=warehouse,
            document_type=document_type,
            year=year,
        ).first()

        if counter:
            next_num = counter.last_number + 1
        else:
            seed_number = 0
            if document_type in cls.MODEL_MAPPINGS:
                mappings = cls.MODEL_MAPPINGS[document_type]
                model_paths = mappings if isinstance(mappings, list) else [mappings]
                for model_path, field_name in model_paths:
                    try:
                        from django.apps import apps
                        target_model = apps.get_model(model_path)
                        cand_seed = LegacySequenceAnalyzer.get_max_legacy_seed(
                            target_model, field_name, year
                        )
                        if cand_seed > seed_number:
                            seed_number = cand_seed
                    except Exception:
                        pass
            next_num = seed_number + 1

        return SequenceFormatter.format_number(
            prefix=prefix,
            year=year,
            number=next_num,
            padding=padding,
        )

    @classmethod
    def recalibrate_counters(cls, company_code: str = "DEFAULT") -> dict:
        """
        فحص السجلات الفعلية وضبط العدادات على أعلى رقم حقيقي مسجل لكل نوع مستند
        """
        from django.apps import apps
        results = {}
        current_year = timezone.now().year

        for doc_type, mappings in cls.MODEL_MAPPINGS.items():
            model_paths = mappings if isinstance(mappings, list) else [mappings]
            max_seed = 0
            for model_path, field_name in model_paths:
                try:
                    target_model = apps.get_model(model_path)
                    cand_seed = LegacySequenceAnalyzer.get_max_legacy_seed(
                        target_model, field_name, current_year
                    )
                    if cand_seed > max_seed:
                        max_seed = cand_seed
                except Exception:
                    pass

            counter = DocumentSequenceCounter.objects.filter(
                company_code=company_code,
                document_type=doc_type,
                year=current_year,
            ).first()

            if counter:
                old_val = counter.last_number
                counter.last_number = max_seed
                counter.save(update_fields=["last_number"])
                results[doc_type] = {"old": old_val, "recalibrated": max_seed}
            else:
                results[doc_type] = {"max_found": max_seed}

        return results

    @classmethod
    def get_next_number(
        cls,
        document_type: str,
        warehouse=None,
        company_code: str = "DEFAULT",
        date=None,
        user=None,
        source_type: str = "USER",
    ) -> str:
        """
        توليد الرقم التالي في التسلسل الذري المحمي بـ select_for_update
        """
        document_type = cls.normalize_document_type(document_type)
        if not date:
            date = timezone.now().date()

        year = date.year if hasattr(date, "year") else timezone.now().year
        company_code = str(company_code or "DEFAULT").strip().upper()

        try:
            with transaction.atomic():
                # 1. Get or Create Rule
                rule = DocumentSequenceRule.objects.filter(
                    company_code=company_code,
                    warehouse=warehouse,
                    document_type=document_type,
                    version=1,
                ).first()
                if not rule:
                    rule = DocumentSequenceRule.objects.create(
                        company_code=company_code,
                        warehouse=warehouse,
                        document_type=document_type,
                        version=1,
                        prefix=cls.get_default_prefix(document_type),
                        padding=4,
                        numbering_basis="POSTING_DATE",
                        status="ACTIVE",
                    )

                # 2. Get or Create Counter with Atomic Lock
                counter = (
                    DocumentSequenceCounter.objects.select_for_update()
                    .filter(
                        company_code=company_code,
                        warehouse=warehouse,
                        document_type=document_type,
                        year=year,
                    )
                    .first()
                )

                if not counter:
                    # Calculate legacy seed offset if counter doesn't exist
                    seed_number = 0
                    if document_type in cls.MODEL_MAPPINGS:
                        mappings = cls.MODEL_MAPPINGS[document_type]
                        model_paths = mappings if isinstance(mappings, list) else [mappings]
                        for model_path, field_name in model_paths:
                            try:
                                from django.apps import apps
                                target_model = apps.get_model(model_path)
                                cand_seed = LegacySequenceAnalyzer.get_max_legacy_seed(
                                    target_model, field_name, year
                                )
                                if cand_seed > seed_number:
                                    seed_number = cand_seed
                            except Exception:
                                pass

                    counter = DocumentSequenceCounter.objects.create(
                        rule=rule,
                        company_code=company_code,
                        warehouse=warehouse,
                        document_type=document_type,
                        year=year,
                        last_number=seed_number,
                    )


                # 3. Increment Counter with collision protection
                while True:
                    counter.last_number += 1
                    generated_number = SequenceFormatter.format_number(
                        prefix=rule.prefix,
                        year=year,
                        number=counter.last_number,
                        padding=rule.padding,
                    )
                    
                    collision = False
                    if document_type in cls.MODEL_MAPPINGS:
                        mappings = cls.MODEL_MAPPINGS[document_type]
                        model_paths = mappings if isinstance(mappings, list) else [mappings]
                        for model_path, field_name in model_paths:
                            try:
                                from django.apps import apps
                                target_model = apps.get_model(model_path)
                                if target_model.objects.filter(**{field_name: generated_number}).exists():
                                    collision = True
                                    break
                            except Exception:
                                pass
                    if not collision:
                        break

                counter.save(update_fields=["last_number", "last_reserved_at"])

                # 4. Lock Rule after first generation
                if not rule.is_locked:
                    rule.is_locked = True
                    rule.save(update_fields=["is_locked"])

                # 6. Audit Trail Logging
                DocumentSequenceAudit.objects.create(
                    event_type="GENERATED",
                    document_type=document_type,
                    document_number=generated_number,
                    company_code=company_code,
                    warehouse=warehouse,
                    user=user if (user and hasattr(user, 'is_authenticated') and user.is_authenticated) else None,
                    source_type=source_type,
                    prefix_snapshot=rule.prefix,
                    padding_snapshot=rule.padding,
                    year_snapshot=year,
                    sequence_number=counter.last_number,
                    new_value=generated_number,
                )

                return generated_number

        except DatabaseError as e:
            # Audit rollback/failure
            DocumentSequenceAudit.objects.create(
                event_type="FAILED",
                document_type=document_type,
                company_code=company_code,
                warehouse=warehouse,
                user=user if (user and hasattr(user, 'is_authenticated') and user.is_authenticated) else None,
                source_type=source_type,
                reason=str(e),
            )
            raise e

    @classmethod
    def get_batch_numbers(
        cls,
        document_type: str,
        count: int,
        warehouse=None,
        company_code: str = "DEFAULT",
        date=None,
        user=None,
        source_type: str = "JOB",
    ) -> list:
        """
        توليد دفعة من الأرقام التسلسلية بقفزة ذرية واحدة في العداد لمصادر الاستيراد والعمليات الجماعية
        """
        if count <= 0:
            return []

        document_type = cls.normalize_document_type(document_type)
        if not date:
            date = timezone.now().date()

        year = date.year if hasattr(date, "year") else timezone.now().year
        company_code = str(company_code or "DEFAULT").strip().upper()

        numbers = []
        with transaction.atomic():
            rule = DocumentSequenceRule.objects.filter(
                company_code=company_code,
                warehouse=warehouse,
                document_type=document_type,
                version=1,
            ).first()
            if not rule:
                rule = DocumentSequenceRule.objects.create(
                    company_code=company_code,
                    warehouse=warehouse,
                    document_type=document_type,
                    version=1,
                    prefix=cls.get_default_prefix(document_type),
                    padding=4,
                    numbering_basis="POSTING_DATE",
                    status="ACTIVE",
                )

            counter = (
                DocumentSequenceCounter.objects.select_for_update()
                .filter(
                    company_code=company_code,
                    warehouse=warehouse,
                    document_type=document_type,
                    year=year,
                )
                .first()
            )

            if not counter:
                seed_number = 0
                if document_type in cls.MODEL_MAPPINGS:
                    model_path, field_name = cls.MODEL_MAPPINGS[document_type]
                    try:
                        from django.apps import apps
                        target_model = apps.get_model(model_path)
                        seed_number = LegacySequenceAnalyzer.get_max_legacy_seed(
                            target_model, field_name, year
                        )
                    except Exception:
                        seed_number = 0

                counter = DocumentSequenceCounter.objects.create(
                    rule=rule,
                    company_code=company_code,
                    warehouse=warehouse,
                    document_type=document_type,
                    year=year,
                    last_number=seed_number,
                )

            start_num = counter.last_number + 1
            counter.last_number += count
            counter.save(update_fields=["last_number", "last_reserved_at"])

            if not rule.is_locked:
                rule.is_locked = True
                rule.save(update_fields=["is_locked"])

            for seq_num in range(start_num, start_num + count):
                gen_num = SequenceFormatter.format_number(
                    prefix=rule.prefix,
                    year=year,
                    number=seq_num,
                    padding=rule.padding,
                )
                numbers.append(gen_num)

            DocumentSequenceAudit.objects.create(
                event_type="GENERATED",
                document_type=document_type,
                document_number=f"BATCH_{numbers[0]}_TO_{numbers[-1]}",
                company_code=company_code,
                warehouse=warehouse,
                user=user if (user and hasattr(user, 'is_authenticated') and user.is_authenticated) else None,
                source_type=source_type,
                prefix_snapshot=rule.prefix,
                padding_snapshot=rule.padding,
                year_snapshot=year,
                sequence_number=counter.last_number,
                new_value=f"COUNT_{count}",
            )

        return numbers

    @classmethod
    def override_document_number(
        cls,
        instance,
        number_field: str,
        new_number: str,
        user,
        reason: str,
    ):
        """
        التجاوز الاستثنائي المحوكم لتعديل رقم مستند مرحّل بقرار إداري وتسجيل الحدث في الـ Audit
        """
        old_number = getattr(instance, number_field, "")
        setattr(instance, number_field, new_number)
        instance.save(update_fields=[number_field])

        DocumentSequenceAudit.objects.create(
            event_type="MANUAL_EDIT_OVERRIDE",
            document_type=getattr(instance, 'document_type', 'MANUAL_OVERRIDE'),
            document_number=new_number,
            user=user if (user and hasattr(user, 'is_authenticated') and user.is_authenticated) else None,
            source_type="ADMIN_OVERRIDE",
            old_value=old_number,
            new_value=new_number,
            reason=reason,
        )

