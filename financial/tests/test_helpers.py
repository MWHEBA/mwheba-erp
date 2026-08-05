from decimal import Decimal
from financial.models import JournalEntry, JournalEntryLine


def assert_journal_entry_balanced(journal_entry: JournalEntry, expected_total: Decimal = None, expected_accounts: list = None):
    """
    FIN-CORE Hardening Helper: Verifies double-entry GL balance equality and account integrity
    """
    assert journal_entry is not None, "JournalEntry instance cannot be None."
    lines = list(journal_entry.lines.all())
    assert len(lines) >= 2, f"Balanced JournalEntry #{journal_entry.id} must have at least 2 lines, found {len(lines)}."

    total_debit = sum((line.debit_amount or Decimal("0.00")) for line in lines)
    total_credit = sum((line.credit_amount or Decimal("0.00")) for line in lines)

    # 1. Assert Double-Entry Equality
    assert total_debit == total_credit, f"JournalEntry #{journal_entry.id} imbalance: Debit ({total_debit}) != Credit ({total_credit})."

    # 2. Assert Expected Total Amount
    if expected_total is not None:
        assert total_debit == expected_total, f"JournalEntry #{journal_entry.id} total mismatch: Expected {expected_total}, got {total_debit}."

    # 3. Assert Expected Account Codes Present
    if expected_accounts:
        found_accounts = [line.account.code for line in lines if line.account]
        for acc in expected_accounts:
            assert acc in found_accounts, f"JournalEntry #{journal_entry.id} missing expected account '{acc}'. Found: {found_accounts}"

    # 4. Assert Line Non-Null and Active Accounts
    for line in lines:
        assert line.account is not None, f"JournalEntryLine #{line.id} has no associated ChartOfAccounts."
        assert line.account.is_active is True, f"JournalEntryLine #{line.id} references inactive account '{line.account.code}'."
