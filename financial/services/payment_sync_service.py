"""
خدمة تزامن المدفوعات المتقدمة مع نظام rollback
"""
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import logging
import time
import traceback

from ..models.payment_sync import (
    PaymentSyncOperation,
    PaymentSyncLog,
    PaymentSyncRule,
    PaymentSyncError,
)
from ..services.journal_service import JournalEntryService
from ..services.redis_cache_service import financial_cache

logger = logging.getLogger(__name__)


class PaymentSyncService:
    """
    خدمة تزامن المدفوعات المتقدمة
    """

    def __init__(self):
        self.rollback_stack = []  # مكدس عمليات التراجع

    def sync_payment(
        self,
        payment_obj,
        operation_type: str = "create_payment",
        user=None,
        force_sync: bool = False,
    ) -> PaymentSyncOperation:
        """
        تزامن دفعة مع جميع الأنظمة المرتبطة
        """
        # إنشاء عملية التزامن
        sync_operation = self._create_sync_operation(payment_obj, operation_type, user)

        try:
            # بدء المعالجة
            sync_operation.start_processing()

            # الحصول على قواعد التزامن المطبقة
            applicable_rules = self._get_applicable_rules(payment_obj, operation_type)

            if not applicable_rules and not force_sync:
                sync_operation.mark_completed()
                return sync_operation

            # تنفيذ التزامن حسب القواعد
            self._execute_sync_rules(sync_operation, payment_obj, applicable_rules)

            # تحديث كاش الأرصدة
            self._update_balance_cache(sync_operation, payment_obj)

            # تحديد العملية كمكتملة
            sync_operation.mark_completed()

            logger.info(
                f"تم تزامن الدفعة {payment_obj} بنجاح - العملية {sync_operation.operation_id}"
            )

        except Exception as e:
            # معالجة الخطأ والتراجع
            self._handle_sync_error(sync_operation, e)

        return sync_operation

    def _create_sync_operation(
        self, payment_obj, operation_type: str, user=None
    ) -> PaymentSyncOperation:
        """
        إنشاء عملية تزامن جديدة
        """
        content_type = ContentType.objects.get_for_model(payment_obj)

        # تحضير بيانات الدفعة
        payment_data = {
            "id": payment_obj.id,
            "amount": str(payment_obj.amount),
            "payment_date": payment_obj.payment_date.isoformat()
            if hasattr(payment_obj, "payment_date")
            else None,
            "payment_method": getattr(payment_obj, "payment_method", None),
            "reference_number": getattr(payment_obj, "reference_number", None),
            "notes": getattr(payment_obj, "notes", None),
        }

        # إضافة بيانات خاصة حسب نوع الدفعة
        if hasattr(payment_obj, "sale"):
            payment_data.update(
                {
                    "sale_id": payment_obj.sale.id,
                    "customer_id": payment_obj.sale.customer.id,
                    "customer_name": payment_obj.sale.customer.name,
                }
            )
        elif hasattr(payment_obj, "purchase"):
            payment_data.update(
                {
                    "purchase_id": payment_obj.purchase.id,
                    "supplier_id": payment_obj.purchase.supplier.id,
                    "supplier_name": payment_obj.purchase.supplier.name,
                }
            )

        return PaymentSyncOperation.objects.create(
            operation_type=operation_type,
            content_type=content_type,
            object_id=payment_obj.id,
            payment_data=payment_data,
            created_by=user,
        )

    def _get_applicable_rules(
        self, payment_obj, operation_type: str
    ) -> List[PaymentSyncRule]:
        """
        الحصول على قواعد التزامن المطبقة
        """
        # تحديد نوع المصدر
        source_model = self._get_source_model_name(payment_obj)

        # تحديد حدث التشغيل
        trigger_event = self._map_operation_to_trigger(operation_type)

        # الحصول على القواعد المطبقة
        rules = PaymentSyncRule.objects.filter(
            source_model=source_model, trigger_event=trigger_event, is_active=True
        ).order_by("priority")

        # فلترة القواعد حسب الشروط
        applicable_rules = []
        for rule in rules:
            if rule.matches_conditions(payment_obj):
                applicable_rules.append(rule)

        return applicable_rules

    def _execute_sync_rules(
        self,
        sync_operation: PaymentSyncOperation,
        payment_obj,
        rules: List[PaymentSyncRule],
    ):
        """
        تنفيذ قواعد التزامن
        """
        for rule in rules:
            try:
                sync_targets = rule.get_sync_targets()
                sync_operation.sync_targets = sync_targets
                sync_operation.save()

                # تنفيذ كل هدف تزامن
                for target in sync_targets:
                    self._execute_sync_target(sync_operation, payment_obj, target, rule)

            except Exception as e:
                logger.error(f"خطأ في تنفيذ قاعدة التزامن {rule.name}: {str(e)}")
                self._log_sync_error(
                    sync_operation, f"rule_execution_{rule.id}", str(e)
                )
                raise

    def _execute_sync_target(
        self,
        sync_operation: PaymentSyncOperation,
        payment_obj,
        target: str,
        rule: PaymentSyncRule,
    ):
        """
        تنفيذ هدف تزامن محدد
        """
        start_time = time.time()

        try:
            if target == "customer_payment":
                self._sync_to_customer_payment(sync_operation, payment_obj, rule)
            elif target == "supplier_payment":
                self._sync_to_supplier_payment(sync_operation, payment_obj, rule)
            elif target == "journal_entry":
                self._sync_to_journal_entry(sync_operation, payment_obj, rule)
            elif target == "balance_cache":
                self._sync_to_balance_cache(sync_operation, payment_obj, rule)

            execution_time = time.time() - start_time

            # تسجيل نجاح العملية
            PaymentSyncLog.objects.create(
                sync_operation=sync_operation,
                action=f"sync_to_{target}",
                target_model=target,
                action_data={"rule_id": rule.id},
                result_data={"success": True},
                success=True,
                execution_time=execution_time,
            )

        except Exception as e:
            execution_time = time.time() - start_time

            # تسجيل فشل العملية
            PaymentSyncLog.objects.create(
                sync_operation=sync_operation,
                action=f"sync_to_{target}",
                target_model=target,
                action_data={"rule_id": rule.id},
                result_data={"error": str(e)},
                success=False,
                error_message=str(e),
                execution_time=execution_time,
            )

            raise

    def _sync_to_customer_payment(
        self, sync_operation: PaymentSyncOperation, payment_obj, rule: PaymentSyncRule
    ):
        """
        مزامنة مع جدول مدفوعات العملاء
        """
        if not hasattr(payment_obj, "sale"):
            return  # ليس دفعة مبيعات

        from client.models import CustomerPayment

        with transaction.atomic():
            # التحقق من وجود الدفعة مسبقاً
            existing_payment = CustomerPayment.objects.filter(
                customer=payment_obj.sale.customer,
                reference_number=f"SALE-{payment_obj.sale.number}-PAY-{payment_obj.id}",
            ).first()

            if (
                sync_operation.operation_type == "create_payment"
                and not existing_payment
            ):
                # إنشاء دفعة عميل جديدة
                customer_payment = CustomerPayment.objects.create(
                    customer=payment_obj.sale.customer,
                    amount=payment_obj.amount,
                    payment_date=payment_obj.payment_date,
                    payment_method=payment_obj.payment_method,
                    reference_number=f"SALE-{payment_obj.sale.number}-PAY-{payment_obj.id}",
                    notes=f"دفعة على فاتورة مبيعات رقم {payment_obj.sale.number}",
                    created_by=sync_operation.created_by,
                )

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "delete_customer_payment",
                        "object_id": customer_payment.id,
                        "model": "CustomerPayment",
                    }
                )

                logger.info(f"تم إنشاء دفعة عميل {customer_payment.id}")

            elif sync_operation.operation_type == "update_payment" and existing_payment:
                # تحديث دفعة عميل موجودة
                old_amount = existing_payment.amount
                existing_payment.amount = payment_obj.amount
                existing_payment.payment_date = payment_obj.payment_date
                existing_payment.payment_method = payment_obj.payment_method
                existing_payment.notes = (
                    f"دفعة محدثة على فاتورة مبيعات رقم {payment_obj.sale.number}"
                )
                existing_payment.save()

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "restore_customer_payment",
                        "object_id": existing_payment.id,
                        "old_data": {"amount": old_amount},
                    }
                )

                logger.info(f"تم تحديث دفعة عميل {existing_payment.id}")

            elif sync_operation.operation_type == "delete_payment" and existing_payment:
                # حذف دفعة عميل
                customer_payment_data = {
                    "customer_id": existing_payment.customer.id,
                    "amount": existing_payment.amount,
                    "payment_date": existing_payment.payment_date,
                    "payment_method": existing_payment.payment_method,
                    "reference_number": existing_payment.reference_number,
                    "notes": existing_payment.notes,
                }

                existing_payment.delete()

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "recreate_customer_payment",
                        "data": customer_payment_data,
                    }
                )

                logger.info(f"تم حذف دفعة عميل {existing_payment.id}")

    def _sync_to_supplier_payment(
        self, sync_operation: PaymentSyncOperation, payment_obj, rule: PaymentSyncRule
    ):
        """
        مزامنة مع جدول مدفوعات الموردين
        """
        if not hasattr(payment_obj, "purchase"):
            return  # ليس دفعة مشتريات

        from supplier.models import SupplierPayment

        with transaction.atomic():
            # التحقق من وجود الدفعة مسبقاً
            existing_payment = SupplierPayment.objects.filter(
                supplier=payment_obj.purchase.supplier,
                reference_number=f"PURCHASE-{payment_obj.purchase.number}-PAY-{payment_obj.id}",
            ).first()

            if (
                sync_operation.operation_type == "create_payment"
                and not existing_payment
            ):
                # إنشاء دفعة مورد جديدة
                supplier_payment = SupplierPayment.objects.create(
                    supplier=payment_obj.purchase.supplier,
                    amount=payment_obj.amount,
                    payment_date=payment_obj.payment_date,
                    payment_method=payment_obj.payment_method,
                    reference_number=f"PURCHASE-{payment_obj.purchase.number}-PAY-{payment_obj.id}",
                    notes=f"دفعة على فاتورة مشتريات رقم {payment_obj.purchase.number}",
                    created_by=sync_operation.created_by,
                )

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "delete_supplier_payment",
                        "object_id": supplier_payment.id,
                        "model": "SupplierPayment",
                    }
                )

                logger.info(f"تم إنشاء دفعة مورد {supplier_payment.id}")

            elif sync_operation.operation_type == "update_payment" and existing_payment:
                # تحديث دفعة مورد موجودة
                old_amount = existing_payment.amount
                existing_payment.amount = payment_obj.amount
                existing_payment.payment_date = payment_obj.payment_date
                existing_payment.payment_method = payment_obj.payment_method
                existing_payment.notes = (
                    f"دفعة محدثة على فاتورة مشتريات رقم {payment_obj.purchase.number}"
                )
                existing_payment.save()

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "restore_supplier_payment",
                        "object_id": existing_payment.id,
                        "old_data": {"amount": old_amount},
                    }
                )

                logger.info(f"تم تحديث دفعة مورد {existing_payment.id}")

            elif sync_operation.operation_type == "delete_payment" and existing_payment:
                # حذف دفعة مورد
                supplier_payment_data = {
                    "supplier_id": existing_payment.supplier.id,
                    "amount": existing_payment.amount,
                    "payment_date": existing_payment.payment_date,
                    "payment_method": existing_payment.payment_method,
                    "reference_number": existing_payment.reference_number,
                    "notes": existing_payment.notes,
                }

                existing_payment.delete()

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "recreate_supplier_payment",
                        "data": supplier_payment_data,
                    }
                )

                logger.info(f"تم حذف دفعة مورد {existing_payment.id}")

    def _sync_to_journal_entry(
        self, sync_operation: PaymentSyncOperation, payment_obj, rule: PaymentSyncRule
    ):
        """
        مزامنة مع القيود المحاسبية
        """
        try:
            if sync_operation.operation_type == "create_payment":
                # إنشاء قيد محاسبي للدفعة
                if hasattr(payment_obj, "sale"):
                    # دفعة مبيعات
                    entry = JournalEntryService.create_simple_entry(
                        debit_account="11011",  # الصندوق الرئيسي
                        credit_account="11030",  # العملاء
                        amount=payment_obj.amount,
                        description=f"دفعة من العميل - فاتورة {payment_obj.sale.number}",
                        date=payment_obj.payment_date,
                        reference=f"SALE-PAY-{payment_obj.id}",
                        user=sync_operation.created_by,
                    )
                elif hasattr(payment_obj, "purchase"):
                    # دفعة مشتريات
                    entry = JournalEntryService.create_simple_entry(
                        debit_account="21010",  # الموردين
                        credit_account="11011",  # الصندوق الرئيسي
                        amount=payment_obj.amount,
                        description=f"دفعة للمورد - فاتورة {payment_obj.purchase.number}",
                        date=payment_obj.payment_date,
                        reference=f"PURCH-PAY-{payment_obj.id}",
                        user=sync_operation.created_by,
                    )

                # إضافة للمكدس للتراجع المحتمل
                self.rollback_stack.append(
                    {
                        "action": "delete_journal_entry",
                        "object_id": entry.id,
                        "model": "JournalEntry",
                    }
                )

                logger.info(f"تم إنشاء قيد محاسبي {entry.number}")

        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد المحاسبي: {str(e)}")
            raise

    def _sync_to_balance_cache(
        self, sync_operation: PaymentSyncOperation, payment_obj, rule: PaymentSyncRule
    ):
        """
        مزامنة مع كاش الأرصدة
        """
        try:
            # تحديد الحسابات المتأثرة
            affected_accounts = []

            if hasattr(payment_obj, "sale"):
                affected_accounts.extend(["11011", "11030"])  # الصندوق والعملاء
            elif hasattr(payment_obj, "purchase"):
                affected_accounts.extend(["11011", "21010"])  # الصندوق والموردين

            # إبطال كاش الحسابات المتأثرة
            for account_code in affected_accounts:
                financial_cache.delete_pattern(f"balance:*account_code:{account_code}*")

            logger.info(f"تم إبطال كاش الأرصدة للحسابات: {affected_accounts}")

        except Exception as e:
            logger.error(f"خطأ في تحديث كاش الأرصدة: {str(e)}")
            # لا نرفع الخطأ هنا لأن فشل الكاش لا يجب أن يوقف العملية

    def _update_balance_cache(self, sync_operation: PaymentSyncOperation, payment_obj):
        """
        تحديث كاش الأرصدة للحسابات المتأثرة
        """
        try:
            from ..models.enhanced_balance import AccountBalanceCache
            from ..models.chart_of_accounts import ChartOfAccounts

            # تحديد الحسابات المتأثرة
            account_codes = []
            if hasattr(payment_obj, "sale"):
                account_codes = ["11011", "11030"]
            elif hasattr(payment_obj, "purchase"):
                account_codes = ["11011", "21010"]

            # تحديث كاش كل حساب
            for account_code in account_codes:
                try:
                    account = ChartOfAccounts.objects.get(
                        code=account_code, is_active=True
                    )
                    cache_obj, created = AccountBalanceCache.objects.get_or_create(
                        account=account, defaults={"needs_refresh": True}
                    )

                    # تحديث الكاش
                    cache_obj.refresh_balance(force=True)

                except ChartOfAccounts.DoesNotExist:
                    logger.warning(f"الحساب {account_code} غير موجود")

        except Exception as e:
            logger.error(f"خطأ في تحديث كاش الأرصدة: {str(e)}")

    def _handle_sync_error(
        self, sync_operation: PaymentSyncOperation, error: Exception
    ):
        """
        معالجة أخطاء التزامن والتراجع
        """
        error_message = str(error)
        error_details = {
            "error_type": type(error).__name__,
            "stack_trace": traceback.format_exc(),
        }

        # تسجيل الخطأ
        sync_error = PaymentSyncError.objects.create(
            sync_operation=sync_operation,
            error_type=self._classify_error(error),
            error_message=error_message,
            stack_trace=traceback.format_exc(),
            context_data=sync_operation.payment_data,
        )

        # محاولة التراجع
        try:
            self._rollback_operations()
            sync_operation.status = "rolled_back"
            logger.info(f"تم التراجع عن العملية {sync_operation.operation_id}")
        except Exception as rollback_error:
            logger.error(f"فشل في التراجع: {str(rollback_error)}")
            sync_operation.status = "failed"

        # تحديث حالة العملية
        sync_operation.mark_failed(error_message, error_details)

        logger.error(
            f"فشل في تزامن الدفعة - العملية {sync_operation.operation_id}: {error_message}"
        )

    def _rollback_operations(self):
        """
        التراجع عن العمليات المنفذة
        """
        # تنفيذ عمليات التراجع بالعكس
        for rollback_item in reversed(self.rollback_stack):
            try:
                self._execute_rollback_item(rollback_item)
            except Exception as e:
                logger.error(f"خطأ في تنفيذ التراجع: {str(e)}")
                raise

        # مسح المكدس
        self.rollback_stack.clear()

    def _execute_rollback_item(self, rollback_item: Dict):
        """
        تنفيذ عنصر تراجع واحد
        """
        action = rollback_item["action"]

        if action == "delete_customer_payment":
            from client.models import CustomerPayment

            CustomerPayment.objects.filter(id=rollback_item["object_id"]).delete()

        elif action == "delete_supplier_payment":
            from supplier.models import SupplierPayment

            SupplierPayment.objects.filter(id=rollback_item["object_id"]).delete()

        elif action == "delete_journal_entry":
            from ..models.journal_entry import JournalEntry

            JournalEntry.objects.filter(id=rollback_item["object_id"]).delete()

        elif action == "restore_customer_payment":
            from client.models import CustomerPayment

            payment = CustomerPayment.objects.get(id=rollback_item["object_id"])
            for key, value in rollback_item["old_data"].items():
                setattr(payment, key, value)
            payment.save()

        elif action == "restore_supplier_payment":
            from supplier.models import SupplierPayment

            payment = SupplierPayment.objects.get(id=rollback_item["object_id"])
            for key, value in rollback_item["old_data"].items():
                setattr(payment, key, value)
            payment.save()

        elif action == "recreate_customer_payment":
            from client.models import CustomerPayment

            CustomerPayment.objects.create(**rollback_item["data"])

        elif action == "recreate_supplier_payment":
            from supplier.models import SupplierPayment

            SupplierPayment.objects.create(**rollback_item["data"])

    def _get_source_model_name(self, payment_obj) -> str:
        """
        تحديد اسم النموذج المصدر
        """
        model_name = payment_obj.__class__.__name__.lower()

        if "sale" in model_name:
            return "sale_payment"
        elif "purchase" in model_name:
            return "purchase_payment"
        elif "customer" in model_name:
            return "customer_payment"
        elif "supplier" in model_name:
            return "supplier_payment"

        return "unknown"

    def _map_operation_to_trigger(self, operation_type: str) -> str:
        """
        ربط نوع العملية بحدث التشغيل
        """
        mapping = {
            "create_payment": "on_create",
            "update_payment": "on_update",
            "delete_payment": "on_delete",
        }

        return mapping.get(operation_type, "on_create")

    def _classify_error(self, error: Exception) -> str:
        """
        تصنيف نوع الخطأ
        """
        if isinstance(error, ValidationError):
            return "validation_error"
        elif isinstance(error, IntegrityError):
            return "database_error"
        elif isinstance(error, PermissionError):
            return "permission_error"
        else:
            return "system_error"

    def _log_sync_error(
        self, sync_operation: PaymentSyncOperation, error_code: str, error_message: str
    ):
        """
        تسجيل خطأ التزامن
        """
        PaymentSyncError.objects.create(
            sync_operation=sync_operation,
            error_type="system_error",
            error_code=error_code,
            error_message=error_message,
            context_data=sync_operation.payment_data,
        )

    def get_sync_statistics(self) -> Dict[str, Any]:
        """
        الحصول على إحصائيات التزامن
        """
        from django.db.models import Count, Q
        from datetime import timedelta

        now = timezone.now()
        today = now.date()

        # إحصائيات العمليات
        total_operations = PaymentSyncOperation.objects.count()
        completed_operations = PaymentSyncOperation.objects.filter(
            status="completed"
        ).count()
        failed_operations = PaymentSyncOperation.objects.filter(status="failed").count()
        pending_operations = PaymentSyncOperation.objects.filter(
            status="pending"
        ).count()

        # عمليات اليوم
        today_operations = PaymentSyncOperation.objects.filter(
            created_at__date=today
        ).count()

        # عمليات آخر 7 أيام
        week_ago = now - timedelta(days=7)
        week_operations = PaymentSyncOperation.objects.filter(
            created_at__gte=week_ago
        ).count()

        # معدل النجاح
        success_rate = 0
        if total_operations > 0:
            success_rate = round((completed_operations / total_operations) * 100, 2)

        # آخر الأخطاء
        recent_errors = PaymentSyncError.objects.select_related(
            "sync_operation"
        ).order_by("-occurred_at")[:5]

        # القواعد النشطة
        active_rules = PaymentSyncRule.objects.filter(is_active=True).count()

        return {
            "total_operations": total_operations,
            "completed_operations": completed_operations,
            "failed_operations": failed_operations,
            "pending_operations": pending_operations,
            "today_operations": today_operations,
            "week_operations": week_operations,
            "success_rate": success_rate,
            "recent_errors": recent_errors,
            "active_rules": active_rules,
        }


# إنشاء instance عام للخدمة
payment_sync_service = PaymentSyncService()
