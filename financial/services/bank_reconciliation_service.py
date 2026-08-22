import logging
import csv
import io
import hashlib
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntryLine
from financial.models.bank_reconciliation import (
    BankStatementBatch,
    BankStatementLine,
    BankReconciliationMatch,
    BankMatchAllocation
)

logger = logging.getLogger("financial.bank_reconciliation_service")


import dateutil.parser


class SmartBankStatementParser:
    """
    محرك استيراد كشوف الحسابات البنكية الفائق الذكاء (Smart Multi-Bank Statement Engine)
    - يدعم التقاط الأعمدة تلقائياً بجميع الصيغ للبنوك المصرية والعربية والدولية (NBE, CIB, QNB, HSBC, Banque Misr, etc.)
    - يدعم تفكيك وتحديد الأعمدة يدوياً (Custom Column Mapping)
    - يدعم ملفات CSV و Excel (xlsx / xls)
    - يدعم صيغ التاريخ المختلفة (YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY)
    - يدعم حقل المبلغ المفرد مع التخمين الآلي (Single Amount + CR/DR Type)
    """

    DATE_ALIASES = [
        'date', 'transaction date', 'trans date', 'tx date', 'value date', 'posting date',
        'post date', 'effective date', 'book date', 'event date', 'stmt date', 'statement date',
        'تاريخ', 'تاريخ المعاملة', 'تاريخ الحركة', 'تاريخ الاستحقاق', 'تاريخ القيد', 'التاريخ',
        'تاريخ القيمة', 'تاريخ العملية', 'تاريخ المستند', 'تاريخ الإشعار', 'تاريخ الترحيل'
    ]

    REF_ALIASES = [
        'reference', 'ref', 'ref no', 'reference number', 'transaction ref', 'doc no', 'document no',
        'cheque no', 'check no', 'serial no', 'voucher no', 'journal ref', 'batch no', 'audit no', 'rrn',
        'المرجع', 'رقم المرجع', 'الرقم المرجعي', 'رقم الحركة', 'رقم المستند', 'رقم الشيك',
        'مرجع', 'مرجعي', 'رقم مرجعي', 'رقم مرجعي تجريبي', 'رقم العملية', 'رقم المعاملة', 'رقم الإشعار',
        'رقم السند', 'رقم الإذن', 'رقم المسلسل', 'رقم القيد'
    ]

    DESC_ALIASES = [
        'description', 'details', 'narration', 'particulars', 'remarks', 'memo', 'statement details',
        'transaction details', 'line description', 'notes', 'explanation', 'narrative',
        'البيان', 'الوصف', 'تفاصيل المعاملة', 'الشرح', 'ملاحظات', 'التفاصيل', 'البيان والتفاصيل',
        'تفاصيل الحركة', 'بيان الحركة', 'شرح الحركة', 'بيان المستند', 'ملاحظة'
    ]

    DEBIT_ALIASES = [
        'deposit', 'in', 'paid in', 'money in', 'money received', 'inflow', 'receipt',
        'receipts', 'credited amount', 'credit amount', 'credit', 'cr',
        'إيداع', 'إيداعات', 'مقبوضات', 'مدخلات', 'مبالغ مضافة', 'وارد', 'مقبوض', 'مستلم', 'دائن'
    ]

    CREDIT_ALIASES = [
        'withdrawal', 'out', 'paid out', 'charge', 'fee', 'money out', 'money spent',
        'outflow', 'payment', 'payments', 'debited amount', 'debit amount', 'debit', 'dr',
        'سحب', 'مسحوبات', 'مصروفات', 'مخرجات', 'مبالغ مسحوبة', 'منصرف', 'مدفوعات', 'صرف', 'رسوم', 'مدين'
    ]

    AMOUNT_ALIASES = [
        'amount', 'txn amount', 'transaction amount', 'net amount', 'value', 'sum',
        'المبلغ', 'قيمة المعاملة', 'مبلغ الحركة', 'القيمة', 'المبلغ الصافي'
    ]

    TYPE_ALIASES = [
        'type', 'txn type', 'transaction type', 'dr/cr', 'd/c', 'indicator', 'code',
        'نوع المعاملة', 'النوع', 'مدين/دائن', 'كود الحركة'
    ]

    @classmethod
    def _normalize_key(cls, key: Any) -> str:
        if not key:
            return ""
        return str(key).strip().lower().replace('_', ' ').replace('-', ' ')

    @classmethod
    def _match_column(cls, available_cols: List[str], aliases: List[str]) -> Optional[str]:
        import re
        # Pass 1: Exact match
        for col in available_cols:
            norm_col = cls._normalize_key(col)
            for alias in aliases:
                norm_alias = cls._normalize_key(alias)
                if norm_col == norm_alias:
                    return col

        # Pass 2: Word boundary regex match
        for col in available_cols:
            norm_col = cls._normalize_key(col)
            for alias in aliases:
                norm_alias = cls._normalize_key(alias)
                if len(norm_alias) <= 3:
                    if re.search(r'\b' + re.escape(norm_alias) + r'\b', norm_col):
                        return col
                else:
                    if norm_alias in norm_col or norm_col in norm_alias:
                        return col
        return None

    @classmethod
    def _find_header_row_index(cls, raw_matrix: List[List[Any]]) -> int:
        """البحث الذكي عن السطر الحقيقي لترويسة الجدول في أول 25 سطر بالملف"""
        all_aliases = (
            cls.DATE_ALIASES + cls.REF_ALIASES + cls.DESC_ALIASES +
            cls.DEBIT_ALIASES + cls.CREDIT_ALIASES + cls.AMOUNT_ALIASES
        )
        best_row_idx = 0
        max_matches = 0

        for idx, row in enumerate(raw_matrix[:25]):
            if not row:
                continue
            row_str = ' '.join([cls._normalize_key(cell) for cell in row if cell is not None])
            matches = 0
            for alias in all_aliases:
                norm_alias = cls._normalize_key(alias)
                if len(norm_alias) <= 3:
                    import re
                    if re.search(r'\b' + re.escape(norm_alias) + r'\b', row_str):
                        matches += 1
                else:
                    if norm_alias in row_str:
                        matches += 1
            if matches > max_matches:
                max_matches = matches
                best_row_idx = idx
                if max_matches >= 3:
                    break

        return best_row_idx

    @classmethod
    def _clean_amount(cls, val: Any) -> Decimal:
        """تطنيش الرموز وتنظيف المبالغ العربية والأجنبية والأرقام ذات الأقواس"""
        if val is None:
            return Decimal('0.00')
        s = str(val).strip()
        if not s or s.lower() in ['nan', 'none', '-', 'null', 'n/a', '--']:
            return Decimal('0.00')

        # 1. تحويل الأرقام العربية (٠١٢٣٤٥٦٧٨٩) إلى القياسية
        arabic_digits = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        s = s.translate(arabic_digits)

        # 2. فحص الإشارة السالبة (الأقواس المحاسبية أو السالب في البداية/النهاية)
        is_neg = False
        if s.startswith('(') and s.endswith(')'):
            is_neg = True
            s = s[1:-1]
        elif s.startswith('-') or s.endswith('-'):
            is_neg = True
            s = s.replace('-', '')

        # 3. إزالة كافة الأحرف العربية والأجنبية مثل EGP, LE, ج.م, CR, DR
        import re
        s = re.sub(r'[a-zA-Z\u0600-\u06FF]', '', s).strip()

        # معالجة التنسيق الأوروبي (1.500,50) مقابل التنسيق القياسي (1,500.50)
        if '.' in s and ',' in s and s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace('،', '').replace(',', '').replace('٫', '.')

        match = re.search(r'\d+(?:\.\d+)?', s)
        if not match:
            return Decimal('0.00')

        try:
            res = Decimal(match.group(0))
            return -res if is_neg else res
        except Exception:
            return Decimal('0.00')

    @classmethod
    def _extract_smart_reference(cls, ref_val: Any, desc_val: Any) -> str:
        """الالتقاط التلقائي الفائق الذكاء للرقم المرجعي من خانة المرجع أو بداخل نص البيان"""
        s_ref = str(ref_val).strip() if ref_val is not None else ""
        if s_ref and s_ref.lower() not in ['', 'nan', 'none', '--', 'n/a', 'null', '0', '-']:
            return s_ref

        if not desc_val:
            return ""

        s_desc = str(desc_val).strip()
        import re
        # 1. البحث عن نمط "مرجع: FT123456" أو "REF: 998822"
        m1 = re.search(r'(?:ref|reference|rrn|ft|txn|chq|مرجع|المرجع|رقم)\s*[:#\s-]?\s*([a-zA-Z0-9_-]{4,30})', s_desc, re.IGNORECASE)
        if m1:
            return m1.group(1).strip()

        # 2. البحث عن أكواد العمليات البنكية القياسية (FT..., TXN..., CHQ..., أو رقم من 6 لـ 16 خانة)
        m2 = re.search(r'\b(FT[0-9A-Z]{6,16}|TXN[0-9A-Z]{6,16}|CHQ[0-9]{4,10}|[0-9]{6,15})\b', s_desc, re.IGNORECASE)
        if m2:
            return m2.group(1).strip()

        return ""

    @classmethod
    def parse(cls, file_content: Any, column_mapping: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        lines = []
        raw_matrix: List[List[Any]] = []

        # 1. القراءة من مصفوفة بايتات أو نص (CSV / Excel)
        if isinstance(file_content, bytes):
            try:
                import pandas as pd
                df = pd.read_excel(io.BytesIO(file_content), header=None)
                raw_matrix = df.values.tolist()
            except Exception:
                decoded_str = None
                for enc in ['utf-8-sig', 'utf-8', 'cp1256', 'latin1']:
                    try:
                        decoded_str = file_content.decode(enc)
                        break
                    except Exception:
                        continue
                if decoded_str:
                    reader = csv.reader(io.StringIO(decoded_str))
                    raw_matrix = [row for row in reader if any(cell and str(cell).strip() for cell in row)]
        elif isinstance(file_content, str):
            reader = csv.reader(io.StringIO(file_content))
            raw_matrix = [row for row in reader if any(cell and str(cell).strip() for cell in row)]

        if not raw_matrix:
            return []

        # 2. الالتقاط الآلي لسطر ترويسة الجدول في الملف (حتى إذا تضمن 5 سطور عنوان بالنواحي البنكية)
        header_idx = cls._find_header_row_index(raw_matrix)
        if header_idx is None or not isinstance(header_idx, int) or header_idx >= len(raw_matrix):
            header_idx = 0
        header_row = [str(cell).strip() if cell is not None and str(cell) != 'nan' else "" for cell in raw_matrix[header_idx]]
        data_rows = raw_matrix[header_idx + 1:]

        rows = []
        for d_row in data_rows:
            row_dict = {}
            for col_i, col_name in enumerate(header_row):
                if col_name and col_i < len(d_row):
                    val = d_row[col_i]
                    if val is not None and str(val) != 'nan':
                        row_dict[col_name] = val
            if row_dict:
                rows.append(row_dict)

        if not rows:
            return []

        # 3. تحديد خريطة الأعمدة (تلقائياً أو عبر التحديد اليدوي column_mapping)
        first_row = rows[0]
        available_cols = [str(k) for k in first_row.keys() if k is not None]

        user_map = column_mapping or {}
        col_date = user_map.get('date_col') or cls._match_column(available_cols, cls.DATE_ALIASES)
        col_ref = user_map.get('ref_col') or cls._match_column(available_cols, cls.REF_ALIASES)
        col_desc = user_map.get('desc_col') or cls._match_column(available_cols, cls.DESC_ALIASES)
        col_debit = user_map.get('debit_col') or cls._match_column(available_cols, cls.DEBIT_ALIASES)
        col_credit = user_map.get('credit_col') or cls._match_column(available_cols, cls.CREDIT_ALIASES)
        col_amount = user_map.get('amount_col') or cls._match_column(available_cols, cls.AMOUNT_ALIASES)
        col_type = user_map.get('type_col') or cls._match_column(available_cols, cls.TYPE_ALIASES)
        invert_directions = bool(user_map.get('invert_directions'))

        for row in rows:
            raw_date = row.get(col_date) if col_date else None
            parsed_date = timezone.now().date()
            if raw_date and str(raw_date).strip() != '':
                try:
                    s_date = str(raw_date).strip()
                    if '-' in s_date and len(s_date.split('-')[0]) == 4:
                        parsed_date = dateutil.parser.parse(s_date, yearfirst=True).date()
                    else:
                        parsed_date = dateutil.parser.parse(s_date, dayfirst=True).date()
                except Exception:
                    pass

            desc_val = str(row.get(col_desc) or '').strip() if col_desc else ''
            ref_val = cls._extract_smart_reference(row.get(col_ref) if col_ref else None, desc_val)

            debit_val = Decimal('0.00')
            credit_val = Decimal('0.00')

            if col_debit and row.get(col_debit) is not None:
                debit_val = cls._clean_amount(row.get(col_debit))

            if col_credit and row.get(col_credit) is not None:
                credit_val = cls._clean_amount(row.get(col_credit))

            # التعامل مع حقل المبلغ الموحد (Single Amount Column) في حالة عدم وجود عمودين منفصلين
            if debit_val == 0 and credit_val == 0 and col_amount and row.get(col_amount) is not None:
                amt = cls._clean_amount(row.get(col_amount))
                type_str = str(row.get(col_type) or '').upper().strip() if col_type else ''

                if 'CR' in type_str or 'إيداع' in type_str or 'CREDIT' in type_str or amt > 0:
                    debit_val = abs(amt)
                else:
                    credit_val = abs(amt)

            # عكس الاتجاه المحاسبي فقط في حالة اختيار المستخدم لخيار invert_directions صراحةً
            if invert_directions:
                debit_val, credit_val = credit_val, debit_val

            if debit_val > 0 or credit_val > 0 or ref_val or desc_val:
                lines.append({
                    'transaction_date': parsed_date,
                    'reference_number': ref_val,
                    'description': desc_val,
                    'debit': abs(debit_val),
                    'credit': abs(credit_val)
                })

        return lines


GenericCSVParser = SmartBankStatementParser


class BankStatementParserFactory:
    """نمط المصنع لاستيراد كشوف الحسابات البنكية المختلفة (FIN-BANK-004)"""
    @classmethod
    def get_parser(cls, format_type: str = "CSV"):
        return SmartBankStatementParser


class BankCandidateEngine:
    """
    محرك ترشيح حركات الشركة المعلقة غير المطابقة بربط استبعاد كلي للحركات المخصصة أو المطابقة مسبقاً
    """
    @classmethod
    def get_all_uncleared_candidates(cls, bank_account, limit: int = 300) -> List[JournalEntryLine]:
        """
        جلب كافة حركات الدفتر العام المعلقة للحساب البنكي (استبعاد تام لأي حركة بها تخصيص نشط أو مطابقة سابقة)
        """
        qs = JournalEntryLine.objects.filter(
            account=bank_account,
            journal_entry__status='posted'
        ).exclude(
            models.Q(bank_matches__status='MATCHED') |
            models.Q(bank_allocations__status__in=['ACTIVE', 'REVIEW_REQUIRED'])
        ).order_by('-journal_entry__date', '-id')

        return list(qs.select_related('journal_entry')[:limit])

    @classmethod
    def get_candidates(cls, bank_account, stmt_line, limit: int = 100, date_window_days: int = 45) -> List[JournalEntryLine]:
        from datetime import timedelta
        amt = stmt_line.debit if stmt_line.debit > 0 else stmt_line.credit
        is_inflow = stmt_line.debit > 0

        min_date = stmt_line.transaction_date - timedelta(days=date_window_days)
        max_date = stmt_line.transaction_date + timedelta(days=date_window_days)

        qs = JournalEntryLine.objects.filter(
            account=bank_account,
            journal_entry__status='posted',
            journal_entry__date__gte=min_date,
            journal_entry__date__lte=max_date
        )

        # استبعاد الحركات المطابقة بالفعل (is_matched أو بها تخصيص نشط)
        qs = qs.exclude(
            models.Q(bank_matches__status='MATCHED') |
            models.Q(bank_allocations__status__in=['ACTIVE', 'REVIEW_REQUIRED'])
        )

        # الفلترة بحسب اتجاه المعاملة المحاسبي (إيداع/مدين مقابل سحب/دائن)
        if is_inflow:
            qs = qs.filter(debit__gt=0)
        else:
            qs = qs.filter(credit__gt=0)

        # الترتيب حسب تقارب التاريخ والرقم المرجعي
        candidates = list(qs.select_related('journal_entry')[:limit])
        return candidates


class BankReconciliationService:
    """
    محرك التسوية والمطابقة البنكية المؤسسي المفصول (Phase 1 Domain Services)
    """
    ALLOWED_TRANSITIONS = {
        'imported': ['reconciling', 'failed'],
        'reconciling': ['partially_matched', 'completed', 'failed'],
        'partially_matched': ['completed', 'reconciling', 'failed'],
        'completed': ['reopened', 'locked'],
        'reopened': ['reconciling', 'completed'],
        'failed': ['reconciling', 'imported'],
    }

    @classmethod
    def import_statement_batch(
        cls,
        bank_account_id: int,
        statement_date,
        opening_balance: Decimal,
        closing_balance: Decimal,
        lines_data: List[Dict[str, Any]],
        user=None,
        **kwargs
    ) -> BankStatementBatch:
        """استيراد دفعة كشف حساب بنكي برمجياً أو عبر ملف"""
        with transaction.atomic():
            bank_acc = ChartOfAccounts.objects.get(pk=bank_account_id)
            batch_num = kwargs.get('batch_number') or f"STMT-{bank_acc.code}-{statement_date}-{uuid.uuid4().hex[:6]}"
            batch = BankStatementBatch.objects.create(
                batch_number=batch_num,
                bank_account=bank_acc,
                statement_date=statement_date,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                created_by=user,
                status='imported'
            )
            for item in lines_data:
                BankStatementLine.objects.create(
                    batch=batch,
                    transaction_date=item.get('transaction_date', statement_date),
                    reference_number=item.get('reference_number', ''),
                    description=item.get('description', ''),
                    debit=item.get('debit', Decimal('0.00')),
                    credit=item.get('credit', Decimal('0.00')),
                    is_matched=False
                )
            return batch

    @classmethod
    def auto_match_batch(cls, batch_id: int, user=None) -> Dict[str, int]:
        """المطابقة الآلية التلقائية لدفعة كشف الحساب البنكي (Exact & Probable Engine)"""
        with transaction.atomic():
            batch = BankStatementBatch.objects.select_for_update().get(pk=batch_id)
            exact_matches = 0
            probable_matches = 0

            for stmt_line in batch.lines.filter(is_matched=False):
                stmt_amt = stmt_line.debit if stmt_line.debit > 0 else stmt_line.credit
                candidates = BankCandidateEngine.get_candidates(batch.bank_account, stmt_line)
                
                matched_line = None
                is_exact = False
                for c in candidates:
                    c_amt = c.debit if c.debit > 0 else c.credit
                    if abs(c_amt - stmt_amt) <= Decimal('0.01'):
                        ref_match = (
                            c.journal_entry.reference and stmt_line.reference_number and
                            str(c.journal_entry.reference).strip() == str(stmt_line.reference_number).strip()
                        )
                        date_match = (c.journal_entry.date == stmt_line.transaction_date)
                        if ref_match and date_match:
                            matched_line = c
                            is_exact = True
                            break
                        elif matched_line is None:
                            matched_line = c
                            is_exact = False

                if matched_line:
                    if is_exact:
                        BankReconciliationMatch.objects.create(
                            statement_line=stmt_line,
                            journal_line=matched_line,
                            matched_amount=stmt_amt,
                            match_type='EXACT',
                            status='MATCHED',
                            matched_by=user
                        )
                        stmt_line.is_matched = True
                        stmt_line.save(update_fields=['is_matched'])
                        exact_matches += 1
                    else:
                        BankReconciliationMatch.objects.create(
                            statement_line=stmt_line,
                            journal_line=matched_line,
                            matched_amount=stmt_amt,
                            match_type='PROBABLE',
                            status='UNMATCHED',
                            matched_by=user
                        )
                        probable_matches += 1

            cls.update_batch_status(batch)
            return {
                'exact_matches': exact_matches,
                'probable_matches_pending': probable_matches
            }

    @classmethod
    def confirm_match(cls, match_id: int, user=None) -> BankReconciliationMatch:
        """تأكيد المطابقة المرجحة من قبل المستخدم"""
        with transaction.atomic():
            match_obj = BankReconciliationMatch.objects.select_for_update().get(pk=match_id)
            match_obj.status = 'MATCHED'
            match_obj.matched_by = user
            match_obj.save(update_fields=['status', 'matched_by'])

            stmt_line = match_obj.statement_line
            stmt_line.is_matched = True
            stmt_line.save(update_fields=['is_matched'])

            cls.update_batch_status(stmt_line.batch)
            return match_obj

    @classmethod
    def update_batch_status(cls, batch: BankStatementBatch) -> str:
        """تحديث آلة حالات الدفعة أوتوماتيكياً بحوكمة حارس الانتقالات"""
        total_lines = batch.lines.count()
        if total_lines == 0:
            return batch.status

        unmatched_count = batch.lines.filter(is_matched=False).count()
        matched_count = total_lines - unmatched_count

        if unmatched_count == 0:
            target = 'completed'
        elif matched_count > 0:
            target = 'partially_matched'
        else:
            target = 'reconciling'

        current = batch.status
        allowed = cls.ALLOWED_TRANSITIONS.get(current, [])
        if target != current and target in allowed:
            batch.status = target
            batch.save(update_fields=['status'])
        return batch.status

    @classmethod
    def create_allocation(
        cls,
        stmt_line_id: int,
        journal_line_id: int,
        allocated_amount: Optional[Decimal] = None,
        user=None
    ) -> BankMatchAllocation:
        """إنشاء تخصيص مطابقة ذري بحماية القفل التزامني select_for_update وسقف المبلغ"""
        from financial.models.bank_reconciliation import BankMatchAllocation
        with transaction.atomic():
            stmt_line = BankStatementLine.objects.select_for_update().get(pk=stmt_line_id)
            jl = JournalEntryLine.objects.select_for_update().get(pk=journal_line_id)

            stmt_amt = stmt_line.debit if stmt_line.debit > 0 else stmt_line.credit
            jl_amt = jl.debit if jl.debit > 0 else jl.credit

            # 1. التحقق الفائق من اتجاه الحركة (إيداع بنك مدين مقابل مدين دفتر / سحب بنك دائن مقابل دائن دفتر)
            stmt_is_debit = (stmt_line.debit > 0)
            jl_is_debit = (jl.debit > 0)
            if stmt_is_debit != jl_is_debit:
                raise ValueError(_("خطأ في الاتجاه المحاسبي: لا يمكن مطابقة حركة إيداع بنكي مع حركة سحب بالدفتر العام."))

            # 2. التحقق الفائق من تطابق المبالغ المالية
            if allocated_amount is None:
                if abs(stmt_amt - jl_amt) > Decimal('0.05'):
                    raise ValueError(
                        _("خطأ في المطابقة المحاسبية: مبلغ سطر كشف البنك ({} ج.م) لا يتطابق مع مبلغ حركة الدفتر العام ({} ج.م). يجب اختيار حركة بنفس المبلغ.").format(stmt_amt, jl_amt)
                    )
                alloc_amt = stmt_amt
            else:
                alloc_amt = Decimal(str(allocated_amount))
                if alloc_amt > stmt_amt or alloc_amt > jl_amt:
                    raise ValueError(_("المبلغ المخصص ({} ج.م) يتجاوز قيمة حركة البنك أو القيد المحاسبي.").format(alloc_amt))

            # حساب مجموع التخصيصات الحالية
            existing_alloc_sum = stmt_line.allocations.filter(status='ACTIVE').aggregate(
                total=models.Sum('allocated_amount')
            )['total'] or Decimal('0.00')

            if existing_alloc_sum + alloc_amt > stmt_amt:
                raise ValueError(_("مجموع التخصيصات ({}) يتجاوز مبلغ سطر البنك الأصل ({})").format(existing_alloc_sum + alloc_amt, stmt_amt))

            alloc = BankMatchAllocation.objects.create(
                statement_line=stmt_line,
                journal_line=jl,
                allocated_amount=alloc_amt,
                status='ACTIVE',
                created_by=user
            )

            # إذا استوفى سطر البنك مبلغه بالكامل يتم تحويل حالته لـ is_matched=True
            new_total = existing_alloc_sum + alloc_amt
            if new_total >= stmt_amt:
                stmt_line.is_matched = True
                stmt_line.save(update_fields=['is_matched'])

            cls.update_batch_status(stmt_line.batch)
            return alloc

    @classmethod
    def remove_allocation(cls, allocation_id: int, user=None) -> bool:
        """فك تخصيص المطابقة بأمان وإعادة حالة البنود"""
        from financial.models.bank_reconciliation import BankMatchAllocation
        with transaction.atomic():
            alloc = BankMatchAllocation.objects.select_for_update().get(pk=allocation_id)
            stmt_line = alloc.statement_line
            stmt_line.is_matched = False
            stmt_line.save(update_fields=['is_matched'])

            alloc.status = 'REVERSED'
            alloc.save(update_fields=['status'])

            cls.update_batch_status(stmt_line.batch)
            return True

    @classmethod
    def create_direct_bank_adjustment(
        cls,
        batch_id: int,
        stmt_line_id: int,
        expense_account_id: int,
        amount: Decimal,
        description: str,
        user=None,
        cost_center_id=None
    ) -> BankMatchAllocation:
        """إنشاء وتأكيد قيد المصاريف/العمولات البنكية الفوري المباشر عبر LedgerCoreService و SequenceService"""
        from financial.services.ledger_core_service import LedgerCoreService
        from financial.models.chart_of_accounts import ChartOfAccounts
        from financial.models.bank_reconciliation import BankMatchAllocation

        batch = BankStatementBatch.objects.get(pk=batch_id)
        stmt_line = BankStatementLine.objects.get(pk=stmt_line_id)
        expense_acc = ChartOfAccounts.objects.get(pk=expense_account_id)
        bank_acc = batch.bank_account

        with transaction.atomic():
            # إجبار قيمة المبلغ لتتطابق 100% مع مبلغ سطر كشف البنك المرفوع لمنع التعديل اليدوي
            amt = stmt_line.debit if stmt_line.debit > 0 else stmt_line.credit
            is_inflow = stmt_line.debit > 0

            # إعداد شرائح القيد المتوازن
            lines_data = []
            if is_inflow:
                # إيداع: حساب البنك مدين، حساب الإيراد/العمولة دائن
                lines_data = [
                    {'account': bank_acc, 'debit': amt, 'credit': Decimal('0.00'), 'description': description},
                    {'account': expense_acc, 'debit': Decimal('0.00'), 'credit': amt, 'description': description, 'cost_center_id': cost_center_id}
                ]
            else:
                # سحب/مصروف: حساب المصروف مدين، حساب البنك دائن
                lines_data = [
                    {'account': expense_acc, 'debit': amt, 'credit': Decimal('0.00'), 'description': description, 'cost_center_id': cost_center_id},
                    {'account': bank_acc, 'debit': Decimal('0.00'), 'credit': amt, 'description': description}
                ]

            entry = LedgerCoreService.create_draft_entry(
                date=stmt_line.transaction_date,
                description=f"{_('تسوية بنكية فورية - ')}{description}",
                reference=stmt_line.reference_number or f"ADJ-{stmt_line.id}",
                entry_type='ADJUSTMENT',
                created_by=user,
                lines_data=lines_data
            )
            LedgerCoreService.post_entry(entry.id, user)

            # العثور على شريحة قيد البنك في القيد المولد لربطها بالتخصيص
            bank_jl = entry.lines.get(account=bank_acc)
            alloc = cls.create_allocation(stmt_line.id, bank_jl.id, allocated_amount=amt, user=user)
            return alloc

    @classmethod
    def calculate_reconciliation_summary(cls, batch_id: int) -> Dict[str, Any]:
        """احتساب معادلة التسوية البنكية الرسمية المعيارية (IAS 7 Cash Control Equation)"""
        batch = BankStatementBatch.objects.select_related('bank_account').get(pk=batch_id)
        bank_account = batch.bank_account

        # 1. رصيد كشف البنك النهائي المرفوع
        ending_bank_balance = batch.closing_balance

        # 2. جلب الحركات المعلقة في الدفتر العام للحساب البنكي
        uncleared_lines = BankCandidateEngine.get_candidates(bank_account, BankStatementLine(transaction_date=batch.statement_date, debit=Decimal('1.00')), limit=500, date_window_days=90)
        
        # الإيداعات تحت التحصيل (Deposits in Transit)
        deposits_in_transit = sum(l.debit for l in uncleared_lines if l.debit > 0)
        
        # الشيكات والحركات المعلقة المسحوبة (Outstanding Checks)
        outstanding_checks = sum(l.credit for l in uncleared_lines if l.credit > 0)

        # الرصيد البنكي المعدل (Adjusted Bank Balance)
        adjusted_bank_balance = ending_bank_balance + deposits_in_transit - outstanding_checks

        # 3. رصيد الحساب البنكي بالدفتر العام في تاريخ الكشف
        gl_lines = JournalEntryLine.objects.filter(
            account=bank_account,
            journal_entry__status='posted',
            journal_entry__date__lte=batch.statement_date
        )
        total_gl_debit = gl_lines.aggregate(s=models.Sum('debit'))['s'] or Decimal('0.00')
        total_gl_credit = gl_lines.aggregate(s=models.Sum('credit'))['s'] or Decimal('0.00')
        gl_balance = total_gl_debit - total_gl_credit

        # الفارق بين الرصيد المعدل ورصيد الدفتر العام
        difference = adjusted_bank_balance - gl_balance

        # 4. مؤشرات الإنجاز والتشغيل الفورية
        total_bank_lines_count = batch.lines.count()
        matched_bank_lines_count = batch.lines.filter(is_matched=True).count()
        pending_bank_lines_count = batch.lines.filter(is_matched=False).count()
        
        pending_bank_lines_debit = sum(l.debit for l in batch.lines.filter(is_matched=False))
        pending_bank_lines_credit = sum(l.credit for l in batch.lines.filter(is_matched=False))
        pending_bank_lines_amount = pending_bank_lines_debit + pending_bank_lines_credit

        progress_percentage = (
            round((matched_bank_lines_count / total_bank_lines_count) * 100)
            if total_bank_lines_count > 0 else 100
        )

        pending_gl_lines_count = len(uncleared_lines)
        pending_gl_lines_amount = deposits_in_transit + outstanding_checks

        return {
            "batch_id": batch.id,
            "bank_account_name": bank_account.name,
            "statement_date": batch.statement_date,
            "ending_bank_balance": ending_bank_balance,
            "deposits_in_transit": deposits_in_transit,
            "outstanding_checks": outstanding_checks,
            "adjusted_bank_balance": adjusted_bank_balance,
            "gl_balance": gl_balance,
            "difference": difference,
            "is_balanced": abs(difference) <= Decimal('0.05'),
            # Operational Gauges & Progress Indicators
            "total_bank_lines_count": total_bank_lines_count,
            "matched_bank_lines_count": matched_bank_lines_count,
            "pending_bank_lines_count": pending_bank_lines_count,
            "pending_bank_lines_amount": pending_bank_lines_amount,
            "progress_percentage": progress_percentage,
            "pending_gl_lines_count": pending_gl_lines_count,
            "pending_gl_lines_amount": pending_gl_lines_amount,
        }
