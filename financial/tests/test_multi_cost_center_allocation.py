import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.cost_center import CostCenter
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryLineCostAllocation, AccountingPeriod
from financial.services.ledger_core_service import LedgerCoreService

User = get_user_model()

@pytest.mark.django_db
class TestMultiCostCenterAllocation:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user, _ = User.objects.get_or_create(username='admin', defaults={'is_superuser': True})
        
        # Account types
        self.asset_type, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'أصول', 'nature': 'DEBIT', 'category': 'asset'})
        self.expense_type, _ = AccountType.objects.get_or_create(code='EXPENSE', defaults={'name': 'مصروفات', 'nature': 'DEBIT', 'category': 'expense'})
        
        # Accounts
        self.cash_account, _ = ChartOfAccounts.objects.get_or_create(code='10100', defaults={'name': 'النقدية بالخزينة', 'account_type': self.asset_type, 'is_active': True})
        self.rent_account, _ = ChartOfAccounts.objects.get_or_create(code='50100', defaults={'name': 'مصروف الإيجار', 'account_type': self.expense_type, 'is_active': True})
        
        # Cost Centers
        self.cc_hq, _ = CostCenter.objects.get_or_create(code='CC-HQ', defaults={'name': 'المقر الرئيسي', 'is_active': True})
        self.cc_alex, _ = CostCenter.objects.get_or_create(code='CC-ALEX', defaults={'name': 'فرع الإسكندرية', 'is_active': True})
        
        today = timezone.now().date()
        self.fiscal_year, _ = FiscalYear.objects.get_or_create(
            name=f"السنة المالية {today.year}",
            defaults={
                'start_date': today.replace(month=1, day=1),
                'end_date': today.replace(month=12, day=31),
                'status': 'open'
            }
        )
        
        self.period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=self.fiscal_year,
            period_number=today.month,
            defaults={
                'name': f"فترة {today.month}",
                'start_date': today.replace(day=1),
                'end_date': today.replace(day=28),
                'status': 'open'
            }
        )

    def test_create_journal_entry_with_multi_cost_center_allocation(self):
        """اختبار إنشاء وتأمين قيد بأسطر ذات توزيع فرعي لمراكز التكلفة (60% و 40%)"""
        lines_data = [
            {
                "account_code": self.rent_account.code,
                "debit": Decimal("10000.00"),
                "credit": Decimal("0.00"),
                "description": "إيجار المقرات الموزع",
                "cost_allocations": [
                    {"cost_center_id": self.cc_hq.id, "percentage": Decimal("60.00"), "amount": Decimal("6000.00"), "foreign_amount": Decimal("0.00")},
                    {"cost_center_id": self.cc_alex.id, "percentage": Decimal("40.00"), "amount": Decimal("4000.00"), "foreign_amount": Decimal("0.00")},
                ]
            },
            {
                "account_code": self.cash_account.code,
                "debit": Decimal("0.00"),
                "credit": Decimal("10000.00"),
                "description": "سداد نقدية الخزينة",
                "cost_center": None
            }
        ]

        draft_entry = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description='قيد توزيع إيجار',
            reference='REF-ALLOC-001',
            entry_type='manual',
            created_by=self.user,
            lines_data=lines_data
        )

        assert draft_entry.status == 'draft'
        assert draft_entry.lines.count() == 2

        rent_line = draft_entry.lines.get(account=self.rent_account)
        assert rent_line.cost_center is None  # Exclusivity Rule
        assert rent_line.cost_allocations.count() == 2

        alloc_hq = rent_line.cost_allocations.get(cost_center=self.cc_hq)
        assert alloc_hq.percentage == Decimal("60.00")
        assert alloc_hq.amount == Decimal("6000.00")

        alloc_alex = rent_line.cost_allocations.get(cost_center=self.cc_alex)
        assert alloc_alex.percentage == Decimal("40.00")
        assert alloc_alex.amount == Decimal("4000.00")

    def test_post_and_reverse_multi_cost_center_journal_entry(self):
        """اختبار ترحيل وعكس القيد متعدد مراكز التكلفة وتنسيق حصص التوزيع الفرعي"""
        lines_data = [
            {
                "account_code": self.rent_account.code,
                "debit": Decimal("5000.00"),
                "credit": Decimal("0.00"),
                "description": "مصروف تسويق موزع",
                "cost_allocations": [
                    {"cost_center_id": self.cc_hq.id, "percentage": Decimal("50.00"), "amount": Decimal("2500.00"), "foreign_amount": Decimal("0.00")},
                    {"cost_center_id": self.cc_alex.id, "percentage": Decimal("50.00"), "amount": Decimal("2500.00"), "foreign_amount": Decimal("0.00")},
                ]
            },
            {
                "account_code": self.cash_account.code,
                "debit": Decimal("0.00"),
                "credit": Decimal("5000.00"),
                "description": "سداد الخزينة",
                "cost_center": None
            }
        ]

        draft_entry = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description='قيد مصروف تسويق',
            reference='REF-ALLOC-002',
            entry_type='manual',
            created_by=self.user,
            lines_data=lines_data
        )

        posted_entry = LedgerCoreService.post_entry(
            entry_id=draft_entry.id,
            user=self.user
        )
        assert posted_entry.status == 'posted'

        # العكس المحاسبي الحاكم
        reversal_entry = LedgerCoreService.reverse_entry(
            entry_id=posted_entry.id,
            user=self.user,
            reversal_reason='تعديل التوزيع المحاسبي'
        )

        assert reversal_entry.status == 'posted'
        assert reversal_entry.lines.count() == 2

        reversed_rent_line = reversal_entry.lines.get(account=self.rent_account)
        assert reversed_rent_line.credit == Decimal("5000.00")
        assert reversed_rent_line.cost_allocations.count() == 2

    def test_manual_journal_entry_create_view_with_multi_allocation(self, client):
        """اختبار تقديم طلب POST لشاشة القيد اليدوي بأسطر ذات توزيع فرعي بـ JSON"""
        import json
        from django.urls import reverse

        client.force_login(self.user)

        alloc_data = [
            {"cost_center_id": self.cc_hq.id, "percentage": 70, "amount": 7000},
            {"cost_center_id": self.cc_alex.id, "percentage": 30, "amount": 3000}
        ]

        post_data = {
            'entry_date': timezone.now().strftime('%Y-%m-%d'),
            'description': 'قيد مصاريف عامة موزع',
            'entry_currency': 'EGP',
            'exchange_rate': '1.000000',
            'accounts[]': [str(self.rent_account.id), str(self.cash_account.id)],
            'debits[]': ['10000.00', '0.00'],
            'credits[]': ['0.00', '10000.00'],
            'line_descriptions[]': ['إيجار المقرات', 'سداد نقدي'],
            'cost_centers[]': ['MULTI', ''],
            'line_allocations_json[]': [json.dumps(alloc_data), '']
        }

        response = client.post(reverse('financial:manual_journal_entry_create'), post_data)
        assert response.status_code == 302  # Redirect on success

        created_entry = JournalEntry.objects.filter(description='قيد مصاريف عامة موزع').first()
        assert created_entry is not None

        rent_line = created_entry.lines.get(account=self.rent_account)
        assert rent_line.cost_center is None  # Exclusivity rule
        assert rent_line.cost_allocations.count() == 2

        alloc_hq = rent_line.cost_allocations.get(cost_center=self.cc_hq)
        assert alloc_hq.percentage == Decimal("70.00")
        assert alloc_hq.amount == Decimal("7000.00")

        alloc_alex = rent_line.cost_allocations.get(cost_center=self.cc_alex)
        assert alloc_alex.percentage == Decimal("30.00")
        assert alloc_alex.amount == Decimal("3000.00")

    def test_manual_journal_entry_create_view_guards(self, client):
        """اختبار منع التوزيع على حساب الميزانية العمومية ورسائل الخطأ"""
        import json
        from django.urls import reverse

        client.force_login(self.user)

        alloc_data = [
            {"cost_center_id": self.cc_hq.id, "percentage": 50, "amount": 2500},
            {"cost_center_id": self.cc_alex.id, "percentage": 50, "amount": 2500}
        ]

        # محاولة التوزيع على حساب أصول (cash_account)
        post_data = {
            'entry_date': timezone.now().strftime('%Y-%m-%d'),
            'description': 'محاولة توزيع خاطئة',
            'entry_currency': 'EGP',
            'exchange_rate': '1.000000',
            'accounts[]': [str(self.cash_account.id), str(self.rent_account.id)],
            'debits[]': ['5000.00', '0.00'],
            'credits[]': ['0.00', '5000.00'],
            'line_descriptions[]': ['نقدية خزانة', 'إيجار'],
            'cost_centers[]': ['MULTI', ''],
            'line_allocations_json[]': [json.dumps(alloc_data), '']
        }

        response = client.post(reverse('financial:manual_journal_entry_create'), post_data)
        assert response.status_code == 302
        
        # التأكد من عدم إنشاء القيد بسبب حوكمة منع توزيع حسابات الميزانية
        created_entry = JournalEntry.objects.filter(description='محاولة توزيع خاطئة').first()
        assert created_entry is None


