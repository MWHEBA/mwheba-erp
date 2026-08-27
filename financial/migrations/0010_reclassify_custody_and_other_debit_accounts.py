from django.db import migrations


def reclassify_custody_and_other_debit_accounts(apps, schema_editor):
    AccountType = apps.get_model("financial", "AccountType")
    ChartOfAccounts = apps.get_model("financial", "ChartOfAccounts")

    # 1. Ensure CURRENT_ASSET account type exists
    current_asset_type = AccountType.objects.filter(code="CURRENT_ASSET").first()
    if not current_asset_type:
        asset_parent = AccountType.objects.filter(code="ASSET").first()
        current_asset_type = AccountType.objects.create(
            code="CURRENT_ASSET",
            name="الأصول المتداولة",
            name_en="Current Assets",
            is_system_type=True,
            category="asset",
            nature="debit",
            parent=asset_parent,
            level=2,
            is_active=True,
        )

    # 2. Ensure OTHER_DEBIT account type exists
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

    # 3. Find Current Assets parent account (11 or 10100/10000)
    current_assets_parent = ChartOfAccounts.objects.filter(code="11").first()
    if not current_assets_parent:
        current_assets_parent = ChartOfAccounts.objects.filter(code__in=["10000", "1"]).first()

    # 4. Clean up any orphan accounts created at root level
    ChartOfAccounts.objects.filter(code__in=["10500", "10510", "10511"]).delete()

    # 5. Create/update 114 (أرصدة مدينة أخرى) under 11
    acc_114, _ = ChartOfAccounts.objects.get_or_create(
        code="114",
        defaults={
            "name": "أرصدة مدينة أخرى",
            "name_en": "Other Debit Balances",
            "account_type": other_debit_type,
            "parent": current_assets_parent,
            "level": 3 if current_assets_parent and current_assets_parent.code == "11" else 2,
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
    if acc_114 and current_assets_parent and acc_114.parent != current_assets_parent:
        acc_114.parent = current_assets_parent
        acc_114.level = 3 if current_assets_parent.code == "11" else 2
        acc_114.save(update_fields=["parent", "level"])

    # 6. Re-parent existing 114xx accounts under 114
    ChartOfAccounts.objects.filter(code__in=["11410", "11420", "11430", "11440"]).update(
        parent=acc_114,
        level=4 if current_assets_parent and current_assets_parent.code == "11" else 3,
    )

    # 7. Create/update 11450 (عهد الموظفين المؤقتة)
    acc_11450, _ = ChartOfAccounts.objects.get_or_create(
        code="11450",
        defaults={
            "name": "عهد الموظفين المؤقتة",
            "name_en": "Temporary Employee Custodies",
            "account_type": other_debit_type,
            "parent": acc_114,
            "level": 4 if current_assets_parent and current_assets_parent.code == "11" else 3,
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

    # 8. Create/update 11451 (عهدة مشتريات عامة)
    ChartOfAccounts.objects.get_or_create(
        code="11451",
        defaults={
            "name": "عهدة مشتريات عامة",
            "name_en": "General Purchase Custody",
            "account_type": other_debit_type,
            "parent": acc_11450,
            "level": 5 if current_assets_parent and current_assets_parent.code == "11" else 4,
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

    # 9. Create/update 11460 (سلف الموظفين الشخصية)
    ChartOfAccounts.objects.get_or_create(
        code="11460",
        defaults={
            "name": "سلف الموظفين الشخصية",
            "name_en": "Employee Advances",
            "account_type": other_debit_type,
            "parent": acc_114,
            "level": 4 if current_assets_parent and current_assets_parent.code == "11" else 3,
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

    # 10. Update 11130 under 111 (Petty cash funds)
    acc_11130 = ChartOfAccounts.objects.filter(code="11130").first()
    if acc_11130:
        acc_11130.name = "صناديق المصروفات النثرية المستديمة"
        acc_11130.is_cash_account = True
        acc_11130.save(update_fields=["name", "is_cash_account"])


def reverse_reclassification(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0009_alter_journalentry_entry_type_and_more"),
    ]

    operations = [
        migrations.RunPython(
            reclassify_custody_and_other_debit_accounts,
            reverse_reclassification,
        ),
    ]
