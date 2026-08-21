import uuid
import json
import hashlib
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction, models
from django.utils import timezone

from financial.models import (
    TaxJurisdiction,
    TaxCode,
    TaxRateHistory,
    TaxRule,
    TaxRuleCondition,
    TaxRuleEvaluationLog,
    TaxAccountMapping,
    TaxRegistration,
    TaxExemptionCertificate,
    TaxCalculationLine,
    TaxEvent,
    TaxDeterminationAudit,
    TaxReversal,
)
from financial.services.tax_decision import (
    TaxDecision,
    TaxCalculationResult,
    TaxAccountingCommand,
    TaxRoundingPolicy,
)
from governance.services.accounting_gateway import create_tax_posting, create_tax_reversal_posting
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("financial.services.tax_service")


class TaxDeterminationService:
    """
    FIN-TAX-001 v3.0: Enterprise Tax Determination Engine Service (Frozen Master Architecture)
    السلطة المركزية الحاكمة لاحتساب وتطبيق الضرائب والقيود المحاسبية عبر كافة مستندات ERP
    """

    @classmethod
    def generate_canonical_tax_audit_hash(
        cls,
        correlation_id: str,
        processed_event_id: str,
        document_number: str,
        tax_code: str,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        currency: str,
        exchange_rate: Decimal,
        timestamp: str
    ) -> str:
        """
        إنشاء التوقيع المشفر Canonical JSON SHA256 لسجل التدقيق والإثبات الضريبي
        """
        payload = {
            "correlation_id": str(correlation_id),
            "currency": str(currency),
            "document_number": str(document_number),
            "exchange_rate": str(exchange_rate),
            "processed_event_id": str(processed_event_id),
            "tax_amount": str(tax_amount),
            "tax_code": str(tax_code),
            "taxable_amount": str(taxable_amount),
            "timestamp": str(timestamp)
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @classmethod
    def calculate_tax(
        cls,
        document_type: str,
        document_id: int,
        customer=None,
        supplier=None,
        lines: List[Dict[str, Any]] = None,
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        transaction_date=None,
        jurisdiction_code: Optional[str] = "EGYPT-TAX",
        is_tax_inclusive: bool = False
    ) -> TaxCalculationResult:
        """
        FIN-TAX-001 v3.2: Enterprise Line-by-Line Multi-Tax Determination Engine
        حساب وتقييم الضريبة على مستوى كل بند صنف مستقلاً مع دعم الأسعار الشاملة وغير الشاملة وفروق التقريب
        """
        if lines is None:
            lines = []

        date_val = transaction_date or timezone.now().date()
        doc_num = f"{document_type}-{document_id}"

        # 1. Resolve Jurisdiction
        jurisdiction = TaxJurisdiction.objects.filter(code=jurisdiction_code, is_active=True).first()
        if not jurisdiction:
            jurisdiction, _ = TaxJurisdiction.objects.get_or_create(
                code="EGYPT-TAX",
                defaults={"name": "Egyptian Tax Authority", "country": "Egypt", "tax_authority": "مصلحة الضرائب المصرية", "is_active": True}
            )

        # 2. Check Global Tax Exemption Certificate on Party
        party_exemption = None
        if customer:
            party_exemption = TaxExemptionCertificate.objects.filter(customer=customer, status="ACTIVE").first()
        elif supplier:
            party_exemption = TaxExemptionCertificate.objects.filter(supplier=supplier, status="ACTIVE").first()

        is_party_exempt = False
        if party_exemption and party_exemption.is_valid_on(date_val):
            is_party_exempt = True

        # 3. Rule Evaluation Hierarchy: Jurisdiction -> TaxRule Priority Resolution
        candidate_rules_qs = TaxRule.objects.filter(is_active=True, effective_from__lte=date_val).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=date_val)
        ).select_related("tax_code", "jurisdiction")

        if jurisdiction:
            cand_j = candidate_rules_qs.filter(jurisdiction=jurisdiction)
            if cand_j.exists():
                candidate_rules_qs = cand_j

        candidate_rules = list(candidate_rules_qs.order_by("-priority", "-version"))
        selected_rule = candidate_rules[0] if candidate_rules else None

        # Default system tax code fallback
        default_vat = selected_rule.tax_code if selected_rule else None
        if not default_vat:
            default_vat, _ = TaxCode.objects.get_or_create(
                code="VAT14",
                defaults={
                    "name": "ضريبة القيمة المضافة العامة 14%",
                    "tax_type": "VAT",
                    "tax_nature": "OUTPUT",
                    "rate": Decimal("14.0000"),
                    "recoverability_percentage": Decimal("100.00"),
                    "is_active": True
                }
            )

        line_decisions = []
        tax_decisions = []
        total_subtotal = Decimal("0.00")
        total_taxable = Decimal("0.00")
        total_tax = Decimal("0.00")

        # 4. Line-by-Line Multi-Tax Evaluation
        for line_idx, line in enumerate(lines, start=1):
            raw_amount = Decimal(str(line.get("amount", "0.00")))
            line_prod = line.get("product")
            line_prod_id = line.get("product_id")
            line_tax_code = line.get("tax_code")
            line_tax_code_obj = None

            # Resolve line tax code
            if isinstance(line_tax_code, TaxCode):
                line_tax_code_obj = line_tax_code
            elif isinstance(line_tax_code, str):
                line_tax_code_obj = TaxCode.objects.filter(code=line_tax_code, is_active=True).first()

            if not line_tax_code_obj and line_prod:
                if hasattr(line_prod, 'tax_code') and line_prod.tax_code:
                    line_tax_code_obj = line_prod.tax_code
            elif not line_tax_code_obj and line_prod_id:
                from product.models import Product
                prod_obj = Product.objects.filter(pk=line_prod_id).select_related("tax_code").first()
                if prod_obj and prod_obj.tax_code:
                    line_tax_code_obj = prod_obj.tax_code

            if not line_tax_code_obj:
                line_tax_code_obj = default_vat

            rate = line_tax_code_obj.rate

            # Handle Party Exemption or Line Exemption
            if is_party_exempt or line_tax_code_obj.tax_type in ["EXEMPT", "ZERO_RATED"]:
                if is_party_exempt:
                    ex_reason = f"معفى بموجب شهادة إعفاء ضريبي رقم {party_exemption.certificate_number}"
                else:
                    ex_reason = f"صنف معفى / خاضع لسعر صفر ({line_tax_code_obj.name})"
                
                line_base = raw_amount
                line_tax = Decimal("0.00")
                applied_rate = Decimal("0.0000")
            else:
                ex_reason = None
                applied_rate = rate
                line_is_inclusive = line.get("is_tax_inclusive", is_tax_inclusive)
                if line_is_inclusive and applied_rate > Decimal("0.00"):
                    # Extraction formula: Base = Amount / (1 + Rate/100)
                    multiplier = Decimal("1.00") + (applied_rate / Decimal("100.00"))
                    line_base = (raw_amount / multiplier).quantize(Decimal("0.01"))
                    line_tax = (raw_amount - line_base).quantize(Decimal("0.01"))
                else:
                    line_base = raw_amount
                    line_tax = (line_base * (applied_rate / Decimal("100.00"))).quantize(Decimal("0.01"))

            total_subtotal += line_base
            total_taxable += line_base
            total_tax += line_tax

            ld = {
                "line_index": line_idx,
                "document_line_id": line.get("line_id", line_idx),
                "tax_code": line_tax_code_obj.code,
                "tax_name": line_tax_code_obj.name,
                "tax_nature": line_tax_code_obj.tax_nature,
                "taxable_amount": str(line_base),
                "tax_rate": str(applied_rate),
                "tax_amount": str(line_tax),
                "exemption_reason": ex_reason
            }
            line_decisions.append(ld)

        # Primary decision for header summary
        primary_code = line_decisions[0]["tax_code"] if line_decisions else default_vat.code
        primary_rate = Decimal(line_decisions[0]["tax_rate"]) if line_decisions else default_vat.rate

        header_decision = TaxDecision(
            decision_type="TAX_EXEMPT" if is_party_exempt else "TAX_APPLIED",
            applicable=not is_party_exempt and total_tax > Decimal("0.00"),
            selected_rule_code=None if is_party_exempt else (selected_rule.code if selected_rule else "LINE_MULTI_TAX_RESOLUTION"),
            rule_version=selected_rule.version if selected_rule else 1,
            tax_code=primary_code,
            tax_rate=primary_rate,
            taxable_amount=total_taxable,
            tax_amount=total_tax,
            jurisdiction_code=jurisdiction.code,
            decision_reason="Exempted by certificate" if is_party_exempt else f"Applied TaxRule {selected_rule.code if selected_rule else primary_code}",
            effective_date=date_val.isoformat(),
            accounting_position=default_vat.tax_nature,
            line_decisions=line_decisions,
            exemption_certificate_id=party_exemption.id if party_exemption else None
        )
        tax_decisions.append(header_decision)

        # Log Evaluation in TaxRuleEvaluationLog
        TaxRuleEvaluationLog.objects.create(
            document_type=document_type,
            document_number=doc_num,
            candidate_rules=[r.code for r in candidate_rules] if candidate_rules else [ld["tax_code"] for ld in line_decisions],
            selected_rule=selected_rule.code if selected_rule else f"MULTI_TAX:{primary_code}",
            rejected_rules=[{"rule": r.code, "reason": "Lower Priority"} for r in candidate_rules[1:]] if candidate_rules else [],
            priority_score=selected_rule.priority if selected_rule else 100
        )

        func_tax = (total_tax * exchange_rate).quantize(Decimal("0.01"))

        return TaxCalculationResult(
            document_id=document_id,
            subtotal=total_subtotal,
            taxable_amount=total_taxable,
            tax_amount=total_tax,
            total_amount=total_subtotal + total_tax,
            currency=currency,
            exchange_rate=exchange_rate,
            functional_tax_amount=func_tax,
            tax_decisions=tax_decisions,
            line_decisions=line_decisions
        )

    @classmethod
    def apply_tax_posting(
        cls,
        document_type: str,
        document_id: int,
        document_number: str,
        customer=None,
        supplier=None,
        lines: List[Dict[str, Any]] = None,
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        user=None,
        journal_entry=None
    ) -> TaxDeterminationAudit:
        """
        FIN-TAX-001 v3.2: Atomic Tax Determination & Audit Evidence Logger (Zero Double-Posting)
        يربط السجل مباشرة بالقيد المحاسبي الأساسي للفاتورة مع التوقيع المشفر SHA256 وسجل الأحداث المستقل
        """
        with transaction.atomic():
            event_id = f"TAX-{document_type}-{document_id}"

            # Check Event Idempotency Guard
            existing = TaxDeterminationAudit.objects.filter(processed_event_id=event_id).first()
            if existing:
                logger.warning(f"Tax Event '{event_id}' already applied in Audit #{existing.id}. Returning existing.")
                return existing

            calc_result = cls.calculate_tax(
                document_type=document_type,
                document_id=document_id,
                customer=customer,
                supplier=supplier,
                lines=lines,
                currency=currency,
                exchange_rate=exchange_rate
            )

            decision = calc_result.tax_decisions[0]
            tax_code_obj = TaxCode.objects.filter(code=decision.tax_code).first()
            if not tax_code_obj:
                tax_code_obj = TaxCode.objects.first()

            # Persist Line Calculations
            for ld in calc_result.line_decisions:
                l_code = TaxCode.objects.filter(code=ld["tax_code"]).first() or tax_code_obj
                TaxCalculationLine.objects.create(
                    document_type=document_type,
                    document_id=document_id,
                    document_line_id=ld["document_line_id"],
                    tax_code=l_code,
                    taxable_amount=Decimal(ld["taxable_amount"]),
                    tax_rate=Decimal(ld["tax_rate"]),
                    tax_amount=Decimal(ld["tax_amount"]),
                    exemption_reason=ld.get("exemption_reason")
                )

            func_tax = calc_result.functional_tax_amount
            correlation_id = uuid.uuid4()

            # Create standalone journal entry ONLY if no existing journal entry is provided
            posted_journal_entry = journal_entry
            if not posted_journal_entry and func_tax > Decimal("0.00") and decision.applicable:
                try:
                    from financial.services.role_registry import AccountRoleRegistry
                    default_ar = AccountRoleRegistry.get_account_code("AR_CONTROL_ACCOUNT") or "11010"
                    default_ap = AccountRoleRegistry.get_account_code("AP_CONTROL_ACCOUNT") or "21010"
                    output_tax_acc = AccountRoleRegistry.get_account_code("OUTPUT_TAX_ACCOUNT") or "22010"
                    input_tax_acc = AccountRoleRegistry.get_account_code("INPUT_TAX_ACCOUNT") or "11050"
                    
                    mapping = TaxAccountMapping.objects.filter(tax_code=tax_code_obj).first()
                    if mapping and mapping.debit_account and mapping.credit_account:
                        dr_acc = mapping.debit_account.code
                        cr_acc = mapping.credit_account.code
                    elif decision.accounting_position == "OUTPUT":
                        dr_acc = customer.financial_account.code if (customer and hasattr(customer, 'financial_account') and customer.financial_account) else default_ar
                        cr_acc = output_tax_acc
                    elif decision.accounting_position == "INPUT":
                        dr_acc = input_tax_acc
                        cr_acc = supplier.financial_account.code if (supplier and hasattr(supplier, 'financial_account') and supplier.financial_account) else default_ap
                    else:
                        dr_acc = input_tax_acc
                        cr_acc = output_tax_acc

                    command = TaxAccountingCommand(
                        command_id=str(uuid.uuid4()),
                        correlation_id=str(correlation_id),
                        document_type=document_type,
                        document_number=document_number,
                        tax_code=tax_code_obj.code,
                        debit_account_code=dr_acc,
                        credit_account_code=cr_acc,
                        taxable_amount=decision.taxable_amount,
                        tax_amount=decision.tax_amount,
                        currency_code=currency,
                        exchange_rate=exchange_rate,
                        functional_amount=func_tax,
                        posting_date=timezone.now().date(),
                        user=user
                    )
                    posted_journal_entry = create_tax_posting(command)
                except Exception as e:
                    logger.warning(f"Could not post tax GL entry: {e}")

            audit = TaxDeterminationAudit(
                document_type=document_type,
                document_id=document_id,
                document_number=document_number,
                customer=customer,
                supplier=supplier,
                tax_code=tax_code_obj,
                taxable_amount=decision.taxable_amount,
                tax_amount=decision.tax_amount,
                currency=currency,
                exchange_rate=exchange_rate,
                functional_tax_amount=func_tax,
                audit_status="POSTED" if posted_journal_entry else "CALCULATED",
                processed_event_id=event_id,
                correlation_id=correlation_id,
                audit_hash="",
                journal_entry=posted_journal_entry
            )
            audit.save()

            # Generate SHA256 Audit Hash using saved timestamp
            hash_val = cls.generate_canonical_tax_audit_hash(
                correlation_id=str(correlation_id),
                processed_event_id=event_id,
                document_number=document_number,
                tax_code=tax_code_obj.code,
                taxable_amount=decision.taxable_amount,
                tax_amount=decision.tax_amount,
                currency=currency,
                exchange_rate=exchange_rate,
                timestamp=audit.created_at.isoformat()
            )

            TaxDeterminationAudit.objects.filter(pk=audit.id).update(audit_hash=hash_val)
            audit.audit_hash = hash_val

            # Capture Transaction-Time Snapshots
            from financial.models import TaxTransactionSnapshot, TaxExemptionSnapshot
            cust_name = customer.name if (customer and hasattr(customer, 'name')) else None
            supp_name = supplier.name if (supplier and hasattr(supplier, 'name')) else None
            party_tax_num = getattr(customer, 'tax_number', None) or getattr(supplier, 'tax_number', None)

            TaxTransactionSnapshot.objects.create(
                audit=audit,
                document_type=document_type,
                document_number=document_number,
                customer_name=cust_name,
                supplier_name=supp_name,
                tax_registration_number=party_tax_num,
                applied_rule_code=decision.selected_rule_code or "EXEMPT",
                applied_tax_rate=decision.tax_rate
            )

            if decision.exemption_certificate_id:
                try:
                    ex_cert = TaxExemptionCertificate.objects.get(pk=decision.exemption_certificate_id)
                    TaxExemptionSnapshot.objects.create(
                        audit=audit,
                        certificate_number=ex_cert.certificate_number,
                        tax_code_code=ex_cert.tax_code.code,
                        valid_from=ex_cert.valid_from,
                        valid_to=ex_cert.valid_to,
                        exemption_reason=ex_cert.exemption_reason
                    )
                    # Update quota tracking if defined
                    if ex_cert.max_quota_amount is not None:
                        TaxExemptionCertificate.objects.filter(pk=ex_cert.id).update(
                            utilized_amount=models.F('utilized_amount') + decision.taxable_amount
                        )
                except TaxExemptionCertificate.DoesNotExist:
                    pass

            # Log Independent Domain TaxEvent
            TaxEvent.objects.create(
                event_type="TAX_POSTING_APPLIED",
                document_type=document_type,
                document_number=document_number,
                status="PROCESSED"
            )

            logger.info(f"TaxDeterminationAudit #{audit.id} applied for {document_type} #{document_number} (Hash: {hash_val[:8]}...).")
            return audit

    @classmethod
    def process_tax_reversal(
        cls,
        audit_id: int,
        reversal_amount: Optional[Decimal] = None,
        reason: str = "Tax Reversal",
        user=None
    ) -> TaxReversal:
        """
        عكس القيد الضريبي المحاسبي بالكامل أو جزئياً
        """
        with transaction.atomic():
            audit = TaxDeterminationAudit.objects.select_for_update().get(pk=audit_id)

            rev_amt = reversal_amount if reversal_amount is not None else audit.functional_tax_amount

            if rev_amt > audit.functional_tax_amount:
                raise FinancialCoreError(f"Reversal Cap Guard: Requested reversal ({rev_amt}) exceeds recorded audit tax amount ({audit.functional_tax_amount}).")

            rev_journal = None
            if audit.journal_entry:
                rev_journal = create_tax_reversal_posting(audit.journal_entry, user=user, reason=reason)

            reversal = TaxReversal.objects.create(
                original_audit=audit,
                reversal_amount=rev_amt,
                journal_entry=rev_journal,
                reason=reason
            )

            audit.audit_status = "REVERSED"

            TaxEvent.objects.create(
                event_type="TAX_REVERSAL_APPLIED",
                document_type=audit.document_type,
                document_number=audit.document_number,
                status="PROCESSED"
            )

            logger.info(f"TaxReversal #{reversal.id} created for Audit #{audit_id}.")
            return reversal

    @classmethod
    def verify_audit_integrity(cls, audit_id: int) -> bool:
        """
        فحص سلامة التوقيع المشفر Canonical SHA256 لحسابات السجل الضريبي
        """
        audit = TaxDeterminationAudit.objects.select_related("tax_code").get(pk=audit_id)
        expected_hash = cls.generate_canonical_tax_audit_hash(
            correlation_id=str(audit.correlation_id),
            processed_event_id=audit.processed_event_id,
            document_number=audit.document_number,
            tax_code=audit.tax_code.code,
            taxable_amount=audit.taxable_amount,
            tax_amount=audit.tax_amount,
            currency=audit.currency,
            exchange_rate=audit.exchange_rate,
            timestamp=audit.created_at.isoformat()
        )
        return audit.audit_hash == expected_hash

    @classmethod
    def seed_egyptian_tax_presets(cls) -> Dict[str, Any]:
        """
        توليد القواعد والأكواد الضريبية المعيارية للجمهورية المصرية بضغطة زر واحدة (One-Click Preset Generator)
        """
        presets = [
            {
                "code": "VAT14",
                "name": "ضريبة القيمة المضافة العامة 14%",
                "tax_type": "VAT",
                "tax_nature": "OUTPUT",
                "rate": Decimal("14.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T1",
                "is_default": True
            },
            {
                "code": "VAT14_IN",
                "name": "ضريبة القيمة المضافة على المشتريات (مدخلات) 14%",
                "tax_type": "VAT",
                "tax_nature": "INPUT",
                "rate": Decimal("14.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T1"
            },
            {
                "code": "VAT_NON_REC",
                "name": "ضريبة مدخلات غير قابلة للاسترداد (سيارات وضيافة) 14%",
                "tax_type": "VAT",
                "tax_nature": "NON_RECOVERABLE",
                "rate": Decimal("14.0000"),
                "recoverability_percentage": Decimal("0.00"),
                "is_recoverable": False,
                "eta_tax_type": "T1"
            },
            {
                "code": "TABLE_05",
                "name": "ضريبة الجدول (سلع وخدمات خاصة) 5%",
                "tax_type": "EXCISE",
                "tax_nature": "OUTPUT",
                "rate": Decimal("5.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T2"
            },
            {
                "code": "ZERO_RATED",
                "name": "ضريبة بسعر صفر (صادرات ومناطق حرة) 0%",
                "tax_type": "ZERO_RATED",
                "tax_nature": "OUTPUT",
                "rate": Decimal("0.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T1"
            },
            {
                "code": "EXEMPT",
                "name": "معفى من الضريبة بنص القانون 0%",
                "tax_type": "EXEMPT",
                "tax_nature": "OUTPUT",
                "rate": Decimal("0.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T1"
            },
            {
                "code": "WHT_01",
                "name": "خصم وتحصيل - توريدات ومقاولات (1%)",
                "tax_type": "WITHHOLDING",
                "tax_nature": "WITHHOLDING",
                "rate": Decimal("1.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T4",
                "is_default": True
            },
            {
                "code": "WHT_03",
                "name": "خصم وتحصيل - خدمات (3%)",
                "tax_type": "WITHHOLDING",
                "tax_nature": "WITHHOLDING",
                "rate": Decimal("3.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T4"
            },
            {
                "code": "WHT_05",
                "name": "خصم وتحصيل - مهن حرة واستشارات (5%)",
                "tax_type": "WITHHOLDING",
                "tax_nature": "WITHHOLDING",
                "rate": Decimal("5.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "eta_tax_type": "T4"
            }
        ]

        created_count = 0
        updated_count = 0
        for p in presets:
            obj, created = TaxCode.objects.update_or_create(code=p["code"], defaults=p)
            if created:
                created_count += 1
            else:
                updated_count += 1

        # دمج وحذف الأكواد القديمة المكررة لضمان نظافة وتوحيد جدول الضرائب
        legacy_mappings = [
            ("VAT0", "ZERO_RATED"),
            ("WHT1", "WHT_01"),
        ]

        from product.models.product_core import Product
        for old_code, target_code in legacy_mappings:
            old_obj = TaxCode.objects.filter(code=old_code).first()
            target_obj = TaxCode.objects.filter(code=target_code).first()
            if old_obj and target_obj and old_obj.id != target_obj.id:
                # تحديث أي مراجع تشير للكود القديم
                Product.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
                TaxRule.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
                TaxDeterminationAudit.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
                TaxCalculationLine.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
                TaxAccountMapping.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
                TaxRateHistory.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
                old_obj.delete()

        return {"status": "success", "created_count": created_count, "updated_count": updated_count, "total_presets": len(presets)}
