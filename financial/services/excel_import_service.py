import logging
from decimal import Decimal
from typing import Dict, Any, List, Tuple
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine, OpeningBalanceImportBatch
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency

logger = logging.getLogger("financial.excel_import_service")


class ExcelImportService:
    """
    خدمة استيراد شيتات الأرصدة الافتتاحية مجمعة (4-Step Pipeline: Parse -> Validate -> Preview -> Commit)
    """

    @classmethod
    def parse(cls, file_obj, template_version: str = 'v1.0') -> List[Dict[str, Any]]:
        """
        1. قراءة واستخراج البيانات من ملف Excel أو CSV
        """
        rows = []
        filename = getattr(file_obj, 'name', 'import.csv').lower()

        if filename.endswith('.csv'):
            import csv
            import io
            content = file_obj.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            for r in reader:
                rows.append(r)
        else:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_obj, data_only=True)
                ws = wb.active
                headers = [str(cell.value or '').strip() for cell in ws[1]]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not any(row):
                        continue
                    row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
                    rows.append(row_dict)
            except Exception as e:
                logger.error(f"Error parsing Excel file: {e}")
                raise ValidationError(_("فشل قراءة ملف Excel: {}").format(str(e)))

        return rows

    @classmethod
    def validate_rows(cls, raw_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        2. فحص والتحقق من صحة كود الحساب والمبالغ
        """
        valid_rows = []
        invalid_rows = []

        all_accounts = {a.code: a for a in ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)}

        for idx, row in enumerate(raw_rows, start=2):
            acc_code = str(row.get('account_code') or row.get('كود الحساب') or '').strip()
            debit_val = Decimal(str(row.get('debit') or row.get('مدين') or '0.00'))
            credit_val = Decimal(str(row.get('credit') or row.get('دائن') or '0.00'))
            line_type = str(row.get('line_type') or row.get('نوع السطر') or 'GL').strip().upper()

            account = all_accounts.get(acc_code)
            errors = []

            if not account:
                errors.append(_("كود الحساب ({}) غير موجود أو غير نشط").format(acc_code))
            if debit_val < 0 or credit_val < 0:
                errors.append(_("المبالغ لا يمكن أن تكون بالسالب"))

            if errors:
                invalid_rows.append({'row_number': idx, 'data': row, 'errors': errors})
            else:
                valid_rows.append({
                    'row_number': idx,
                    'account': account,
                    'line_type': line_type,
                    'debit': debit_val,
                    'credit': credit_val
                })

        return valid_rows, invalid_rows

    @classmethod
    def commit(cls, batch: OpeningBalanceBatch, valid_rows: List[Dict[str, Any]], user, filename: str = 'import.xlsx', template_version: str = 'v1.0') -> OpeningBalanceImportBatch:
        """
        4. حفظ وحقن الأسطر الصحيحة بالدفعة المسودة وتوثيق سجل الاستيراد
        """
        line_objects = []
        for v in valid_rows:
            line_objects.append(OpeningBalanceLine(
                batch=batch,
                account=v['account'],
                line_type=v.get('line_type', 'GL'),
                debit=v['debit'],
                credit=v['credit']
            ))

        OpeningBalanceLine.objects.bulk_create(line_objects)

        import_record = OpeningBalanceImportBatch.objects.create(
            file_name=filename,
            template_version=template_version,
            uploaded_by=user,
            total_rows=len(valid_rows),
            valid_rows=len(valid_rows),
            invalid_rows=0
        )
        return import_record
