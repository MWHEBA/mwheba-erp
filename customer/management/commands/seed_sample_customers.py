# -*- coding: utf-8 -*-
import json
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import User
from customer.models import Customer, CustomerCreditProfile, PaymentTerm
from financial.models import Currency
from financial.services.subledger_account_service import SubledgerAccountService


class Command(BaseCommand):
    help = "إضافة 3 عملاء نموذجيين ببيانات كاملة 100% ومطابقة للهوية الضريبية"

    def handle(self, *args, **options):
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        default_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()

        terms_map = {}
        for days in [15, 30, 60]:
            term, _ = PaymentTerm.objects.update_or_create(
                code=f"NET{days}",
                defaults={"name": f"سداد خلال {days} يوماً", "days": days, "is_active": True}
            )
            terms_map[days] = term

        json_path = Path(__file__).resolve().parent / "seed_sample_customers.json"
        with open(json_path, "r", encoding="utf-8") as f:
            customers_data = json.load(f)

        for c_data in customers_data:
            payment_term_days = c_data.pop("payment_term_days", 30)
            grace_period_days = c_data.pop("grace_period_days", 0)
            credit_status = c_data.pop("credit_status", "ACTIVE")
            risk_category = c_data.pop("risk_category", "LOW")
            review_days = c_data.pop("review_days", 180)
            credit_limit = Decimal(str(c_data.pop("credit_limit", "0")))

            customer, created = Customer.objects.update_or_create(
                code=c_data["code"],
                defaults={
                    **c_data,
                    "credit_limit": credit_limit,
                    "last_contact_date": timezone.now(),
                    "created_by": user,
                    "default_currency": default_curr
                }
            )
            
            # Update or create credit profile
            CustomerCreditProfile.objects.update_or_create(
                customer=customer,
                defaults={
                    "credit_limit": customer.credit_limit,
                    "currency": default_curr.code if default_curr else "EGP",
                    "default_payment_term": terms_map.get(payment_term_days),
                    "grace_period_days": grace_period_days,
                    "credit_status": credit_status,
                    "risk_category": risk_category,
                    "next_review_date": timezone.now().date() + timezone.timedelta(days=review_days),
                }
            )
            
            # Ensure financial account is linked and named properly
            if not customer.financial_account:
                SubledgerAccountService.get_or_create_customer_account(customer, user=user)
                customer.refresh_from_db()
            else:
                customer.financial_account.name = f"{customer.name} - {customer.code}"
                customer.financial_account.save()
            
            self.stdout.write(self.style.SUCCESS(f"Saved Customer: {customer.code} - {customer.name}"))
