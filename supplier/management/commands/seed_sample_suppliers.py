# -*- coding: utf-8 -*-
import json
import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from users.models import User
from supplier.models import Supplier, SupplierType
from customer.models import PaymentTerm
from financial.models import Currency
from supplier.services.supplier_service import SupplierService


class Command(BaseCommand):
    help = "إضافة 3 موردين نموذجيين ببيانات كاملة 100% ومطابقة للهوية الضريبية والتسهيلات"

    def handle(self, *args, **options):
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        func_currency = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()

        terms_map = {}
        term_names = {
            "CASH": "سداد فوري (نقدي)",
            "NET15": "أجل 15 يوماً",
            "NET30": "أجل 30 يوماً",
            "NET60": "أجل 60 يوماً",
        }
        days_map = {"CASH": 0, "NET15": 15, "NET30": 30, "NET60": 60}
        for code_t, name_t in term_names.items():
            term, _ = PaymentTerm.objects.update_or_create(
                code=code_t,
                defaults={"name": name_t, "days": days_map[code_t], "is_active": True}
            )
            terms_map[code_t] = term

        json_path = os.path.join(os.path.dirname(__file__), "seed_sample_suppliers.json")
        with open(json_path, "r", encoding="utf-8") as f:
            suppliers_data = json.load(f)

        with transaction.atomic():
            for s_data in suppliers_data:
                code = s_data["code"]
                name = s_data["name"]

                primary_type_code = s_data.get("primary_type_code", "general")
                primary_type_name = s_data.get("primary_type_name", "عام")
                primary_type, _ = SupplierType.objects.get_or_create(
                    code=primary_type_code,
                    defaults={
                        "name": primary_type_name,
                        "description": f"موردين {primary_type_name}",
                        "icon": "fas fa-boxes" if "raw" in primary_type_code else ("fas fa-tools" if "main" in primary_type_code else "fas fa-print"),
                        "color": "#198754" if "raw" in primary_type_code else "#0d6efd",
                        "is_active": True,
                    }
                )

                payment_term_code = s_data.get("payment_term_code", "CASH")
                payment_term = terms_map.get(payment_term_code)

                supplier, created = Supplier.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "entity_type": s_data.get("entity_type", "company"),
                        "primary_type": primary_type,
                        "national_id": s_data.get("national_id") or None,
                        "commercial_registry": s_data.get("commercial_registry") or None,
                        "tax_number": s_data.get("tax_number") or None,
                        "phone": s_data.get("phone", ""),
                        "secondary_phone": s_data.get("secondary_phone", ""),
                        "whatsapp": s_data.get("whatsapp", ""),
                        "email": s_data.get("email", ""),
                        "website": s_data.get("website", ""),
                        "country": s_data.get("country", "مصر"),
                        "city": s_data.get("city", "القاهرة"),
                        "address": s_data.get("address", ""),
                        "contact_person": s_data.get("contact_person", ""),
                        "default_currency": func_currency,
                        "credit_limit": Decimal(str(s_data.get("credit_limit", "0.00"))),
                        "default_payment_term": payment_term,
                        "payment_terms": payment_term.name if payment_term else "",
                        "grace_period_days": int(s_data.get("grace_period_days", 0)),
                        "bank_name": s_data.get("bank_name"),
                        "bank_account_number": s_data.get("bank_account_number"),
                        "bank_beneficiary_name": s_data.get("bank_beneficiary_name"),
                        "working_hours": s_data.get("working_hours", ""),
                        "delivery_time_days": s_data.get("delivery_time_days"),
                        "min_order_amount": Decimal(str(s_data.get("min_order_amount", "0.00"))) if s_data.get("min_order_amount") else None,
                        "supplier_rating": Decimal(str(s_data.get("supplier_rating", "5.0"))) if s_data.get("supplier_rating") else None,
                        "is_preferred": s_data.get("is_preferred", False),
                        "is_active": s_data.get("is_active", True),
                        "created_by": user,
                    }
                )

                if not supplier.financial_account:
                    SupplierService.create_financial_account_for_supplier(supplier, user=user)
                    supplier.refresh_from_db()
                else:
                    supplier.financial_account.name = f"{supplier.name} - {supplier.code}"
                    supplier.financial_account.save()

                status_msg = "Created" if created else "Updated"
                account_code = supplier.financial_account.code if supplier.financial_account else "No Account"
                self.stdout.write(self.style.SUCCESS(f"Saved Supplier: {supplier.code} - {supplier.name} (Account: {account_code})"))

        self.stdout.write(self.style.SUCCESS("All sample suppliers seeded successfully."))
