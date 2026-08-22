"""
FIN-CORE-SSOT: SubledgerAccountService
المحرك المركزي الموحد لإدارة وإنشاء ومزامنة حسابات الأستاذ المساعد للعملاء والموردين.
يتعامل بدقة مع الحسابات الرقابية (Control Accounts) وحسابات الأستاذ المساعد (Subledger Accounts).
"""

import logging
from typing import Optional, Tuple, Any
from django.db import transaction, DatabaseError
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.services.role_registry import AccountRoleRegistry, RoleConfigurationError

logger = logging.getLogger(__name__)
User = get_user_model()


class SubledgerAccountService:
    """
    المحرك المركزي الموحد لإدارة حسابات الأستاذ المساعد (Subledger Accounts)
    للعملاء (تحت 11210) والموردين (تحت 21110) وأي كيانات تجارية أخرى.
    """

    @classmethod
    def _resolve_control_account(
        cls, 
        role_name: str, 
        default_code: str, 
        default_name: str,
        category: str = "asset",
        nature: str = "debit"
    ) -> Optional[ChartOfAccounts]:
        """
        تحديد الحساب الرقابي (Control Account) في شجرة الحسابات.
        يبحث في سجل الأدوار أولاً، ثم بالكود الافتراضي، ثم ينشئه تلقائياً إذا لم يكن موجوداً.
        """
        import os
        from django.conf import settings
        from financial.services.role_registry import RoleConfigurationError

        # 1. فحص ما إذا كان هناك Override صريح من البيئة أو الإعدادات
        env_var_name = f"ACCOUNT_ROLE_{role_name.upper()}"
        env_code = os.getenv(env_var_name) or getattr(settings, env_var_name, None)
        if env_code:
            account = ChartOfAccounts.objects.filter(code=str(env_code).strip(), is_active=True).first()
            if account:
                return account
            raise RoleConfigurationError(f"الحساب الرقابي المحدد في المتغير البيئي ({env_code}) للدور {role_name} غير موجود أو غير نشط")

        # 2. فحص الحساب الرقابي في شجرة الحسابات (بالكود الافتراضي أو كود الدور)
        control_code = default_code
        try:
            resolved = AccountRoleRegistry.get_account_code(role_name)
            if resolved:
                control_code = resolved
        except Exception:
            pass

        account = ChartOfAccounts.objects.filter(code=control_code).first()
        if account:
            if not account.is_active:
                account.is_active = True
                account.save(update_fields=["is_active"])
            return account

        # 3. محاولة الإنشاء التلقائي للحساب الرقابي (Self-Healing Control Account)
        try:
            account_type = AccountType.objects.filter(category=category).first()
            if not account_type:
                account_type = AccountType.objects.first()
            if not account_type:
                account_type, _ = AccountType.objects.get_or_create(
                    code=category.upper(),
                    defaults={
                        "name": default_name,
                        "category": category,
                        "nature": nature
                    }
                )

            if account_type:
                control_account = ChartOfAccounts.objects.create(
                    code=default_code,
                    name=default_name,
                    account_type=account_type,
                    level=3 if len(default_code) == 5 else 2,
                    is_control_account=True,
                    is_leaf=False,
                    is_active=True
                )
                logger.info(f"✅ تم إنشاء الحساب الرقابي المفقود تلقائياً: {default_code} - {default_name}")
                return control_account
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء الحساب الرقابي {default_code}: {e}")

        return None

    @classmethod
    def _generate_next_sub_code(cls, parent_account: ChartOfAccounts) -> Tuple[str, ChartOfAccounts]:
        """
        توليد الكود التالي الفريد تحت الحساب الرقابي بشكل ذري مع قفل تزامني.
        - للحسابات الخماسية (11210 / 21110 / 11160): يُولد كود ثماني (8 أرقام) مثل 11210001
        - للحسابات الفرعية الأخرى: يحدد الطول والتسلسل ديناميكياً
        """
        # إعادة جلب الحساب الرقابي مع قفل تزامني (Row-level Lock)
        locked_parent = (
            ChartOfAccounts.objects.select_for_update()
            .filter(pk=parent_account.pk)
            .first()
        )
        if not locked_parent:
            locked_parent = parent_account

        parent_code = str(locked_parent.code).strip()
        prefix_len = len(parent_code)

        # استخراج جميع الأكواد الفرعية المباشرة تحت الحساب الرقابي
        existing_sub_codes = list(
            ChartOfAccounts.objects.filter(
                code__startswith=parent_code
            ).exclude(code=parent_code).values_list("code", flat=True)
        )

        max_seq = 0
        pad_width = 4  # الافتراضي 8 خانات إذا كان الأب 5 خانات
        if prefix_len == 5:
            target_len = 8
            pad_width = 3 if target_len - prefix_len == 3 else 4
        elif prefix_len == 4:
            target_len = 6
            pad_width = 2
        else:
            target_len = prefix_len + 3
            pad_width = 3

        for code_str in existing_sub_codes:
            code_clean = str(code_str).strip()
            if code_clean.startswith(parent_code) and len(code_clean) > prefix_len:
                suffix = code_clean[prefix_len:]
                if suffix.isdigit():
                    seq = int(suffix)
                    if seq > max_seq:
                        max_seq = seq

        next_seq = max_seq + 1
        sub_code = f"{parent_code}{next_seq:0{pad_width}d}"

        # التحقق من عدم التعارض وإعادة المحاولة إن لزم
        while ChartOfAccounts.objects.filter(code=sub_code).exists():
            next_seq += 1
            sub_code = f"{parent_code}{next_seq:0{pad_width}d}"

        return sub_code, locked_parent

    @classmethod
    def create_subledger_account(
        cls,
        entity: Any,
        role_name: str,
        default_code: str,
        default_name: str,
        category: str = "asset",
        nature: str = "debit",
        user: Optional[User] = None
    ) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب أستاذ مساعد لكيان تجاري (عميل / مورد) تحت حسابه الرقابي المعين.
        """
        if not entity:
            return None

        # 1. التحقق إذا كان الكيان يملك بالفعل حساباً فعالاً
        if hasattr(entity, "financial_account") and entity.financial_account and entity.financial_account.is_active:
            return entity.financial_account

        try:
            with transaction.atomic():
                # 2. تحديد الحساب الرقابي الحاكم
                parent_account = cls._resolve_control_account(
                    role_name=role_name,
                    default_code=default_code,
                    default_name=default_name,
                    category=category,
                    nature=nature
                )

                if not parent_account:
                    logger.error(f"❌ تعذر تحديد الحساب الرقابي لـ {entity} (الدور: {role_name}, الكود: {default_code})")
                    return None

                # 3. توليد الكود التالي الفريد تحت الحساب الرقابي مع قفل تزامني
                account_code, locked_parent = cls._generate_next_sub_code(parent_account)

                # 4. تحديد اسم الحساب وعملته ونوع الحساب الموروث
                entity_name = getattr(entity, "name", "") or getattr(entity, "company_name", "") or f"طرف {entity.pk}"
                account_name = str(entity_name).strip()
                currency = getattr(entity, "currency", "EGP") or "EGP"

                # وراثة نوع الحساب من الحساب الرقابي
                account_type = locked_parent.account_type
                if not account_type:
                    account_type = AccountType.objects.filter(category=category).first() or AccountType.objects.first()

                from financial.models.currency import Currency
                curr_obj = None
                if currency:
                    curr_obj = Currency.objects.filter(code=currency).first()
                if not curr_obj:
                    curr_obj = Currency.objects.filter(is_functional=True).first()

                # 5. إنشاء حساب الأستاذ المساعد في شجرة الحسابات
                subledger_account = ChartOfAccounts.objects.create(
                    code=account_code,
                    name=account_name,
                    account_type=account_type,
                    parent=locked_parent,
                    currency=curr_obj,
                    level=locked_parent.level + 1 if locked_parent.level else 4,
                    is_leaf=True,
                    is_active=True
                )

                # 6. ربط الحساب بالكيان وحفظه دون إطلاق سيجنالز تكرارية
                if hasattr(entity, "financial_account"):
                    entity.financial_account = subledger_account
                    if getattr(entity, "pk", None):
                        try:
                            entity.save(update_fields=["financial_account"])
                        except Exception:
                            entity.save()
                    else:
                        entity.save()

                logger.info(f"✅ تم إنشاء حساب أستاذ مساعد بنجاح: {account_code} - {account_name} للكيان ID={entity.pk}")
                return subledger_account

        except RoleConfigurationError:
            raise
        except Exception as e:
            logger.error(f"❌ خطأ أثناء إنشاء حساب الأستاذ المساعد للكيان {entity}: {e}", exc_info=True)
            return None

    @classmethod
    def create_customer_account(cls, customer: Any, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """إنشاء حساب أستاذ مساعد للعميل تحت الحساب الرقابي 11210 (العملاء)"""
        return cls.create_subledger_account(
            entity=customer,
            role_name="CUSTOMER_RECEIVABLE_CONTROL",
            default_code="11210",
            default_name="العملاء",
            category="asset",
            nature="debit",
            user=user
        )

    @classmethod
    def create_supplier_account(cls, supplier: Any, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """إنشاء حساب أستاذ مساعد للمورد تحت الحساب الرقابي 21110 (الموردون)"""
        return cls.create_subledger_account(
            entity=supplier,
            role_name="SUPPLIER_PAYABLE_CONTROL",
            default_code="21110",
            default_name="الموردون",
            category="liability",
            nature="credit",
            user=user
        )

    @classmethod
    def get_or_create_customer_account(cls, customer: Any, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """الحصول على الحساب المحاسبي للعميل أو إنشاؤه إذا لم يكن موجوداً"""
        if not customer:
            return None
        if getattr(customer, "financial_account", None) and customer.financial_account.is_active:
            return customer.financial_account
        return cls.create_customer_account(customer, user)

    @classmethod
    def get_or_create_supplier_account(cls, supplier: Any, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """الحصول على الحساب المحاسبي للمورد أو إنشاؤه إذا لم يكن موجوداً"""
        if not supplier:
            return None
        if getattr(supplier, "financial_account", None) and supplier.financial_account.is_active:
            return supplier.financial_account
        return cls.create_supplier_account(supplier, user)

    @classmethod
    def sync_entity_to_account(cls, entity: Any) -> bool:
        """
        مزامنة بيانات الكيان (الاسم، العملة، الحالة) مع حسابه المحاسبي في شجرة الحسابات.
        """
        if not entity or not getattr(entity, "financial_account", None):
            return False

        try:
            account = entity.financial_account
            entity_name = str(getattr(entity, "name", "") or getattr(entity, "company_name", "")).strip()
            entity_currency = getattr(entity, "currency", "EGP") or "EGP"
            
            # تحديد ما إذا كان الكيان نشطاً
            is_active = True
            if hasattr(entity, "is_active"):
                is_active = entity.is_active
            elif hasattr(entity, "status"):
                is_active = (entity.status == "active")

            updated_fields = []
            if entity_name and account.name != entity_name:
                account.name = entity_name
                updated_fields.append("name")

            # مزامنة العملة إذا كانت محددة
            if hasattr(entity, "currency") or hasattr(entity, "default_currency"):
                raw_curr = getattr(entity, "currency", None) or getattr(entity, "default_currency", None)
                from financial.models.currency import Currency
                curr_obj = None
                if isinstance(raw_curr, Currency):
                    curr_obj = raw_curr
                elif isinstance(raw_curr, str) and raw_curr:
                    curr_obj = Currency.objects.filter(code=raw_curr).first()

                if curr_obj and account.currency != curr_obj:
                    account.currency = curr_obj
                    updated_fields.append("currency")

            if account.is_active != is_active:
                account.is_active = is_active
                updated_fields.append("is_active")

            if updated_fields:
                account.save(update_fields=updated_fields)
                logger.info(f"🔄 تم مزامنة حساب الأستاذ المساعد {account.code} مع الكيان {entity.pk}")

            return True
        except Exception as e:
            logger.error(f"❌ فشل مزامنة الحساب المحاسبي للكيان {entity}: {e}")
            return False

    @classmethod
    def handle_entity_deletion(cls, entity: Any) -> bool:
        """
        معالجة حذف الكيان: تعطيل الحساب المحاسبي بدلاً من حذفه نهائياً لحماية القيود التاريخية.
        """
        if not entity or not getattr(entity, "financial_account", None):
            return False

        try:
            account = entity.financial_account
            if account.is_active:
                account.is_active = False
                account.save(update_fields=["is_active"])
                logger.info(f"🔒 تم تعطيل حساب الأستاذ المساعد {account.code} بعد حذف الكيان {entity.pk}")
            return True
        except Exception as e:
            logger.error(f"❌ فشل تعطيل الحساب المحاسبي عند حذف الكيان {entity}: {e}")
            return False
