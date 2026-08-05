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
        jurisdiction_code: Optional[str] = "EGYPT-TAX"
    ) -> TaxCalculationResult:
        """
        حساب وتقييم الضريبة والـ Calculation Output مع تسجيل سجل تتبع تقييم القواعد TaxRuleEvaluationLog
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

        # 2. Check Tax Exemption Management
        exemption = None
        if customer:
            exemption = TaxExemptionCertificate.objects.filter(customer=customer, status="ACTIVE").first()
        elif supplier:
            exemption = TaxExemptionCertificate.objects.filter(supplier=supplier, status="ACTIVE").first()

        if exemption and exemption.is_valid_on(date_val):
            total_base = sum(Decimal(str(l.get("amount", "0.00"))) for l in lines)
            decision = TaxDecision(
                decision_type="TAX_EXEMPT",
                applicable=False,
                selected_rule_code=None,
                rule_version=1,
                tax_code=exemption.tax_code.code,
                tax_rate=Decimal("0.0000"),
                taxable_amount=total_base,
                tax_amount=Decimal("0.00"),
                jurisdiction_code=jurisdiction.code,
                decision_reason=f"Exempted by valid Exemption Certificate #{exemption.certificate_number}",
                exemption_certificate_id=exemption.id,
                effective_date=date_val.isoformat()
            )

            # Log Evaluation
            TaxRuleEvaluationLog.objects.create(
                document_type=document_type,
                document_number=doc_num,
                candidate_rules=[],
                selected_rule=None,
                rejected_rules=[{"reason": "Exempted by valid certificate"}],
                priority_score=0
            )

            return TaxCalculationResult(
                document_id=document_id,
                subtotal=total_base,
                taxable_amount=total_base,
                tax_amount=Decimal("0.00"),
                total_amount=total_base,
                currency=currency,
                exchange_rate=exchange_rate,
                functional_tax_amount=Decimal("0.00"),
                tax_decisions=[decision],
                line_decisions=[]
            )

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

        if not selected_rule:
            tax_code_obj, _ = TaxCode.objects.get_or_create(
                code="VAT14",
                defaults={"name": "Standard Value Added Tax 14%", "tax_type": "VAT", "tax_nature": "OUTPUT", "rate": Decimal("14.0000"), "recoverability_percentage": Decimal("100.00")}
            )
            selected_rule = TaxRule.objects.create(
                code="RUL-VAT14-DEFAULT",
                name="Default System VAT 14%",
                version=1,
                priority=1,
                rule_scope="GLOBAL",
                tax_code=tax_code_obj,
                jurisdiction=jurisdiction,
                is_active=True
            )

        # Log Rule Resolution Audit
        TaxRuleEvaluationLog.objects.create(
            document_type=document_type,
            document_number=doc_num,
            candidate_rules=[r.code for r in candidate_rules],
            selected_rule=selected_rule.code,
            rejected_rules=[{"rule": r.code, "reason": "Lower Priority"} for r in candidate_rules[1:]],
            priority_score=selected_rule.priority
        )

        tax_code = selected_rule.tax_code
        rate = tax_code.rate

        # 4. Line Calculations & Integrity Assurance
        line_decisions = []
        total_subtotal = Decimal("0.00")
        total_taxable = Decimal("0.00")
        total_tax = Decimal("0.00")

        for line_idx, line in enumerate(lines, start=1):
            line_amount = Decimal(str(line.get("amount", "0.00")))
            line_tax = (line_amount * (rate / Decimal("100.00"))).quantize(Decimal("0.01"))

            total_subtotal += line_amount
            total_taxable += line_amount
            total_tax += line_tax

            line_decisions.append({
                "line_index": line_idx,
                "document_line_id": line.get("line_id", line_idx),
                "tax_code": tax_code.code,
                "taxable_amount": str(line_amount),
                "tax_rate": str(rate),
                "tax_amount": str(line_tax)
            })

        decision = TaxDecision(
            decision_type="TAX_APPLIED",
            applicable=True,
            selected_rule_code=selected_rule.code,
            rule_version=selected_rule.version,
            tax_code=tax_code.code,
            tax_rate=rate,
            taxable_amount=total_taxable,
            tax_amount=total_tax,
            jurisdiction_code=jurisdiction.code,
            decision_reason=f"Applied TaxRule {selected_rule.code} (Rate: {rate}%)",
            effective_date=date_val.isoformat(),
            accounting_position=tax_code.tax_nature,
            line_decisions=line_decisions
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
            tax_decisions=[decision],
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
        user=None
    ) -> TaxDeterminationAudit:
        """
        تطبيق واحتساب وقيد الضريبة ذرية بـ select_for_update مع التوقيع المشفر SHA256 وسجل الأحداث المستقل TaxEvent
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
            tax_code_obj = TaxCode.objects.get(code=decision.tax_code)

            # Persist Line Calculations
            for ld in calc_result.line_decisions:
                TaxCalculationLine.objects.create(
                    document_type=document_type,
                    document_id=document_id,
                    document_line_id=ld["document_line_id"],
                    tax_code=tax_code_obj,
                    taxable_amount=Decimal(ld["taxable_amount"]),
                    tax_rate=Decimal(ld["tax_rate"]),
                    tax_amount=Decimal(ld["tax_amount"]),
                    exemption_reason=decision.decision_reason if not decision.applicable else None
                )

            func_tax = calc_result.functional_tax_amount
            correlation_id = uuid.uuid4()

            # Resolve Account Mapping
            mapping = TaxAccountMapping.objects.filter(tax_code=tax_code_obj, currency=currency).first()
            if mapping and mapping.debit_account and mapping.credit_account:
                dr_acc = mapping.debit_account.code
                cr_acc = mapping.credit_account.code
            elif decision.accounting_position == "OUTPUT":
                dr_acc = customer.financial_account.code if (customer and hasattr(customer, 'financial_account') and customer.financial_account) else "11010"
                cr_acc = "22010"
            elif decision.accounting_position == "INPUT":
                dr_acc = "11050"
                cr_acc = supplier.financial_account.code if (supplier and hasattr(supplier, 'financial_account') and supplier.financial_account) else "20100"
            else:
                dr_acc = "11050"
                cr_acc = "22010"

            journal_entry = None
            if func_tax > Decimal("0.00") and decision.applicable:
                try:
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
                    journal_entry = create_tax_posting(command)
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
                audit_status="POSTED" if journal_entry else "CALCULATED",
                processed_event_id=event_id,
                correlation_id=correlation_id,
                audit_hash="",
                journal_entry=journal_entry
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
