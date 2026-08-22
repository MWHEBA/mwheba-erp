import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional
from django.db import transaction, models
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry
from financial.exceptions import ImmutableLedgerError
from financial.services.opening_balance_service import RoundingTolerancePolicy

logger = logging.getLogger("financial.opening_balance_balancing_service")


def _normalize_text(text: str) -> str:
    """تطبيع النصوص العربية للبحث المرن عن أسماء الحسابات القياسية"""
    if not text:
        return ""
    t = text.strip().lower()
    t = t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    t = t.replace('ة', 'ه').replace('ى', 'ي')
    return t


class SmartBalancingService:
    """
    محرك ومساعد الموازنة والمطابقة الذكي للأرصدة الافتتاحية (Enterprise Smart Equity Balancing Engine)
    مسؤول عن:
    1. تحليل فارق التوازن المالي واتجاهه (فائض أصول دائن مقابل عجز مالي مدين).
    2. الترتيب الذكي للسيناريوهات المحاسبية وتحديد الخيار الموصى به.
    3. دعم الموازنة الكاملة (100%)، التوزيع المزدوج (Split Balancing)، والترصيد الصافي الجبري (Algebraic Netting).
    4. ضمان سلامة المعايير المالية (IAS 21) وحماية الحسابات الحاكمة وقصر القيد على الحسابات النهائية (Leaf Accounts).
    """

    @classmethod
    def get_balancing_analysis(cls, batch: OpeningBalanceBatch) -> Dict[str, Any]:
        """
        تحليل حالة الدفعة وحساب الفارق المالي وتوليد قائمة السيناريوهات المرتبة ذكياً
        مع توافقية كاملة للعقود المزدوجة (Dual-Key Compatibility)
        """
        func_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.filter(is_active=True).first()
        func_code = func_curr.code if func_curr else ""
        func_symbol = func_curr.symbol if (func_curr and func_curr.symbol) else func_code
        tolerance = RoundingTolerancePolicy.get_tolerance(func_code)

        lines = list(batch.lines.select_related('account', 'account__account_type').all())
        if len(lines) == 0:
            return {
                'batch_id': batch.id,
                'total_debit': 0.0,
                'total_credit': 0.0,
                'raw_diff': 0.0,
                'raw_difference': 0.0,
                'abs_diff': 0.0,
                'abs_difference': 0.0,
                'direction': 'EMPTY',
                'is_balanced': False,
                'is_empty': True,
                'currency_code': func_code,
                'currency_symbol': func_symbol,
                'rounding_tolerance': float(tolerance),
                'scenarios': [],
                'split_supported': False,
                'equity_accounts': []
            }

        total_debit = sum((l.debit for l in lines), Decimal('0.00'))
        total_credit = sum((l.credit for l in lines), Decimal('0.00'))
        raw_diff = total_debit - total_credit
        abs_diff = abs(raw_diff)
        is_balanced = (len(lines) > 0 and abs_diff <= tolerance)

        if abs_diff <= Decimal('0.000001'):
            direction = 'BALANCED'
        elif raw_diff > Decimal('0.00'):
            direction = 'CREDIT_NEEDED'  # الأصول أكبر ⬅️ نحتاج دائن
        else:
            direction = 'DEBIT_NEEDED'   # الخصوم أكبر ⬅️ نحتاج مدين

        # 1. كشف حالة المنشأة (جديدة أم قائمة)
        is_new_entity = cls._detect_if_new_entity(batch)

        # 2. حصر حسابات حقوق الملكية النهائية القابلة للقيد فقط (Leaf Accounts Only)
        equity_accounts = [
            acc for acc in ChartOfAccounts.objects.filter(
                account_type__category='equity',
                is_active=True
            ).order_by('code')
            if acc.is_leaf and not acc.children.exists()
        ]

        # خريطة السطور الحالية في الدفعة
        existing_lines_map = {}
        for l in lines:
            if l.account_id:
                existing_lines_map[l.account_id] = {
                    'line_id': l.id,
                    'line_type': l.line_type,
                    'debit': float(l.debit),
                    'credit': float(l.credit)
                }

        # 3. إيجاد الحسابات القياسية بمرونة التطبيع الصرفي
        capital_acc = cls._find_capital_account(equity_accounts)
        retained_acc = cls._find_retained_earnings_account(batch, equity_accounts)
        losses_acc = cls._find_accumulated_losses_account(equity_accounts)
        suspense_acc = cls._find_suspense_account(equity_accounts)
        partner_accounts = [
            acc for acc in equity_accounts
            if 'شريك' in _normalize_text(acc.name) or 'partner' in (acc.name_en or '').lower() or str(acc.code).startswith('302')
        ]

        # 4. بناء السيناريوهات وترتيبها
        scenarios = []

        if direction == 'CREDIT_NEEDED':
            # السيناريو 1: رأس المال
            if capital_acc:
                scenarios.append({
                    'key': 'CAPITAL',
                    'title': _("رأس المال المدفوع"),
                    'account_id': capital_acc.id,
                    'account_code': capital_acc.code,
                    'account_name': capital_acc.name,
                    'is_recommended': is_new_entity,
                    'recommendation_reason': _("موصى به للمنشآت الجديدة وأول سنة مالية") if is_new_entity else "",
                    'description': _("إثبات رأس المال التأسيسي للملاك بحقوق الملكية."),
                    'desc': _("إثبات رأس المال التأسيسي للملاك بحقوق الملكية."),
                    'consequences': "",
                    'target_side': 'CREDIT',
                    'has_existing_line': capital_acc.id in existing_lines_map,
                    'existing_line': existing_lines_map.get(capital_acc.id)
                })

            # السيناريو 2: الأرباح المبقاة
            if retained_acc:
                scenarios.append({
                    'key': 'RETAINED_EARNINGS',
                    'title': _("الأرباح المبقاة / المتراكمة"),
                    'account_id': retained_acc.id,
                    'account_code': retained_acc.code,
                    'account_name': retained_acc.name,
                    'is_recommended': not is_new_entity,
                    'recommendation_reason': _("موصى به للشركات القائمة والمستمرة من سنوات سابقة") if not is_new_entity else "",
                    'description': _("ترحيل صافي أرباح السنوات السابقة دون المساس برأس المال."),
                    'desc': _("ترحيل صافي أرباح السنوات السابقة دون المساس برأس المال."),
                    'consequences': "",
                    'target_side': 'CREDIT',
                    'has_existing_line': retained_acc.id in existing_lines_map,
                    'existing_line': existing_lines_map.get(retained_acc.id)
                })

            # السيناريو 3: حسابات الشركاء (كخيار واحد مجمع بقائمة منسدلة)
            if partner_accounts:
                p_first = partner_accounts[0]
                scenarios.append({
                    'key': 'PARTNER',
                    'title': _("جاري الشريك"),
                    'is_partner_selector': True,
                    'partner_accounts': [
                        {
                            'id': p.id,
                            'code': p.code,
                            'name': p.name,
                            'has_existing_line': p.id in existing_lines_map
                        }
                        for p in partner_accounts
                    ],
                    'account_id': p_first.id,
                    'account_code': p_first.code,
                    'account_name': p_first.name,
                    'is_recommended': False,
                    'recommendation_reason': "",
                    'description': _("توجيه الفارق المالي لحساب جاري الشريك المحدد."),
                    'desc': _("توجيه الفارق المالي لحساب جاري الشريك المحدد."),
                    'consequences': "",
                    'target_side': 'CREDIT',
                    'has_existing_line': p_first.id in existing_lines_map,
                    'existing_line': existing_lines_map.get(p_first.id)
                })

        elif direction == 'DEBIT_NEEDED':
            # حالة العجز المالي
            if losses_acc:
                scenarios.append({
                    'key': 'ACCUMULATED_LOSSES',
                    'title': _("الخسائر المرحلة"),
                    'account_id': losses_acc.id,
                    'account_code': losses_acc.code,
                    'account_name': losses_acc.name,
                    'is_recommended': True,
                    'recommendation_reason': _("موصى به لحالات العجز المالي (الالتزامات أكبر من الأصول)"),
                    'description': _("إثبات العجز المالي المتراكم كبند مدين بحقوق الملكية."),
                    'desc': _("إثبات العجز المالي المتراكم كبند مدين بحقوق الملكية."),
                    'consequences': "",
                    'target_side': 'DEBIT',
                    'has_existing_line': losses_acc.id in existing_lines_map,
                    'existing_line': existing_lines_map.get(losses_acc.id)
                })

            if partner_accounts:
                p_first = partner_accounts[0]
                scenarios.append({
                    'key': 'PARTNER',
                    'title': _("مسحوبات / جاري الشريك"),
                    'is_partner_selector': True,
                    'partner_accounts': [
                        {
                            'id': p.id,
                            'code': p.code,
                            'name': p.name,
                            'has_existing_line': p.id in existing_lines_map
                        }
                        for p in partner_accounts
                    ],
                    'account_id': p_first.id,
                    'account_code': p_first.code,
                    'account_name': p_first.name,
                    'is_recommended': False,
                    'recommendation_reason': "",
                    'description': _("إثبات مسحوبات الشريك أو رصيده المدين بحقوق الملكية."),
                    'desc': _("إثبات مسحوبات الشريك أو رصيده المدين بحقوق الملكية."),
                    'consequences': "",
                    'target_side': 'DEBIT',
                    'has_existing_line': p_first.id in existing_lines_map,
                    'existing_line': existing_lines_map.get(p_first.id)
                })

        # دائماً نضيف خيار الحساب الوسيط في النهاية
        if suspense_acc:
            scenarios.append({
                'key': 'SUSPENSE',
                'title': _("حساب وسيط الأرصدة الافتتاحية"),
                'account_id': suspense_acc.id,
                'account_code': suspense_acc.code,
                'account_name': suspense_acc.name,
                'is_recommended': False,
                'recommendation_reason': "",
                'description': _("تسوية مؤقتة للفارق لحين المراجعة قبل اعتماد الميزانية."),
                'desc': _("تسوية مؤقتة للفارق لحين المراجعة قبل اعتماد الميزانية."),
                'consequences': "",
                'target_side': 'CREDIT' if direction == 'CREDIT_NEEDED' else 'DEBIT',
                'is_suspense': True,
                'has_existing_line': suspense_acc.id in existing_lines_map,
                'existing_line': existing_lines_map.get(suspense_acc.id)
            })

        # ترتيب بحيث يأتي الموصى به أولاً
        scenarios.sort(key=lambda s: (not s.get('is_recommended', False), s.get('is_suspense', False)))

        # تجهيز خيارات التوزيع المزدوج (Split)
        split_supported = (direction == 'CREDIT_NEEDED' and capital_acc is not None and retained_acc is not None)

        return {
            'batch_id': batch.id,
            'status': batch.status,
            'total_debit': float(total_debit),
            'total_credit': float(total_credit),
            'raw_diff': float(raw_diff),
            'raw_difference': float(raw_diff),
            'abs_diff': float(abs_diff),
            'abs_difference': float(abs_diff),
            'is_balanced': is_balanced,
            'direction': direction,
            'is_new_entity': is_new_entity,
            'scenarios': scenarios,
            'split_supported': split_supported,
            'currency_code': func_code,
            'currency_symbol': func_symbol,
            'rounding_tolerance': float(tolerance),
            'default_capital_account_id': capital_acc.id if capital_acc else None,
            'default_retained_account_id': retained_acc.id if retained_acc else None,
            'equity_accounts': [
                {'id': acc.id, 'code': acc.code, 'name': acc.name}
                for acc in equity_accounts
            ]
        }

    @classmethod
    def _apply_netted_line(cls, batch: OpeningBalanceBatch, account: ChartOfAccounts, needed_debit: Decimal, needed_credit: Decimal):
        """
        دالة مركزية للترصيد الصافي الجبري (Algebraic Netting):
        تمنع حدوث أي تضارب بين المدين والدائن في السطر الواحد، وتحذف السطر تلقائياً إذا وصل الصافي إلى الصفر.
        """
        existing_line = batch.lines.filter(account=account).first()
        if existing_line:
            net = (existing_line.debit - existing_line.credit) + (needed_debit - needed_credit)
            if net > Decimal('0.00'):
                existing_line.debit = net
                existing_line.credit = Decimal('0.00')
                existing_line.line_type = 'EQUITY'
                existing_line.currency = None
                existing_line.debit_foreign = Decimal('0.00')
                existing_line.credit_foreign = Decimal('0.00')
                existing_line.exchange_rate = Decimal('1.000000')
                existing_line.full_clean()
                existing_line.save()
            elif net < Decimal('0.00'):
                existing_line.debit = Decimal('0.00')
                existing_line.credit = abs(net)
                existing_line.line_type = 'EQUITY'
                existing_line.currency = None
                existing_line.debit_foreign = Decimal('0.00')
                existing_line.credit_foreign = Decimal('0.00')
                existing_line.exchange_rate = Decimal('1.000000')
                existing_line.full_clean()
                existing_line.save()
            else:
                # تصفير السطر تماماً -> حذفه لتنظيف الدفعة ومنع خطأ clean()
                existing_line.delete()
        else:
            if needed_debit > Decimal('0.00') or needed_credit > Decimal('0.00'):
                new_line = OpeningBalanceLine(
                    batch=batch,
                    account=account,
                    line_type='EQUITY',
                    debit=needed_debit,
                    credit=needed_credit,
                    currency=None,
                    debit_foreign=Decimal('0.00'),
                    credit_foreign=Decimal('0.00'),
                    exchange_rate=Decimal('1.000000')
                )
                new_line.full_clean()
                new_line.save()

    @classmethod
    @transaction.atomic
    def apply_balancing(cls, batch: OpeningBalanceBatch, mode: str, data: Dict[str, Any], user) -> Dict[str, Any]:
        """
        تطبيق الموازنة داخل معاملة ذرية متوافقة مع معايير الحوكمة المالية والترصيد الصافي الجبري
        """
        batch = OpeningBalanceBatch.objects.select_for_update().get(pk=batch.id)

        if batch.status in ['posted', 'reversed']:
            raise ImmutableLedgerError(_("لا يمكن موازنة دفعة مرحلة أو معكوسة."))

        lines = list(batch.lines.all())
        total_debit = sum((l.debit for l in lines), Decimal('0.00'))
        total_credit = sum((l.credit for l in lines), Decimal('0.00'))
        raw_diff = total_debit - total_credit
        abs_diff = abs(raw_diff)

        func_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.filter(is_active=True).first()
        func_code = func_curr.code if func_curr else ""
        tolerance = RoundingTolerancePolicy.get_tolerance(func_code)

        if abs_diff <= tolerance:
            return {
                'success': True,
                'message': _("الدفعة متزنة بالفعل."),
                'is_balanced': True,
                'total_debit': float(total_debit),
                'total_credit': float(total_credit),
                'balance_diff': float(abs_diff)
            }

        if mode == 'SINGLE':
            account_id = data.get('account_id')
            if not account_id:
                raise ValidationError(_("يجب تحديد الحساب المحاسبي للموازنة."))

            account = ChartOfAccounts.objects.filter(pk=account_id, is_active=True).first()
            if not account or not account.is_leaf or account.children.exists():
                raise ValidationError(_("الحساب المحاسبي غير موجود أو غير نشط أو ليس حساباً نهائياً."))

            if raw_diff > 0:
                needed_debit = Decimal('0.00')
                needed_credit = abs_diff
            else:
                needed_debit = abs_diff
                needed_credit = Decimal('0.00')

            cls._apply_netted_line(batch, account, needed_debit, needed_credit)

        elif mode == 'SPLIT':
            capital_account_id = data.get('capital_account_id')
            retained_account_id = data.get('retained_account_id')

            if not capital_account_id or not retained_account_id:
                raise ValidationError(_("يجب تحديد حساب رأس المال وحساب الأرباح المبقاة."))

            if str(capital_account_id) == str(retained_account_id):
                raise ValidationError(_("لا يمكن اختيار نفس الحساب لكلا حصتي التوزيع."))

            capital_amount = Decimal(str(data.get('capital_amount', '0.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            if capital_amount < Decimal('0.00') or capital_amount > abs_diff:
                raise ValidationError(_("مبلغ رأس المال غير صالح. يجب أن يكون بين 0 و {}").format(abs_diff))

            retained_amount = (abs_diff - capital_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            capital_acc = ChartOfAccounts.objects.filter(pk=capital_account_id, is_active=True).first()
            retained_acc = ChartOfAccounts.objects.filter(pk=retained_account_id, is_active=True).first()

            if not capital_acc or not capital_acc.is_leaf or capital_acc.children.exists():
                raise ValidationError(_("حساب رأس المال غير صالح أو ليس حساباً نهائياً."))

            if not retained_acc or not retained_acc.is_leaf or retained_acc.children.exists():
                raise ValidationError(_("حساب الأرباح المبقاة غير صالح أو ليس حساباً نهائياً."))

            # تطبيق الترصيد الصافي لكل من رأس المال والأرباح
            if raw_diff > 0:
                cls._apply_netted_line(batch, capital_acc, Decimal('0.00'), capital_amount)
                cls._apply_netted_line(batch, retained_acc, Decimal('0.00'), retained_amount)
            else:
                cls._apply_netted_line(batch, capital_acc, capital_amount, Decimal('0.00'))
                cls._apply_netted_line(batch, retained_acc, retained_amount, Decimal('0.00'))

        else:
            raise ValidationError(_("نمط الموازنة غير معروف: {}").format(mode))

        # إعادة حساب الإجماليات
        updated_lines = list(batch.lines.all())
        new_total_debit = sum((l.debit for l in updated_lines), Decimal('0.00'))
        new_total_credit = sum((l.credit for l in updated_lines), Decimal('0.00'))
        new_diff = abs(new_total_debit - new_total_credit)
        new_balanced = (len(updated_lines) > 0 and new_diff <= Decimal('0.05'))

        logger.info(f"Smart balancing applied on Batch {batch.batch_number} by User {user.username}: mode={mode}, new_diff={new_diff}")

        return {
            'success': True,
            'message': _("تمت موازنة الدفعة الافتتاحية بنجاح."),
            'is_balanced': new_balanced,
            'total_debit': float(new_total_debit),
            'total_credit': float(new_total_credit),
            'balance_diff': float(new_diff)
        }

    # =========================================================
    # دوال المساعدة الداخلية
    # =========================================================

    @classmethod
    def _detect_if_new_entity(cls, batch: OpeningBalanceBatch) -> bool:
        """
        فحص ما إذا كانت المنشأة جديدة (لا توجد قيود يومية مرحلة سابقة لتاريخ الرصيد الافتتاحي)
        """
        has_prior_entries = JournalEntry.objects.filter(
            date__lt=batch.opening_date,
            status='posted'
        ).exclude(
            models.Q(reference_type='OPENING_BALANCE') | models.Q(source_module='OPENING_BALANCE')
        ).exists()

        return not has_prior_entries

    @classmethod
    def _find_capital_account(cls, equity_accounts: List[ChartOfAccounts]) -> Optional[ChartOfAccounts]:
        """العثور على حساب رأس المال بمرونة التطبيع الصرفي"""
        # أولاً: بالأكواد القياسية
        for acc in equity_accounts:
            if str(acc.code) in ['30100', '3101', '301000', '3100']:
                return acc
        # ثانياً: بالاسم مع التطبيع
        for acc in equity_accounts:
            norm_name = _normalize_text(acc.name)
            if 'راس المال' in norm_name or 'capital' in (acc.name_en or '').lower():
                return acc
        return equity_accounts[0] if equity_accounts else None

    @classmethod
    def _find_retained_earnings_account(cls, batch: OpeningBalanceBatch, equity_accounts: List[ChartOfAccounts]) -> Optional[ChartOfAccounts]:
        """العثور على حساب الأرباح المبقاة المعتمد للسنة المالية"""
        if batch.fiscal_year and hasattr(batch.fiscal_year, 'get_effective_retained_earnings_account'):
            eff_acc = batch.fiscal_year.get_effective_retained_earnings_account()
            if eff_acc and eff_acc.is_leaf and not eff_acc.children.exists():
                return eff_acc

        for acc in equity_accounts:
            if str(acc.code) in ['30300', '3201', '303000', '3200']:
                return acc
        for acc in equity_accounts:
            norm_name = _normalize_text(acc.name)
            if 'مبقاه' in norm_name or 'محتجزه' in norm_name or 'مرحله' in norm_name or 'retained' in (acc.name_en or '').lower():
                if 'خسائر' not in norm_name and 'خساير' not in norm_name:
                    return acc
        return None

    @classmethod
    def _find_accumulated_losses_account(cls, equity_accounts: List[ChartOfAccounts]) -> Optional[ChartOfAccounts]:
        """العثور على حساب الخسائر المرحلة"""
        for acc in equity_accounts:
            if str(acc.code) in ['30400', '3202', '304000']:
                return acc
        for acc in equity_accounts:
            norm_name = _normalize_text(acc.name)
            if 'خسائر' in norm_name or 'خساير' in norm_name or 'خساره' in norm_name or 'loss' in (acc.name_en or '').lower():
                return acc
        return None

    @classmethod
    def _find_suspense_account(cls, equity_accounts: List[ChartOfAccounts]) -> Optional[ChartOfAccounts]:
        """العثور على حساب وسيط الأرصدة الافتتاحية المعلق"""
        for acc in equity_accounts:
            if str(acc.code) in ['30900', '3999', '309000', '3900']:
                return acc
        for acc in equity_accounts:
            norm_name = _normalize_text(acc.name)
            if 'وسيط' in norm_name or 'معلق' in norm_name or 'تسوي' in norm_name or 'suspense' in (acc.name_en or '').lower():
                return acc
        return None
