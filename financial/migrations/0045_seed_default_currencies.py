from decimal import Decimal
from django.db import migrations
from django.utils import timezone


def seed_default_currencies(apps, schema_editor):
    Currency = apps.get_model("financial", "Currency")
    ExchangeRate = apps.get_model("financial", "ExchangeRate")

    # Only seed if no functional currency currently exists in the system
    if not Currency.objects.filter(is_functional=True).exists():
        egp, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={
                "name": "جنيه مصري",
                "symbol": "ج.م",
                "decimal_places": 2,
                "is_functional": True,
                "is_active": True,
            },
        )
        usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={
                "name": "دولار أمريكي",
                "symbol": "$",
                "decimal_places": 2,
                "is_functional": False,
                "is_active": True,
            },
        )

        # Seed initial exchange rate between USD and EGP to avoid 1.0 fallback
        ExchangeRate.objects.get_or_create(
            from_currency=usd,
            to_currency=egp,
            effective_date=timezone.now().date(),
            defaults={
                "rate": Decimal("50.000000"),
                "source": "INITIAL_SEED",
            },
        )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("financial", "0044_reconciliationissue"),
    ]

    operations = [
        migrations.RunPython(seed_default_currencies, reverse_code=reverse_seed),
    ]
