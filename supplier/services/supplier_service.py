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
    def create_supplier(name, code=None, phone='', email='', address='', city='',
                       country='مصر', contact_person='', tax_number='',
                       website='', whatsapp='', secondary_phone='',
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
                phone=phone,
                email=email,
                address=address,
                city=city,
                country=country,
                contact_person=contact_person,
                tax_number=tax_number,
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
    def update_supplier(supplier, name=None, phone=None, email=None, address=None,
                       city=None, country=None, contact_person=None, tax_number=None,
                       website=None, whatsapp=None, secondary_phone=None,
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
        
        if exists and result_data:
            # Account already created, return existing account
            account_id = result_data.get('account_id')
            if account_id:
                try:
                    account = ChartOfAccounts.objects.get(id=account_id)
                    logger.info(
                        f"✅ Idempotency: Returning existing account {account.code} "
                        f"for supplier {supplier.code}"
                    )
                    return account
                except ChartOfAccounts.DoesNotExist:
                    # Account was deleted, continue to create new one
                    logger.warning(
                        f"⚠️ Idempotency record exists but account {account_id} not found. "
                        f"Creating new account."
                    )
        
        try:
            # التحقق من عدم وجود حساب محاسبي مسبقاً
            if supplier.financial_account:
                logger.info(f"المورد {supplier.name} لديه حساب محاسبي بالفعل: {supplier.financial_account.code}")
                return supplier.financial_account
            
            # الحصول على نوع حساب الموردين (Liability)
            liability_type = AccountType.objects.filter(code='LIABILITY').first()
            if not liability_type:
                liability_type = AccountType.objects.create(
                    code='LIABILITY',
                    name='خصوم',
                    nature='credit'
                )
            
            # الحصول على الحساب الرئيسي للموردين (20100)
            parent_account = ChartOfAccounts.objects.filter(code='20100').first()
            if not parent_account:
                parent_account = ChartOfAccounts.objects.create(
                    code='20100',
                    name='الموردون',
                    account_type=liability_type,
                    is_active=True
                )
            
            # توليد كود فرعي للمورد - النمط: 2010XXXX
            last_supplier_account = ChartOfAccounts.objects.filter(
                code__startswith='2010',
                parent=parent_account
            ).exclude(code='20100').order_by('-code').first()
            
            if last_supplier_account:
                try:
                    last_number = int(last_supplier_account.code[-4:])
                    new_number = last_number + 1
                except (ValueError, AttributeError, IndexError):
                    new_number = 1
            else:
                new_number = 1
            
            # توليد الكود الجديد: 2010 + 4 digits
            account_code = f"2010{new_number:04d}"
            
            # التأكد من عدم تكرار الكود
            while ChartOfAccounts.objects.filter(code=account_code).exists():
                new_number += 1
                account_code = f"2010{new_number:04d}"
            
            # إنشاء الحساب المحاسبي
            financial_account = ChartOfAccounts.objects.create(
                code=account_code,
                name=f"{supplier.name} - {supplier.code}",
                account_type=liability_type,
                parent=parent_account,
                is_active=True
            )
            
            # ربط الحساب بالمورد - استخدام update() لتجنب تشغيل الـ signal
            from supplier.models import Supplier
            Supplier.objects.filter(pk=supplier.pk).update(financial_account=financial_account)
            supplier.financial_account = financial_account  # Update in-memory instance
            
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
            
            # إجمالي المشتريات
            total_purchases = Purchase.objects.filter(
                supplier=supplier,
                status='confirmed'
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            
            # إجمالي المدفوعات
            total_payments = PurchasePayment.objects.filter(
                purchase__supplier=supplier,
                status='posted'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            # الرصيد = المشتريات - المدفوعات
            balance = total_purchases - total_payments
            
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
            purchases_stats = Purchase.objects.filter(
                supplier=supplier,
                status='confirmed'
            ).aggregate(
                total_purchases=Sum('total'),
                count=Count('id')
            )
            
            # إحصائيات المدفوعات
            payments_stats = PurchasePayment.objects.filter(
                purchase__supplier=supplier,
                status='posted'
            ).aggregate(
                total_payments=Sum('amount'),
                count=Count('id')
            )
            
            total_purchases = purchases_stats['total_purchases'] or Decimal('0')
            total_payments = payments_stats['total_payments'] or Decimal('0')
            balance = total_purchases - total_payments
            
            # آخر معاملة
            last_purchase = Purchase.objects.filter(
                supplier=supplier,
                status='confirmed'
            ).order_by('-date').first()
            
            last_payment = PurchasePayment.objects.filter(
                purchase__supplier=supplier,
                status='posted'
            ).order_by('-payment_date').first()
            
            return {
                'total_purchases': total_purchases,
                'purchases_count': purchases_stats['count'] or 0,
                'total_payments': total_payments,
                'payments_count': payments_stats['count'] or 0,
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
    @transaction.atomic
    def delete_supplier(supplier, user=None):
        """
        حذف مورد (soft delete - تعطيل فقط)
        
        Args:
            supplier: المورد المراد حذفه
            user: المستخدم
            
        Note:
            لا يتم حذف المورد فعلياً، بل يتم تعطيله فقط للحفاظ على سلامة البيانات
        """
        try:
            # التحقق من عدم وجود معاملات مرتبطة
            from purchase.models import Purchase
            
            purchases_count = Purchase.objects.filter(supplier=supplier).count()
            
            if purchases_count > 0:
                # تعطيل المورد بدلاً من الحذف
                supplier.is_active = False
                supplier.save(update_fields=['is_active'])
                logger.info(f"✅ تم تعطيل المورد {supplier.name} ({supplier.code}) - لديه {purchases_count} معاملة")
                return {
                    'success': True,
                    'action': 'deactivated',
                    'message': f'تم تعطيل المورد - لديه {purchases_count} معاملة مرتبطة'
                }
            else:
                # حذف فعلي إذا لم يكن لديه معاملات
                supplier_name = supplier.name
                supplier_code = supplier.code
                supplier.delete()
                logger.info(f"✅ تم حذف المورد {supplier_name} ({supplier_code})")
                return {
                    'success': True,
                    'action': 'deleted',
                    'message': 'تم حذف المورد بنجاح'
                }
            
        except Exception as e:
            logger.error(f"❌ خطأ في حذف المورد {supplier.code}: {str(e)}")
            raise

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
