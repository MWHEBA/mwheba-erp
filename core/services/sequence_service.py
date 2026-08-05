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
        DocumentType.PURCHASE_INVOICE: "AP-INV",
        DocumentType.DEBIT_NOTE: "DBN",
        DocumentType.CUSTOMER_RECEIPT: "REC",
        DocumentType.VENDOR_PAYMENT: "VPY",
        DocumentType.FIXED_ASSET_ENTRY: "AST",
        DocumentType.DELIVERY_NOTE: "DEL",
        DocumentType.GOODS_RECEIPT_NOTE: "GRN",
        DocumentType.PURCHASE_ORDER: "PO",
        DocumentType.SALES_ORDER: "SO",
        DocumentType.STOCK_RECEIPT: "SR",
        DocumentType.STOCK_ISSUE: "SI",
        DocumentType.STOCK_TRANSFER: "ST",
        DocumentType.INVENTORY_ADJUSTMENT: "IA",
    }

    # خريطة الموديلات والحقول لتحديد الـ Seed الأولي للبيانات القديمة
    MODEL_MAPPINGS = {
        DocumentType.SALES_INVOICE: ("sale.SalesInvoice", "invoice_number"),
        DocumentType.SALES_ORDER: ("sale.SalesOrder", "order_number"),
        DocumentType.DELIVERY_NOTE: ("sale.DeliveryNote", "delivery_number"),
        DocumentType.PURCHASE_ORDER: ("purchase.PurchaseOrder", "po_number"),
        DocumentType.PURCHASE_INVOICE: ("purchase.SupplierBill", "bill_number"),
        DocumentType.GOODS_RECEIPT_NOTE: ("purchase.GoodsReceivedNote", "grn_number"),
        DocumentType.JOURNAL_ENTRY: ("financial.JournalEntry", "number"),
    }

    @classmethod
    def get_default_prefix(cls, document_type: str) -> str:
        return cls.DEFAULT_PREFIXES.get(document_type, "DOC")

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
        if not date:
            date = timezone.now().date()

        year = date.year if hasattr(date, "year") else timezone.now().year
        company_code = str(company_code or "DEFAULT").strip().upper()

        try:
            with transaction.atomic():
                # 1. Get or Create Rule
                rule, created = DocumentSequenceRule.objects.get_or_create(
                    company_code=company_code,
                    warehouse=warehouse,
                    document_type=document_type,
                    version=1,
                    defaults={
                        "prefix": cls.get_default_prefix(document_type),
                        "padding": 5,
                        "numbering_basis": "POSTING_DATE",
                        "status": "ACTIVE",
                    },
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

                # 3. Increment Counter
                counter.last_number += 1
                counter.save(update_fields=["last_number", "last_reserved_at"])

                # 4. Lock Rule after first generation
                if not rule.is_locked:
                    rule.is_locked = True
                    rule.save(update_fields=["is_locked"])

                # 5. Format Number String
                generated_number = SequenceFormatter.format_number(
                    prefix=rule.prefix,
                    year=year,
                    number=counter.last_number,
                    padding=rule.padding,
                )

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

        if not date:
            date = timezone.now().date()

        year = date.year if hasattr(date, "year") else timezone.now().year
        company_code = str(company_code or "DEFAULT").strip().upper()

        numbers = []
        with transaction.atomic():
            rule, _ = DocumentSequenceRule.objects.get_or_create(
                company_code=company_code,
                warehouse=warehouse,
                document_type=document_type,
                version=1,
                defaults={
                    "prefix": cls.get_default_prefix(document_type),
                    "padding": 5,
                    "numbering_basis": "POSTING_DATE",
                    "status": "ACTIVE",
                },
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

