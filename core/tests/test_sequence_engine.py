# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Enterprise Sequence Engine Comprehensive Test Suite
Tests for:
1. Atomic Sequence Generation
2. Multi-Tenant / Multi-Warehouse Isolation
3. Legacy Seed Parsing & Offset
4. Immutability & Manual Edit Guards
5. Audit Trail & Event Logging
6. Rule Versioning & Locking
"""
import concurrent.futures
from decimal import Decimal
from datetime import date
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.models import (
    DocumentSequenceRule,
    DocumentSequenceCounter,
    DocumentSequenceAudit,
)
from core.services.sequence_service import SequenceService
from core.services.sequence_formatter import SequenceFormatter
from core.services.sequence_validator import SequenceValidator
from core.services.legacy_seed_service import LegacySequenceAnalyzer
from product.models import Warehouse
from financial.models import JournalEntry, Currency
from sale.models import Sale as SalesInvoice
try:
    from sale.models import SalesOrder
except ImportError:
    SalesOrder = None
from client.models import Customer

User = get_user_model()


class SequenceEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="seq_user", password="password123")
        self.warehouse_main = Warehouse.objects.create(name="المخزن الرئيسي", code="MAIN-WH")
        self.warehouse_alex = Warehouse.objects.create(name="مخزن الإسكندرية", code="ALEX-WH")
        self.customer = Customer.objects.create(name="عميل تجريبي", code="CUST-001")
        self.currency, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م"})

    def test_standard_sequence_generation(self):
        """اختبار التوليد القياسي للأرقام التسلسلية للمستندات المختلفة"""
        so_num1 = SequenceService.get_next_number(
            DocumentType.SALES_ORDER, warehouse=self.warehouse_main, user=self.user
        )
        so_num2 = SequenceService.get_next_number(
            DocumentType.SALES_ORDER, warehouse=self.warehouse_main, user=self.user
        )

        year_short = str(timezone.now().year)[-2:]
        self.assertEqual(so_num1, f"SO{year_short}0001")
        self.assertEqual(so_num2, f"SO{year_short}0002")

        # Verify audit trail creation
        audit = DocumentSequenceAudit.objects.filter(document_number=so_num1).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.event_type, "GENERATED")
        self.assertEqual(audit.prefix_snapshot, "SO")
        self.assertEqual(audit.sequence_number, 1)

    def test_multi_warehouse_isolation(self):
        """اختبار استقلال الترقيم والتسلسل بين المخازن/الفروع المختلفة"""
        year_short = str(timezone.now().year)[-2:]
        num_main = SequenceService.get_next_number(
            DocumentType.DELIVERY_NOTE, warehouse=self.warehouse_main, user=self.user
        )
        num_alex = SequenceService.get_next_number(
            DocumentType.DELIVERY_NOTE, warehouse=self.warehouse_alex, user=self.user
        )

        self.assertEqual(num_main, f"DEL{year_short}0001")
        self.assertEqual(num_alex, f"DEL{year_short}0001")

    def test_rule_locking_on_first_use(self):
        """اختبار قفل القاعدة تلقائياً بعد إنتاج أول رقم"""
        rule_before = DocumentSequenceRule.objects.filter(
            document_type=DocumentType.PURCHASE_ORDER, warehouse=self.warehouse_main
        ).first()
        self.assertIsNone(rule_before)

        po_num = SequenceService.get_next_number(
            DocumentType.PURCHASE_ORDER, warehouse=self.warehouse_main, user=self.user
        )
        rule_after = DocumentSequenceRule.objects.get(
            document_type=DocumentType.PURCHASE_ORDER, warehouse=self.warehouse_main
        )
        self.assertTrue(rule_after.is_locked)

    def test_legacy_seed_analyzer_parsing(self):
        """اختبار تحليل النصوص القديمة بالـ Regex لاستخراج الـ Seed الصحيح"""
        year, seq1 = LegacySequenceAnalyzer.parse_legacy_number("INV-20260803-0098")
        self.assertEqual(year, 2026)
        self.assertEqual(seq1, 98)

        year2, seq2 = LegacySequenceAnalyzer.parse_legacy_number("PO-2026-0015")
        self.assertEqual(year2, 2026)
        self.assertEqual(seq2, 15)

        year3, seq3 = LegacySequenceAnalyzer.parse_legacy_number("JE-0042")
        self.assertEqual(seq3, 42)

    def test_manual_edit_blocked_on_posted_document(self):
        """اختبار حظر تعديل الأرقام المرحّلة وتسجيل حدث MANUAL_EDIT_BLOCKED"""
        so = SalesOrder.objects.create(
            order_number="SO-2026-00001",
            order_date=date(2026, 8, 3),
            customer=self.customer,
            warehouse=self.warehouse_main,
            currency="EGP",
            status="APPROVED",
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            SequenceValidator.validate_number_immutability(
                instance=so,
                field_name="order_number",
                old_number="SO-2026-00001",
                new_number="SO-2026-99999",
                user=self.user,
            )

        audit = DocumentSequenceAudit.objects.filter(event_type="MANUAL_EDIT_BLOCKED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.old_value, "SO-2026-00001")
        self.assertEqual(audit.new_value, "SO-2026-99999")

    def test_journal_entry_generation_service(self):
        """اختبار توليد أرقام القيود المحاسبية بالصيغة JE-XXXX"""
        je = JournalEntry(
            date=date(2026, 8, 3),
            description="قيد تسوية تجريبي",
            entry_type="manual",
        )
        entry_number = je.generate_entry_number()
        self.assertTrue(entry_number.startswith("JE") or entry_number.startswith("GL") or entry_number.startswith("REV"))

    def test_batch_numbers_generation(self):
        """اختبار التوليد الجماعي لأرقام دفعة واحدة"""
        numbers = SequenceService.get_batch_numbers(
            DocumentType.SALES_INVOICE, count=5
        )
        self.assertEqual(len(numbers), 5)
        self.assertEqual(len(set(numbers)), 5)

    def test_peek_next_number_is_idempotent_and_zero_waste(self):
        """اختبار دالة المعاينة للتأكد من عدم حرق أي أرقام أو تسجيل audit"""
        from core.models import DocumentSequenceCounter, DocumentSequenceAudit

        initial_audits = DocumentSequenceAudit.objects.count()

        # Call peek 15 times
        peek_results = [
            SequenceService.peek_next_number(DocumentType.SALES_INVOICE)
            for _ in range(15)
        ]

        # All 15 calls should return identical preview string
        self.assertEqual(len(set(peek_results)), 1)
        self.assertEqual(peek_results[0], "INV260001")

        # Zero audit entries created by peek
        self.assertEqual(DocumentSequenceAudit.objects.count(), initial_audits)

        # Now actually generate one number
        actual = SequenceService.get_next_number(DocumentType.SALES_INVOICE)
        self.assertEqual(actual, "INV260001")

        # Next peek should cleanly point to next number without incrementing
        next_peek = SequenceService.peek_next_number(DocumentType.SALES_INVOICE)
        self.assertEqual(next_peek, "INV260002")

    def test_legacy_sequence_analyzer_compact_and_various_formats(self):
        """اختبار دقة محلل السجلات القديمة والمدمجة بدقة 100%"""
        from core.services.legacy_seed_service import LegacySequenceAnalyzer

        # 1. Compact format INV260009
        y1, s1 = LegacySequenceAnalyzer.parse_legacy_number("INV260009")
        self.assertEqual(y1, 2026)
        self.assertEqual(s1, 9)

        # 2. Compact format GL260001
        y2, s2 = LegacySequenceAnalyzer.parse_legacy_number("GL260001")
        self.assertEqual(y2, 2026)
        self.assertEqual(s2, 1)

        # 3. Standard dash format
        y3, s3 = LegacySequenceAnalyzer.parse_legacy_number("INV-2026-0005")
        self.assertEqual(y3, 2026)
        self.assertEqual(s3, 5)

        # 4. Full date format
        y4, s4 = LegacySequenceAnalyzer.parse_legacy_number("INV-20260803-0098")
        self.assertEqual(y4, 2026)
        self.assertEqual(s4, 98)

        # 5. Timestamp fallback format (should ignore timestamp digits)
        y5, s5 = LegacySequenceAnalyzer.parse_legacy_number("GRN-20260809205840")
        self.assertEqual(y5, 2026)
        self.assertEqual(s5, 0)

    def test_document_type_normalization_and_immunity(self):
        """اختبار مناعة تطبيع أسماء المستندات ومنع بادئة DOC"""
        # Test lowercase string mappings
        self.assertEqual(SequenceService.normalize_document_type('journal_entry'), DocumentType.JOURNAL_ENTRY)
        self.assertEqual(SequenceService.normalize_document_type('sale'), DocumentType.SALES_INVOICE)
        self.assertEqual(SequenceService.normalize_document_type('sales_order'), DocumentType.SALES_ORDER)
        self.assertEqual(SequenceService.normalize_document_type('purchase_order'), DocumentType.PURCHASE_ORDER)
        self.assertEqual(SequenceService.normalize_document_type('purchase_invoice'), DocumentType.PURCHASE_INVOICE)

        # Prefix should be GL not DOC
        prefix = SequenceService.get_default_prefix('journal_entry')
        self.assertEqual(prefix, 'GL')


class SequenceConcurrencyTestCase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="seq_conc_user", password="password123")
        self.warehouse = Warehouse.objects.create(name="مخزن الضغط", code="STRESS-WH")

    def test_atomic_concurrency_race_condition_safety(self):
        """اختبار 20 طلب متزامن للتوليد للتأكد من عدم وجود أخطاء تكرار مفاتيح"""
        generated_numbers = set()

        def generate_number():
            return SequenceService.get_next_number(
                DocumentType.SALES_INVOICE, warehouse=self.warehouse, user=self.user
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(generate_number) for _ in range(20)]
            for future in concurrent.futures.as_completed(futures):
                num = future.result()
                generated_numbers.add(num)

        # 20 distinct sequence numbers generated without duplicates
        self.assertEqual(len(generated_numbers), 20)
