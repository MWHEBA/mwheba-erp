from django.db import migrations


def restructure_114_hierarchy(apps, schema_editor):
    AccountType = apps.get_model("financial", "AccountType")
    ChartOfAccounts = apps.get_model("financial", "ChartOfAccounts")

    # 1. Ensure OTHER_DEBIT AccountType exists
    current_asset_type = AccountType.objects.filter(code="CURRENT_ASSET").first()
    other_debit_type, _ = AccountType.objects.get_or_create(
        code="OTHER_DEBIT",
        defaults={
            "name": "أرصدة مدينة أخرى",
            "name_en": "Other Debit Balances",
            "is_system_type": True,
            "category": "asset",
            "nature": "debit",
            "parent": current_asset_type,
            "level": 3,
            "is_active": True,
        },
    )

    # 2. Find Current Assets parent account (code 11)
    p11 = ChartOfAccounts.objects.filter(code="11").first()
    if not p11:
        p11 = ChartOfAccounts.objects.filter(code__in=["10000", "1"]).first()

    # 3. Clean up any orphan 10500 accounts created at root level
    ChartOfAccounts.objects.filter(code__in=["10500", "10510", "10511"]).delete()

    # 4. Create/update 114 (أرصدة مدينة أخرى) under 11 (Current Assets)
    acc_114, _ = ChartOfAccounts.objects.get_or_create(
        code="114",
        defaults={
            "name": "أرصدة مدينة أخرى",
            "name_en": "Other Debit Balances",
            "account_type": other_debit_type,
            "parent": p11,
            "level": 3 if p11 and p11.code == "11" else 2,
            "is_leaf": False,
            "is_bank_account": False,
            "is_cash_account": False,
            "is_reconcilable": True,
            "is_control_account": False,
            "opening_balance": 0,
            "is_active": True,
            "is_system_account": True,
        },
    )
    if acc_114 and p11 and acc_114.parent != p11:
        acc_114.parent = p11
        acc_114.level = 3 if p11.code == "11" else 2
        acc_114.save(update_fields=["parent", "level"])

    # 5. Move 114xx sub-accounts under 114
    ChartOfAccounts.objects.filter(code__in=["11410", "11420", "11430", "11440"]).update(
        parent=acc_114,
        level=4 if p11 and p11.code == "11" else 3,
    )

    # 6. Create/update 11450 (عهد الموظفين المؤقتة)
    acc_11450, _ = ChartOfAccounts.objects.get_or_create(
        code="11450",
        defaults={
            "name": "عهد الموظفين المؤقتة",
            "name_en": "Temporary Employee Custodies",
            "account_type": other_debit_type,
            "parent": acc_114,
            "level": 4 if p11 and p11.code == "11" else 3,
            "is_leaf": False,
            "is_bank_account": False,
            "is_cash_account": False,
            "is_reconcilable": True,
            "is_control_account": False,
            "opening_balance": 0,
            "is_active": True,
            "is_system_account": True,
        },
    )
    if acc_11450 and acc_11450.parent != acc_114:
        acc_11450.parent = acc_114
        acc_11450.level = 4 if p11 and p11.code == "11" else 3
        acc_11450.save(update_fields=["parent", "level"])

    # 7. Create/update 11451 (عهدة مشتريات عامة)
    acc_11451, _ = ChartOfAccounts.objects.get_or_create(
        code="11451",
        defaults={
            "name": "عهدة مشتريات عامة",
            "name_en": "General Purchase Custody",
            "account_type": other_debit_type,
            "parent": acc_11450,
            "level": 5 if p11 and p11.code == "11" else 4,
            "is_leaf": True,
            "is_bank_account": False,
            "is_cash_account": False,
            "is_reconcilable": True,
            "is_control_account": False,
            "opening_balance": 0,
            "is_active": True,
            "is_system_account": True,
        },
    )
    if acc_11451 and acc_11451.parent != acc_11450:
        acc_11451.parent = acc_11450
        acc_11451.level = 5 if p11 and p11.code == "11" else 4
        acc_11451.save(update_fields=["parent", "level"])

    # 8. Create/update 11460 (سلف الموظفين الشخصية)
    acc_11460, _ = ChartOfAccounts.objects.get_or_create(
        code="11460",
        defaults={
            "name": "سلف الموظفين الشخصية",
            "name_en": "Employee Advances",
            "account_type": other_debit_type,
            "parent": acc_114,
            "level": 4 if p11 and p11.code == "11" else 3,
            "is_leaf": True,
            "is_bank_account": False,
            "is_cash_account": False,
            "is_reconcilable": True,
            "is_control_account": False,
            "opening_balance": 0,
            "is_active": True,
            "is_system_account": True,
        },
    )
    if acc_11460 and acc_11460.parent != acc_114:
        acc_11460.parent = acc_114
        acc_11460.level = 4 if p11 and p11.code == "11" else 3
        acc_11460.save(update_fields=["parent", "level"])

    # 9. Update 11130 under 111 (Petty cash funds)
    acc_11130 = ChartOfAccounts.objects.filter(code="11130").first()
    if acc_11130:
        acc_11130.name = "صناديق المصروفات النثرية المستديمة"
        acc_11130.is_cash_account = True
        acc_11130.save(update_fields=["name", "is_cash_account"])


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0010_reclassify_custody_and_other_debit_accounts"),
    ]

    operations = [
        migrations.RunPython(
            restructure_114_hierarchy,
            reverse_func,
        ),
    ]
