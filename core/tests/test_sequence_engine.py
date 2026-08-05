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
        self.currency = Currency.objects.create(code="EGP", name="جنيه مصري", symbol="ج.م")

    def test_standard_sequence_generation(self):
        """اختبار التوليد القياسي للأرقام التسلسلية للمستندات المختلفة"""
        so_num1 = SequenceService.get_next_number(
            DocumentType.SALES_ORDER, warehouse=self.warehouse_main, user=self.user
        )
        so_num2 = SequenceService.get_next_number(
            DocumentType.SALES_ORDER, warehouse=self.warehouse_main, user=self.user
        )

        year = timezone.now().year
        self.assertEqual(so_num1, f"SO-{year}-00001")
        self.assertEqual(so_num2, f"SO-{year}-00002")

        # Verify audit trail creation
        audit = DocumentSequenceAudit.objects.filter(document_number=so_num1).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.event_type, "GENERATED")
        self.assertEqual(audit.prefix_snapshot, "SO")
        self.assertEqual(audit.sequence_number, 1)

    def test_multi_warehouse_isolation(self):
        """اختبار استقلال الترقيم والتسلسل بين المخازن/الفروع المختلفة"""
        year = timezone.now().year
        num_main = SequenceService.get_next_number(
            DocumentType.DELIVERY_NOTE, warehouse=self.warehouse_main, user=self.user
        )
        num_alex = SequenceService.get_next_number(
            DocumentType.DELIVERY_NOTE, warehouse=self.warehouse_alex, user=self.user
        )

        self.assertEqual(num_main, f"DEL-{year}-00001")
        self.assertEqual(num_alex, f"DEL-{year}-00001")

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
        self.assertTrue(entry_number.startswith("JE-") or entry_number.startswith("GL-"))

    def test_batch_numbers_generation(self):
        """اختبار التوليد الجماعي لأرقام دفعة واحدة"""
        numbers = SequenceService.get_batch_numbers(
            DocumentType.SALES_INVOICE, count=5
        )
        self.assertEqual(len(numbers), 5)
        self.assertEqual(len(set(numbers)), 5)


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
