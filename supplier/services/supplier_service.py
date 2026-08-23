"""
Supplier Service - خدمة موحدة لإدارة الموردين

هذه الخدمة تستخدم:
- AccountingGateway للقيود المحاسبية (مع الحوكمة الكاملة)
- إدارة شاملة للموردين وحساباتهم المالية

الهدف: ضمان الالتزام الكامل بمعايير الحوكمة والتدقيق
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import logging

from supplier.models import Supplier, SupplierType
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()
logger = logging.getLogger(__name__)


class SupplierService:
    """
    خدمة موحدة لإدارة الموردين مع الالتزام الكامل بالحوكمة
    """

    @staticmethod
    @transaction.atomic
    def create_supplier(name, code=None, entity_type="company", national_id=None,
                       commercial_registry=None, phone='', email='', address='', city='',
                       country='مصر', contact_person='', tax_number='',
                       website='', whatsapp='', secondary_phone='',
                       credit_limit=Decimal('0.00'), default_payment_term=None,
                       grace_period_days=0, bank_name=None, bank_account_number=None,
                       bank_beneficiary_name=None, default_currency=None,
                       working_hours='', is_preferred=False, is_active=True,
                       primary_type_id=None, primary_type_code=None,
                       user=None, create_financial_account=True):
        """
        إنشاء مورد جديد مع الحساب المحاسبي
        
        Args:
            name: اسم المورد (مطلوب)
            code: كود المورد (اختياري - يتم توليده تلقائياً)
            phone: رقم الهاتف
            email: البريد الإلكتروني
            address: العنوان
            city: المدينة
            country: البلد
            contact_person: الشخص المسؤول
            tax_number: الرقم الضريبي
            website: الموقع الإلكتروني
            whatsapp: رقم الواتساب
            secondary_phone: هاتف ثانوي
            working_hours: ساعات العمل
            is_preferred: مورد مفضل
            is_active: نشط
            primary_type_id: معرف نوع المورد
            primary_type_code: كود نوع المورد (بديل لـ primary_type_id)
            user: المستخدم الذي ينشئ المورد
            create_financial_account: إنشاء حساب محاسبي تلقائياً
            
        Returns:
            Supplier: المورد المنشأ
            
        Raises:
            ValidationError: في حالة بيانات غير صحيحة
            Exception: في حالة فشل أي عملية
        """
        try:
            # التحقق من البيانات المطلوبة
            if not name or not name.strip():
                raise ValidationError("اسم المورد مطلوب")
            
            # الحصول على نوع المورد
            primary_type = None
            if primary_type_id:
                try:
                    primary_type = SupplierType.objects.get(id=primary_type_id, is_active=True)
                except SupplierType.DoesNotExist:
                    raise ValidationError(f"نوع المورد بمعرف {primary_type_id} غير موجود")
            elif primary_type_code:
                try:
                    primary_type = SupplierType.objects.get(code=primary_type_code, is_active=True)
                except SupplierType.DoesNotExist:
                    raise ValidationError(f"نوع المورد بكود {primary_type_code} غير موجود")
            else:
                # استخدام النوع الافتراضي (general)
                primary_type = SupplierType.objects.filter(code='general', is_active=True).first()
                if not primary_type:
                    # إنشاء نوع عام افتراضي
                    primary_type = SupplierType.objects.create(
                        name='مورد عام',
                        code='general',
                        description='مورد عام',
                        icon='fas fa-truck',
                        color='#6c757d',
                        is_active=True
                    )
            
            # إنشاء المورد
            supplier = Supplier.objects.create(
                name=name.strip(),
                code=code if code else None,  # سيتم توليده تلقائياً في save()
                entity_type=entity_type,
                national_id=national_id,
                commercial_registry=commercial_registry,
                phone=phone,
                email=email,
                address=address,
                city=city,
                country=country,
                contact_person=contact_person,
                tax_number=tax_number,
                credit_limit=credit_limit or Decimal('0.00'),
                default_payment_term=default_payment_term,
                grace_period_days=grace_period_days or 0,
                bank_name=bank_name,
                bank_account_number=bank_account_number,
                bank_beneficiary_name=bank_beneficiary_name,
                default_currency=default_currency,
                website=website,
                whatsapp=whatsapp,
                secondary_phone=secondary_phone,
                working_hours=working_hours,
                is_preferred=is_preferred,
                is_active=is_active,
                primary_type=primary_type,
                balance=Decimal('0'),
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء المورد: {supplier.name} ({supplier.code})")
            
            # إنشاء الحساب المحاسبي
            if create_financial_account:
                SupplierService.create_financial_account_for_supplier(supplier, user)
            
            return supplier
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء المورد: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def update_supplier(supplier, name=None, entity_type=None, national_id=None,
                       commercial_registry=None, phone=None, email=None, address=None,
                       city=None, country=None, contact_person=None, tax_number=None,
                       credit_limit=None, default_payment_term=None, grace_period_days=None,
                       bank_name=None, bank_account_number=None, bank_beneficiary_name=None,
                       default_currency=None, website=None, whatsapp=None, secondary_phone=None,
                       working_hours=None, is_preferred=None, is_active=None,
                       primary_type_id=None, user=None):
        """
        تحديث بيانات مورد
        
        Args:
            supplier: المورد المراد تحديثه
            name: اسم المورد الجديد
            phone: رقم الهاتف الجديد
            ... (باقي الحقول)
            user: المستخدم الذي يحدث البيانات
            
        Returns:
            Supplier: المورد المحدث
        """
        try:
            # تحديث الحقول المطلوبة فقط
            if name is not None:
                if not name.strip():
                    raise ValidationError("اسم المورد لا يمكن أن يكون فارغاً")
                supplier.name = name.strip()
            
            if entity_type is not None:
                supplier.entity_type = entity_type
            
            if national_id is not None:
                supplier.national_id = national_id
            
            if commercial_registry is not None:
                supplier.commercial_registry = commercial_registry
            
            if phone is not None:
                supplier.phone = phone
            
            if email is not None:
                supplier.email = email
            
            if address is not None:
                supplier.address = address
            
            if city is not None:
                supplier.city = city
            
            if country is not None:
                supplier.country = country
            
            if contact_person is not None:
                supplier.contact_person = contact_person
            
            if tax_number is not None:
                supplier.tax_number = tax_number
            
            if credit_limit is not None:
                supplier.credit_limit = credit_limit
            
            if default_payment_term is not None:
                supplier.default_payment_term = default_payment_term
            
            if grace_period_days is not None:
                supplier.grace_period_days = grace_period_days
            
            if bank_name is not None:
                supplier.bank_name = bank_name
            
            if bank_account_number is not None:
                supplier.bank_account_number = bank_account_number
            
            if bank_beneficiary_name is not None:
                supplier.bank_beneficiary_name = bank_beneficiary_name
            
            if default_currency is not None:
                supplier.default_currency = default_currency
            
            if website is not None:
                supplier.website = website
            
            if whatsapp is not None:
                supplier.whatsapp = whatsapp
            
            if secondary_phone is not None:
                supplier.secondary_phone = secondary_phone
            
            if working_hours is not None:
                supplier.working_hours = working_hours
            
            if is_preferred is not None:
                supplier.is_preferred = is_preferred
            
            if is_active is not None:
                supplier.is_active = is_active
            
            if primary_type_id is not None:
                try:
                    primary_type = SupplierType.objects.get(id=primary_type_id, is_active=True)
                    supplier.primary_type = primary_type
                except SupplierType.DoesNotExist:
                    raise ValidationError(f"نوع المورد بمعرف {primary_type_id} غير موجود")
            
            supplier.save()
            
            logger.info(f"✅ تم تحديث المورد: {supplier.name} ({supplier.code})")
            return supplier
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث المورد {supplier.code}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def create_financial_account_for_supplier(supplier, user=None):
        """
        إنشاء حساب محاسبي للمورد في دليل الحسابات
        
        Uses idempotency to prevent duplicate account creation.
        
        Args:
            supplier: المورد
            user: المستخدم
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي المنشأ
        """
        from governance.services.idempotency_service import IdempotencyService
        from django.contrib.auth import get_user_model
        
        if user is None:
            User = get_user_model()
            user = getattr(supplier, 'created_by', None) or User.objects.filter(is_superuser=True).first() or User.objects.first()
        
        # Generate idempotency key for this operation
        idempotency_key = IdempotencyService.generate_key(
            'SUPPLIER_ACCOUNT',
            supplier.id,
            supplier.code
        )
        
        # Check if account already created
        exists, record, result_data = IdempotencyService.check_operation_exists(
            operation_type='create_supplier_account',
            idempotency_key=idempotency_key
        )
        
        if exists and result_data and result_data.get('account_id'):
            # Account already created, return existing account
            account_id = result_data.get('account_id')
            try:
                account = ChartOfAccounts.objects.get(id=account_id)
                if not supplier.financial_account_id:
                    from supplier.models import Supplier
                    Supplier.objects.filter(pk=supplier.pk).update(financial_account=account)
                    supplier.financial_account = account
                    supplier.financial_account_id = account.id
                logger.info(
                    f"✅ Idempotency: Returning existing account {account.code} "
                    f"for supplier {supplier.code}"
                )
                return account
            except ChartOfAccounts.DoesNotExist:
                logger.warning(
                    f"⚠️ Idempotency record exists but account {account_id} not found. "
                    f"Creating new account."
                )
        
        try:
            # التحقق من عدم وجود حساب محاسبي مسبقاً
            if supplier.financial_account:
                logger.info(f"المورد {supplier.name} لديه حساب محاسبي بالفعل: {supplier.financial_account.code}")
                return supplier.financial_account

            from financial.services.subledger_account_service import SubledgerAccountService
            financial_account = SubledgerAccountService.create_supplier_account(supplier, user=user)

            if not financial_account:
                raise ValueError(f"تعذر إنشاء حساب محاسبي للمورد {supplier.name}")

            # Record idempotency to prevent future duplicates
            IdempotencyService.check_and_record_operation(
                operation_type='create_supplier_account',
                idempotency_key=idempotency_key,
                result_data={
                    'account_id': financial_account.id,
                    'account_code': financial_account.code,
                    'supplier_id': supplier.id,
                    'supplier_code': supplier.code
                },
                user=user,
                expires_in_hours=720  # 30 days
            )

            logger.info(f"✅ تم إنشاء حساب محاسبي للمورد {supplier.name}: {financial_account.code}")
            return financial_account

        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء الحساب المحاسبي للمورد {supplier.name}: {str(e)}")
            raise

    @staticmethod
    def get_supplier_balance(supplier):
        """
        حساب رصيد المورد الفعلي من المعاملات
        
        Args:
            supplier: المورد
            
        Returns:
            Decimal: الرصيد الفعلي
        """
        try:
            from django.db.models import Sum
            from purchase.models import Purchase, PurchasePayment
            
            # إجمالي المشتريات بالمعادل الوظيفي
            purchases_qs = Purchase.objects.filter(supplier=supplier, status='confirmed')
            total_purchases = sum(
                (getattr(p, 'total_functional', None) or (p.total * (getattr(p, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))).quantize(Decimal('0.01'))
                for p in purchases_qs
            ) if purchases_qs.exists() else Decimal('0.00')
            
            # إجمالي المدفوعات بالمعادل الوظيفي
            payments_qs = PurchasePayment.objects.filter(purchase__supplier=supplier, status='posted').select_related('purchase')
            total_payments = Decimal('0.00')
            for p in payments_qs:
                rate = getattr(p.purchase, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')
                settled = getattr(p, 'amount_settled_invoice_currency', p.amount) or p.amount
                func_amt = (Decimal(str(settled)) * Decimal(str(rate))).quantize(Decimal('0.01'))
                total_payments += func_amt
            
            # الرصيد = المشتريات - المدفوعات
            balance = (total_purchases - total_payments).quantize(Decimal('0.01'))
            
            return balance
            
        except Exception as e:
            logger.error(f"❌ خطأ في حساب رصيد المورد {supplier.code}: {str(e)}")
            return Decimal('0')

    @staticmethod
    def get_supplier_statement(supplier, date_from=None, date_to=None):
        """
        الحصول على كشف حساب المورد
        
        Args:
            supplier: المورد
            date_from: من تاريخ
            date_to: إلى تاريخ
            
        Returns:
            dict: كشف الحساب مع التفاصيل
        """
        try:
            from purchase.models import Purchase, PurchasePayment
            
            # فلترة حسب التاريخ
            purchases_query = Purchase.objects.filter(supplier=supplier, status='confirmed')
            payments_query = PurchasePayment.objects.filter(purchase__supplier=supplier, status='posted')
            
            if date_from:
                purchases_query = purchases_query.filter(date__gte=date_from)
                payments_query = payments_query.filter(payment_date__gte=date_from)
            
            if date_to:
                purchases_query = purchases_query.filter(date__lte=date_to)
                payments_query = payments_query.filter(payment_date__lte=date_to)
            
            # الحصول على البيانات
            purchases = purchases_query.order_by('date')
            payments = payments_query.order_by('payment_date')
            
            # حساب الإجماليات
            from django.db.models import Sum
            total_purchases = purchases.aggregate(Sum('total'))['total__sum'] or Decimal('0')
            total_payments = payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            balance = total_purchases - total_payments
            
            # تجميع المعاملات
            transactions = []
            
            for purchase in purchases:
                transactions.append({
                    'date': purchase.date,
                    'type': 'purchase',
                    'reference': purchase.number,
                    'description': f'فاتورة مشتريات رقم {purchase.number}',
                    'debit': purchase.total,
                    'credit': Decimal('0'),
                    'balance': None  # سيتم حسابه لاحقاً
                })
            
            for payment in payments:
                transactions.append({
                    'date': payment.payment_date,
                    'type': 'payment',
                    'reference': f'PAY-{payment.purchase.number}',
                    'description': f'دفعة على فاتورة {payment.purchase.number}',
                    'debit': Decimal('0'),
                    'credit': payment.amount,
                    'balance': None  # سيتم حسابه لاحقاً
                })
            
            # ترتيب المعاملات حسب التاريخ
            transactions.sort(key=lambda x: x['date'])
            
            # حساب الرصيد التراكمي
            running_balance = Decimal('0')
            for transaction in transactions:
                running_balance += transaction['debit'] - transaction['credit']
                transaction['balance'] = running_balance
            
            return {
                'supplier': supplier,
                'date_from': date_from,
                'date_to': date_to,
                'total_purchases': total_purchases,
                'total_payments': total_payments,
                'balance': balance,
                'transactions': transactions,
                'transactions_count': len(transactions)
            }
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على كشف حساب المورد {supplier.code}: {str(e)}")
            return {
                'supplier': supplier,
                'error': str(e),
                'transactions': []
            }

    @staticmethod
    def get_supplier_statistics(supplier):
        """
        الحصول على إحصائيات المورد
        
        Args:
            supplier: المورد
            
        Returns:
            dict: إحصائيات شاملة
        """
        try:
            from django.db.models import Sum, Count
            from purchase.models import Purchase, PurchasePayment
            
            # إحصائيات المشتريات
            # إحصائيات المشتريات بالمعادل الوظيفي
            purchases_qs = Purchase.objects.filter(supplier=supplier, status='confirmed')
            purchases_count = purchases_qs.count()
            total_purchases = sum(
                (getattr(p, 'total_functional', None) or (p.total * (getattr(p, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))).quantize(Decimal('0.01'))
                for p in purchases_qs
            ) if purchases_count > 0 else Decimal('0.00')
            
            # إحصائيات المدفوعات بالمعادل الوظيفي
            payments_qs = PurchasePayment.objects.filter(purchase__supplier=supplier, status='posted').select_related('purchase')
            payments_count = payments_qs.count()
            total_payments = Decimal('0.00')
            for p in payments_qs:
                rate = getattr(p.purchase, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')
                settled = getattr(p, 'amount_settled_invoice_currency', p.amount) or p.amount
                func_amt = (Decimal(str(settled)) * Decimal(str(rate))).quantize(Decimal('0.01'))
                total_payments += func_amt
            
            balance = (total_purchases - total_payments).quantize(Decimal('0.01'))
            
            # آخر معاملة
            last_purchase = purchases_qs.order_by('-date').first()
            last_payment = payments_qs.order_by('-payment_date').first()
            
            return {
                'total_purchases': total_purchases,
                'purchases_count': purchases_count,
                'total_payments': total_payments,
                'payments_count': payments_count,
                'balance': balance,
                'last_purchase_date': last_purchase.date if last_purchase else None,
                'last_payment_date': last_payment.payment_date if last_payment else None,
                'is_active': supplier.is_active,
                'is_preferred': supplier.is_preferred,
                'has_financial_account': supplier.financial_account is not None
            }
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على إحصائيات المورد {supplier.code}: {str(e)}")
            return {
                'error': str(e)
            }

    @staticmethod
    def can_delete_supplier(supplier) -> tuple:
        """
        فحص شامل لمصفوفة المعاملات السيادية للمورد.
        إرجاع: (can_delete_permanently: bool, transactions_summary_list: list, exposure_dict: dict)
        """
        transactions_summary = []
        
        # 1. فواتير المشتريات
        from purchase.models import Purchase
        purchases_count = Purchase.objects.filter(supplier=supplier).count()
        if purchases_count > 0:
            transactions_summary.append({'label': 'فواتير مشتريات', 'count': purchases_count, 'icon': 'fas fa-shopping-cart'})

        # 2. أوامر الشراء
        try:
            from purchase.models import PurchaseOrder
            po_count = PurchaseOrder.objects.filter(supplier=supplier).count()
            if po_count > 0:
                transactions_summary.append({'label': 'أوامر شراء', 'count': po_count, 'icon': 'fas fa-file-invoice'})
        except Exception:
            pass

        # 3. مرتجعات المشتريات
        try:
            from purchase.models import PurchaseReturn
            returns_count = PurchaseReturn.objects.filter(supplier=supplier).count()
            if returns_count > 0:
                transactions_summary.append({'label': 'مرتجعات مشتريات', 'count': returns_count, 'icon': 'fas fa-exchange-alt'})
        except Exception:
            pass

        # 4. سندات الصرف والدفع للمورد
        payments_count = supplier.payments.count() if hasattr(supplier, 'payments') else 0
        if payments_count > 0:
            transactions_summary.append({'label': 'سندات دفع ومصروفات', 'count': payments_count, 'icon': 'fas fa-money-bill-wave'})

        # 5. الأستاذ المساعد للموردين
        subledger_count = supplier.subledger_transactions.count() if hasattr(supplier, 'subledger_transactions') else 0
        if subledger_count > 0:
            transactions_summary.append({'label': 'حركات أستاذ مساعد', 'count': subledger_count, 'icon': 'fas fa-book'})

        # 6. قيود اليومية المرتبطة بالحساب المالي
        if supplier.financial_account:
            from financial.models.journal_entry import JournalEntryLine
            journal_lines_count = JournalEntryLine.objects.filter(account=supplier.financial_account).count()
            if journal_lines_count > 0:
                transactions_summary.append({'label': 'قيود يومية محاسبية', 'count': journal_lines_count, 'icon': 'fas fa-calculator'})

        # 7. الأرصدة الافتتاحية
        try:
            from financial.models import OpeningBalanceLine
            opening_count = OpeningBalanceLine.objects.filter(supplier=supplier).count()
            if opening_count > 0:
                transactions_summary.append({'label': 'أرصدة افتتاحية', 'count': opening_count, 'icon': 'fas fa-balance-scale'})
        except Exception:
            pass

        # فحص المزامنة الخارجية مع دفترة
        daftra_id = getattr(supplier, 'daftra_id', None)
        if daftra_id:
            transactions_summary.append({'label': 'ارتباط مزامنة دفترة', 'count': 1, 'icon': 'fas fa-sync'})

        total_transactions = sum(item['count'] for item in transactions_summary)
        can_delete = (total_transactions == 0)

        # حساب الالتزامات المالية
        has_debt = (supplier.current_balance != Decimal('0.00')) if hasattr(supplier, 'current_balance') else (supplier.balance != Decimal('0.00') if hasattr(supplier, 'balance') else False)
        balance_val = getattr(supplier, 'current_balance', getattr(supplier, 'balance', Decimal('0.00')))

        exposure_dict = {
            'has_debt': has_debt,
            'balance': balance_val,
            'available_prepaid': Decimal('0.00'),
        }

        return can_delete, transactions_summary, exposure_dict

    @staticmethod
    @transaction.atomic
    def delete_supplier(supplier, user=None):
        """
        حذف نهائي للمورد الجديد الفارغ أو أرشفة وتعطيل ذكي للمورد المرتبط بمعاملات
        مع حماية التزامن وقفل الصفوف.
        """
        from supplier.models import Supplier
        locked_supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
        can_delete, summary, exposure = SupplierService.can_delete_supplier(locked_supplier)

        supplier_name = locked_supplier.name
        supplier_code = locked_supplier.code

        if can_delete:
            financial_account = locked_supplier.financial_account
            locked_supplier.delete()

            if financial_account:
                try:
                    from financial.models import ChartOfAccounts, JournalEntryLine
                    acc = ChartOfAccounts.objects.filter(id=financial_account.id).first()
                    if acc and not JournalEntryLine.objects.filter(account=acc).exists() and not acc.children.exists():
                        acc.delete()
                        logger.info(f"✅ تم تطهير الحساب المالي الفرعي {acc.code} للمورد المحذوف {supplier_name}")
                except Exception as e:
                    logger.warning(f"فشل حذف الحساب المالي بعد حذف المورد: {e}")

            logger.info(f"✅ تم حذف المورد {supplier_name} ({supplier_code}) نهائياً من قاعدة البيانات")
            return {
                'success': True,
                'action': 'deleted',
                'message': f"تم حذف المورد '{supplier_name}' وتطهير الحساب المالي التابع له بنجاح."
            }
        else:
            locked_supplier.is_active = False
            locked_supplier.save(update_fields=['is_active'])

            if locked_supplier.financial_account:
                try:
                    locked_supplier.financial_account.is_active = False
                    locked_supplier.financial_account.save(update_fields=['is_active'])
                except Exception as e:
                    logger.warning(f"فشل تعطيل الحساب المالي للمورد المؤرشف: {e}")

            logger.info(f"📦 تمت أرشفة وتعطيل المورد {supplier_name} ({supplier_code}) بنجاح لوجود سجلات مرتبطة")
            return {
                'success': True,
                'action': 'archived',
                'message': f"تمت أرشفة وتعطيل المورد '{supplier_name}' وحسابه المالي بنجاح لمنع التعامل معه، ويمكنك مراجعته عبر فلتر 'المعطلين'."
            }

    @staticmethod
    @transaction.atomic
    def reactivate_supplier(supplier, user=None) -> dict:
        """
        إعادة تنشيط مورد مؤرشف وحسابه المالي التابع
        """
        from supplier.models import Supplier
        locked_supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
        locked_supplier.is_active = True
        locked_supplier.save(update_fields=['is_active'])

        if locked_supplier.financial_account:
            try:
                locked_supplier.financial_account.is_active = True
                locked_supplier.financial_account.save(update_fields=['is_active'])
            except Exception as e:
                logger.warning(f"فشل إعادة تنشيط الحساب المالي للمورد: {e}")

        logger.info(f"🔄 تمت إعادة تنشيط المورد {locked_supplier.name} ({locked_supplier.code}) وحسابه المالي بنجاح")
        return {
            'success': True,
            'action': 'reactivated',
            'message': f"تمت إعادة تنشيط المورد '{locked_supplier.name}' وحسابه المالي بنجاح."
        }

    @staticmethod
    def get_active_suppliers(supplier_type_code=None):
        """
        الحصول على قائمة الموردين النشطين
        
        Args:
            supplier_type_code: كود نوع المورد (اختياري)
            
        Returns:
            QuerySet: الموردين النشطين
        """
        try:
            suppliers = Supplier.objects.filter(is_active=True)
            
            if supplier_type_code:
                suppliers = suppliers.filter(primary_type__code=supplier_type_code)
            
            return suppliers.select_related('primary_type', 'financial_account').order_by('name')
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على الموردين النشطين: {str(e)}")
            return Supplier.objects.none()

    @staticmethod
    def get_preferred_suppliers():
        """
        الحصول على قائمة الموردين المفضلين
        
        Returns:
            QuerySet: الموردين المفضلين
        """
        try:
            return Supplier.objects.filter(
                is_active=True,
                is_preferred=True
            ).select_related('primary_type', 'financial_account').order_by('name')
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على الموردين المفضلين: {str(e)}")
            return Supplier.objects.none()

    # ================================================================
    # Methods جديدة — خدمات الموردين (المرحلة الأولى)
    # ================================================================

    @staticmethod
    def get_suppliers_by_service_type(service_type_code):
        """
        جلب الموردين الذين يقدمون خدمة من نوع معين.

        Args:
            service_type_code: كود نوع الخدمة (مثل 'paper', 'offset_printing')

        Returns:
            QuerySet: الموردين النشطين الذين لديهم خدمة من هذا النوع
        """
        from supplier.models import SupplierService as SupplierServiceModel
        try:
            return Supplier.objects.filter(
                is_active=True,
                services__service_type__code=service_type_code,
                services__is_active=True,
            ).select_related('primary_type').distinct().order_by('name')
        except Exception as e:
            logger.error(f"❌ خطأ في get_suppliers_by_service_type({service_type_code}): {e}")
            return Supplier.objects.none()

    @staticmethod
    def get_supplier_services(supplier_id, service_type_code=None):
        """
        جلب الخدمات المتاحة عند مورد معين، مع إمكانية الفلترة بنوع الخدمة.

        Args:
            supplier_id: معرف المورد
            service_type_code: كود نوع الخدمة (اختياري)

        Returns:
            QuerySet: خدمات المورد النشطة
        """
        from supplier.models import SupplierService as SupplierServiceModel
        try:
            qs = SupplierServiceModel.objects.filter(
                supplier_id=supplier_id,
                is_active=True,
                supplier__is_active=True,
            ).select_related('service_type', 'supplier')

            if service_type_code:
                qs = qs.filter(service_type__code=service_type_code)

            return qs.order_by('service_type__order', 'name')
        except Exception as e:
            logger.error(f"❌ خطأ في get_supplier_services(supplier={supplier_id}): {e}")
            from supplier.models import SupplierService as SupplierServiceModel
            return SupplierServiceModel.objects.none()

    @staticmethod
    def get_service_price(service_id, quantity=1):
        """
        جلب سعر خدمة معينة للكمية المطلوبة.
        يبحث في الشرائح السعرية أولاً، ثم يرجع base_price كـ fallback.

        Args:
            service_id: معرف الخدمة
            quantity: الكمية المطلوبة (للبحث في الشرائح)

        Returns:
            dict: {price, setup_cost, service_name, supplier_name, is_fallback}
            أو None إذا لم توجد الخدمة
        """
        from supplier.models import SupplierService as SupplierServiceModel
        try:
            service = SupplierServiceModel.objects.select_related(
                'supplier', 'service_type'
            ).get(id=service_id, is_active=True)

            price = service.get_price_for_quantity(quantity)

            return {
                'price':         price,
                'setup_cost':    service.setup_cost,
                'service_name':  service.name,
                'supplier_name': service.supplier.name,
                'supplier_id':   service.supplier_id,
                'service_type':  service.service_type.code,
                'attributes':    service.attributes,
                'is_fallback':   False,
            }
        except SupplierServiceModel.DoesNotExist:
            logger.warning(f"⚠️ SupplierService id={service_id} غير موجود")
            return None
        except Exception as e:
            logger.error(f"❌ خطأ في get_service_price(service={service_id}): {e}")
            return None
