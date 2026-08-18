import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone

from client.models import Customer
from product.models.product_core import Product
from product.models.stock_management import Warehouse
from sale.models.quotation import Quotation
from sale.models.sales_models import (
    SalesOrder,
    SalesOrderItem,
    DeliveryNote,
    DeliveryNoteItem,
    SalesInvoice,
    SalesInvoiceItem,
)
from sale.services.pricing_service import PricingService
from financial.services.approval_service import ApprovalService
from governance.services.movement_service import MovementService
from client.services.customer_subledger_service import CustomerSubledgerService
from financial.services.ledger_core_service import LedgerCoreService
from financial.exceptions import FinancialCoreError

logger = logging.getLogger("sale.services.sales_service")


class SalesService:
    """
    FIN-SAL-001: Enterprise Sales Document Lifecycle Orchestrator
    منسق دورة مستندات المبيعات الحاكم المحاسبي والتشغيلي
    """

    @classmethod
    def create_sales_order(
        cls,
        customer: Customer,
        warehouse: Warehouse,
        order_date,
        items_data: List[Dict[str, Any]],
        user,
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        price_list_id: Optional[int] = None,
        quotation_reference: Optional[Quotation] = None
    ) -> SalesOrder:
        """
        إنشاء أمر بيع وتطبيق لقطات التسعير المحوكمة والتقييم لموافقات الاعتماد
        """
        with transaction.atomic():
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            order_num = SequenceService.get_next_number(
                DocumentType.SALES_ORDER,
                warehouse=warehouse,
                date=order_date,
            )

            so = SalesOrder.objects.create(
                order_number=order_num,
                customer=customer,
                quotation_reference=quotation_reference,
                warehouse=warehouse,
                order_date=order_date,
                currency=currency,
                exchange_rate=exchange_rate,
                price_list_id=price_list_id,
                status="DRAFT",
                created_by=user
            )

            total_val = Decimal("0.00")
            for item in items_data:
                product = item["product"]
                qty = Decimal(str(item["ordered_qty"]))

                # Get governed price snapshot from PricingService
                price_snap = PricingService.get_sales_price(
                    product_id=product.id,
                    customer_id=customer.id,
                    quantity=qty,
                    price_list_id=price_list_id,
                    as_of_date=order_date,
                    currency=currency
                )

                price = Decimal(str(item.get("unit_price", price_snap["base_price"])))
                disc = Decimal(str(item.get("discount_percentage", price_snap["discount_percentage"])))

                # Serialize price_snap for JSONField compatibility
                price_snap_serializable = {
                    k: (str(v) if isinstance(v, Decimal) else v)
                    for k, v in price_snap.items()
                }

                line_total = (qty * price * (Decimal("1.00") - (disc / Decimal("100.00")))).quantize(Decimal("0.01"))
                total_val += line_total

                SalesOrderItem.objects.create(
                    sales_order=so,
                    product=product,
                    ordered_qty=qty,
                    delivered_qty=Decimal("0.0000"),
                    invoiced_qty=Decimal("0.0000"),
                    unit_price=price,
                    discount_percentage=disc,
                    line_total=line_total,
                    price_snapshot=price_snap_serializable
                )

            func_val = (total_val * exchange_rate).quantize(Decimal("0.01"))
            so.total_amount = total_val
            so.functional_amount = func_val

            # Credit Governance Check via CreditDecision Engine (FIN-AR-001 v6.0)
            from client.services.credit_exposure_service import CreditExposureService
            from client.services.credit_decision import CreditDecisionType

            credit_decision = CreditExposureService.evaluate_credit_check(customer.id, total_val, currency)

            if credit_decision.decision == CreditDecisionType.BLOCKED:
                raise FinancialCoreError(credit_decision.reason)

            elif credit_decision.decision == CreditDecisionType.REQUIRES_APPROVAL:
                # Trigger Enterprise Approval Request for Credit Override (FIN-CORE-017)
                app_req = ApprovalService.check_and_create_approval_request(
                    module="CREDIT",
                    reference_id=so.id,
                    amount=func_val,
                    currency=currency,
                    user=user
                )
                so.status = "PENDING_APPROVAL"
                so.approval_request = app_req

            else:
                # Trigger Enterprise Approval Workflow Engine for Sales Amount (FIN-CORE-017)
                app_req = ApprovalService.check_and_create_approval_request(
                    module="SALES",
                    reference_id=so.id,
                    amount=func_val,
                    currency=currency,
                    user=user
                )
                if app_req:
                    so.status = "PENDING_APPROVAL"
                    so.approval_request = app_req
                else:
                    so.status = "APPROVED"
                    # Reserve Inventory Lines (FIN-SAL-003)
                    from product.services.inventory_reservation_service import InventoryReservationService
                    InventoryReservationService.reserve_sales_order_lines(so.id, user)

            so.save()

            logger.info(f"Sales Order #{so.order_number} created for customer {customer.name} (Amount: {total_val} {currency}, Status: {so.status}).")
            return so

    @classmethod
    def approve_sales_order(cls, so_id: int, user) -> SalesOrder:
        """
        اعتماد أمر البيع عبر محرك الاعتمادات المؤسسي FIN-CORE-017
        """
        with transaction.atomic():
            so = SalesOrder.objects.select_for_update().get(pk=so_id)
            if so.status not in ["DRAFT", "PENDING_APPROVAL"]:
                raise FinancialCoreError(f"Cannot approve Sales Order #{so.order_number} in status {so.status}.")

            if so.approval_request:
                ApprovalService.approve_request(so.approval_request.id, user, "Sales Order Approved")

            so.status = "APPROVED"
            so.save()
            logger.info(f"Sales Order #{so.order_number} approved.")
            return so

    @classmethod
    def deliver_goods(
        cls,
        so_id: int,
        delivery_date,
        items_data: List[Dict[str, Any]],
        user
    ) -> DeliveryNote:
        """
        تسليم البضاعة وإصدار إذن التسليم المخزني وتمرير الحركة عبر MovementService
        القيد المحاسبي للتكلفة: Dr. 50100 COGS Control / Cr. 10400 Inventory Asset
        """
        with transaction.atomic():
            so = SalesOrder.objects.select_for_update().get(pk=so_id)
            if so.status not in ["APPROVED", "CONFIRMED", "PARTIALLY_DELIVERED"]:
                raise FinancialCoreError(f"Cannot issue delivery note for Sales Order #{so.order_number} in status {so.status}.")

            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            deliv_num = SequenceService.get_next_number(
                DocumentType.DELIVERY_NOTE,
                warehouse=so.warehouse,
                date=delivery_date,
            )

            dn = DeliveryNote.objects.create(
                delivery_number=deliv_num,
                sales_order=so,
                customer=so.customer,
                warehouse=so.warehouse,
                delivery_date=delivery_date,
                status="DELIVERED",
                created_by=user
            )

            total_cogs_value = Decimal("0.00")

            for item in items_data:
                so_item = SalesOrderItem.objects.select_for_update().get(pk=item["so_item_id"])
                deliv_qty = Decimal(str(item["delivered_qty"]))

                if deliv_qty > (so_item.ordered_qty - so_item.delivered_qty):
                    raise FinancialCoreError(f"Delivered qty {deliv_qty} exceeds remaining qty on SO item #{so_item.id}.")

                # Route movement through MovementService instance
                stock_mvmt = MovementService().process_movement(
                    product_id=so_item.product.id,
                    quantity_change=-deliv_qty,
                    movement_type="out",
                    source_reference=f"DN-{dn.id}",
                    idempotency_key=f"DN-STK-{dn.id}-{so_item.id}",
                    user=user,
                    unit_cost=so_item.product.cost_price,
                    warehouse_id=so.warehouse.id
                )

                item_cogs = (deliv_qty * stock_mvmt.unit_cost).quantize(Decimal("0.01"))
                total_cogs_value += item_cogs

                DeliveryNoteItem.objects.create(
                    delivery_note=dn,
                    so_item=so_item,
                    delivered_qty=deliv_qty,
                    unit_cost=stock_mvmt.unit_cost
                )

                so_item.delivered_qty += deliv_qty
                so_item.save()

            # COGS Accounting Entry via AccountingGateway: Dr. 50100 COGS / Cr. 10400 Inventory
            lines_data = [
                {"account_code": "50100", "debit": total_cogs_value, "credit": Decimal("0.00"), "description": f"COGS Debit for DN #{dn.delivery_number}"},
                {"account_code": "10400", "debit": Decimal("0.00"), "credit": total_cogs_value, "description": f"Inventory Credit for DN #{dn.delivery_number}"}
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=delivery_date,
                description=f"COGS Entry for Delivery Note #{dn.delivery_number}",
                reference=f"DN-{dn.id}",
                entry_type="inventory",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)

            dn.journal_entry = journal_entry
            dn.save()

            # Consume Inventory Reservation (FIN-SAL-003)
            from product.services.inventory_reservation_service import InventoryReservationService
            InventoryReservationService.consume_reservation_for_delivery(so.id, items_data, user)

            # Update SO Status
            all_items = so.items.all()
            if all(i.delivered_qty >= i.ordered_qty for i in all_items):
                so.status = "FULLY_DELIVERED"
            else:
                so.status = "PARTIALLY_DELIVERED"
            so.save()

            logger.info(f"Delivery Note #{dn.delivery_number} posted with COGS Value={total_cogs_value} EGP.")
            return dn

    @classmethod
    def create_sales_invoice(
        cls,
        so_id: int,
        delivery_note_id: Optional[int],
        invoice_date,
        due_date,
        items_data: List[Dict[str, Any]],
        user
    ) -> SalesInvoice:
        """
        إصدار فاتورة المبيعات وتوليد قيد الإيراد (IFRS 15 Revenue Trigger)
        القيد المحاسبي: Dr. 11010 Customer AR / Cr. 40100 Sales Revenue
        تسجيل المعاملة المفتوحة في CustomerSubledgerService
        """
        with transaction.atomic():
            so = SalesOrder.objects.select_for_update().get(pk=so_id)
            dn = DeliveryNote.objects.get(pk=delivery_note_id) if delivery_note_id else None

            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            inv_num = SequenceService.get_next_number(
                DocumentType.SALES_INVOICE,
                warehouse=so.warehouse,
                date=invoice_date,
            )

            inv = SalesInvoice.objects.create(
                invoice_number=inv_num,
                sales_order=so,
                delivery_note=dn,
                customer=so.customer,
                invoice_date=invoice_date,
                due_date=due_date,
                currency=so.currency,
                exchange_rate=so.exchange_rate,
                status="POSTED",
                created_by=user
            )

            total_inv_val = Decimal("0.00")

            for item in items_data:
                so_item = SalesOrderItem.objects.select_for_update().get(pk=item["so_item_id"])
                dn_item = DeliveryNoteItem.objects.get(pk=item["dn_item_id"]) if "dn_item_id" in item else None
                billed_qty = Decimal(str(item["billed_qty"]))
                price = Decimal(str(item.get("unit_price", so_item.unit_price)))

                line_total = (billed_qty * price).quantize(Decimal("0.01"))
                total_inv_val += line_total

                SalesInvoiceItem.objects.create(
                    sales_invoice=inv,
                    dn_item=dn_item,
                    so_item=so_item,
                    billed_qty=billed_qty,
                    unit_price=price,
                    line_total=line_total
                )

                so_item.invoiced_qty += billed_qty
                so_item.save()

            func_val = (total_inv_val * so.exchange_rate).quantize(Decimal("0.01"))
            inv.total_amount = total_inv_val
            inv.functional_amount = func_val

            # Accounting Entry via AccountingGateway: Dr. 11010 Customer AR / Cr. 40100 Revenue (or 22010 Deferred Revenue if pre-delivery)
            cust_account_code = so.customer.financial_account.code if so.customer.financial_account else "11010"
            revenue_account = "40100" if dn else "22010_UNEARNED_REV"
            revenue_desc = f"Sales Revenue Credit Invoice #{inv.invoice_number}" if dn else f"Deferred Revenue Credit Invoice #{inv.invoice_number}"

            lines_data = [
                {"account_code": cust_account_code, "debit": func_val, "credit": Decimal("0.00"), "description": f"Customer AR Debit Invoice #{inv.invoice_number}"},
                {"account_code": revenue_account, "debit": Decimal("0.00"), "credit": func_val, "description": revenue_desc}
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=invoice_date,
                description=f"Sales Revenue Entry for Invoice #{inv.invoice_number}",
                reference=f"INV-{inv.id}",
                entry_type="automatic",
                created_by=user,
                lines_data=lines_data
            )
            journal_entry = LedgerCoreService.post_entry(draft_entry.id, user=user)
            inv.journal_entry = journal_entry
            inv.save()

            # Create IFRS 15 Revenue Recognition Schedules (FIN-AR-002)
            from financial.services.revenue_recognition_service import RevenueRecognitionService
            for inv_item in inv.items.all():
                RevenueRecognitionService.create_schedule_for_invoice_item(inv_item.id, user=user)

            # Apply Tax Determination & Audit Posting (FIN-TAX-001)
            from financial.services.tax_service import TaxDeterminationService
            tax_lines = [{"line_id": item.id, "amount": item.line_total} for item in inv.items.all()]
            TaxDeterminationService.apply_tax_posting(
                document_type="SalesInvoice",
                document_id=inv.id,
                document_number=inv.invoice_number,
                customer=so.customer,
                lines=tax_lines,
                currency=so.currency,
                exchange_rate=so.exchange_rate,
                user=user
            )

            # Register Open Item in CustomerSubledgerService (FIN-AR-003)
            CustomerSubledgerService.register_open_item_transaction(
                customer=so.customer,
                transaction_type="INVOICE",
                transaction_number=inv.invoice_number,
                issue_date=invoice_date,
                due_date=due_date,
                currency=so.currency,
                foreign_amount=total_inv_val,
                exchange_rate=so.exchange_rate,
                functional_amount=func_val,
                journal_entry=journal_entry
            )

            # Update SO Invoiced Status
            all_items = so.items.all()
            if all(i.invoiced_qty >= i.ordered_qty for i in all_items):
                so.status = "INVOICED"
            else:
                so.status = "PARTIALLY_INVOICED"
            so.save()

            logger.info(f"Sales Invoice #{inv.invoice_number} created & posted for customer {so.customer.name} (Amount: {func_val} EGP).")
            return inv

    @classmethod
    def create_fast_sale(
        cls,
        customer: Customer,
        warehouse: Warehouse,
        order_date,
        items_data: List[Dict[str, Any]],
        user,
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        price_list_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Mode 1: Fast / SME Direct Sales Mode
        ينفذ دورة العمل الحاكمة بالكامل تحت المظلة:
        create_sales_order -> validate_credit_limit -> deliver_goods -> create_sales_invoice
        """
        with transaction.atomic():
            so = cls.create_sales_order(
                customer=customer,
                warehouse=warehouse,
                order_date=order_date,
                items_data=items_data,
                user=user,
                currency=currency,
                exchange_rate=exchange_rate,
                price_list_id=price_list_id
            )

            if so.status == "PENDING_APPROVAL":
                raise FinancialCoreError(f"Fast sale blocked for customer {customer.name}: Requires credit or sales amount approval.")

            # Deliver Goods
            deliv_items = [
                {"so_item_id": item.id, "delivered_qty": item.ordered_qty}
                for item in so.items.all()
            ]
            dn = cls.deliver_goods(so_id=so.id, delivery_date=order_date, items_data=deliv_items, user=user)

            # Issue & Post Sales Invoice
            inv_items = [
                {"so_item_id": item.id, "dn_item_id": dn.items.filter(so_item=item).first().id, "billed_qty": item.ordered_qty, "unit_price": item.unit_price}
                for item in so.items.all()
            ]
            inv = cls.create_sales_invoice(
                so_id=so.id,
                delivery_note_id=dn.id,
                invoice_date=order_date,
                due_date=order_date,
                items_data=inv_items,
                user=user
            )

            so.refresh_from_db()

            return {
                "sales_order": so,
                "delivery_note": dn,
                "sales_invoice": inv
            }
