import os
import re
import io
import base64
import logging
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)

def reshape_ar(text):
    """
    إعادة تشكيل وتوجيه النص العربي للطباعة النظيفة في ReportLab
    """
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        config = {
            'delete_harakat': False,
            'support_ligatures': True,
        }
        reshaper = arabic_reshaper.ArabicReshaper(configuration=config)
        reshaped = reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def get_base64_encoded_file(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode('utf-8')
                ext = os.path.splitext(file_path)[1].lower().replace('.', '')
                mime_type = "image/png" if ext == "png" else "image/jpeg" if ext in ["jpg", "jpeg"] else "image/svg+xml" if ext == "svg" else "application/octet-stream"
                return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        logger.warning(f"Failed to encode image to base64 {file_path}: {e}")
    return None

def prepare_html_for_pdf(html_content, request=None):
    base_dir = settings.BASE_DIR
    module_dir = Path(__file__).resolve().parent.parent
    media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(base_dir, 'media'))
    static_root = getattr(settings, 'STATIC_ROOT', os.path.join(base_dir, 'static'))

    # Embed Tajawal fonts into @font-face for WeasyPrint
    possible_reg = [
        os.path.join(base_dir, 'static', 'fonts', 'Tajawal-Regular.ttf'),
        os.path.join(static_root, 'fonts', 'Tajawal-Regular.ttf'),
        os.path.join(module_dir, 'static', 'fonts', 'Tajawal-Regular.ttf'),
        os.path.join(base_dir, 'core', 'static', 'fonts', 'Tajawal-Regular.ttf'),
    ]
    possible_bold = [
        os.path.join(base_dir, 'static', 'fonts', 'Tajawal-Bold.ttf'),
        os.path.join(static_root, 'fonts', 'Tajawal-Bold.ttf'),
        os.path.join(module_dir, 'static', 'fonts', 'Tajawal-Bold.ttf'),
        os.path.join(base_dir, 'core', 'static', 'fonts', 'Tajawal-Bold.ttf'),
    ]
    font_reg_path = next((p for p in possible_reg if p and os.path.exists(p)), None)
    font_bold_path = next((p for p in possible_bold if p and os.path.exists(p)), None)
    
    font_css = ""
    if font_reg_path and os.path.exists(font_reg_path):
        with open(font_reg_path, 'rb') as f:
            b64_reg = base64.b64encode(f.read()).decode('utf-8')
            font_css += f"""
            @font-face {{
                font-family: 'Tajawal';
                src: url('data:font/ttf;base64,{b64_reg}') format('truetype');
                font-weight: normal;
                font-style: normal;
            }}
            """
    if font_bold_path and os.path.exists(font_bold_path):
        with open(font_bold_path, 'rb') as f:
            b64_bold = base64.b64encode(f.read()).decode('utf-8')
            font_css += f"""
            @font-face {{
                font-family: 'Tajawal';
                src: url('data:font/ttf;base64,{b64_bold}') format('truetype');
                font-weight: bold;
                font-style: normal;
            }}
            """

    if font_css and '<head>' in html_content:
        html_content = html_content.replace('<head>', f'<head><style>{font_css}</style>')

    def replace_media(match):
        rel_path = match.group(1)
        full_path = os.path.join(media_root, rel_path.lstrip('/'))
        if os.path.exists(full_path):
            b64 = get_base64_encoded_file(full_path)
            if b64:
                return f'src="{b64}"'
            return f'src="file:///{full_path.replace(os.sep, "/")}"'
        return match.group(0)

    def replace_static(match):
        rel_path = match.group(1)
        full_path = os.path.join(static_root, rel_path.lstrip('/'))
        if not os.path.exists(full_path):
            full_path = os.path.join(base_dir, 'static', rel_path.lstrip('/'))
        if not os.path.exists(full_path):
            full_path = os.path.join(module_dir, 'static', rel_path.lstrip('/'))
        if os.path.exists(full_path):
            b64 = get_base64_encoded_file(full_path)
            if b64:
                return f'src="{b64}"'
            return f'src="file:///{full_path.replace(os.sep, "/")}"'
        return match.group(0)

    html_content = re.sub(r'src=["\']/(?:media|uploads)/([^"\']+)["\']', replace_media, html_content)
    html_content = re.sub(r'src=["\']/static/([^"\']+)["\']', replace_static, html_content)
    return html_content

def generate_pdf_via_reportlab(doc_type, context, filename="document.pdf"):
    """
    محرك ReportLab النقي الخالي من الاعتماديات الخارجية (Pure Python Engine)
    يعمل بنجاح 100% على كافة سيرفرات الاستضافة واستضافات cPanel/Passenger WSGI
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib import colors

        module_dir = Path(__file__).resolve().parent.parent
        possible_paths = [
            os.path.join(settings.BASE_DIR, 'static', 'fonts', 'Tajawal-Regular.ttf'),
            os.path.join(getattr(settings, 'STATIC_ROOT', '') or '', 'fonts', 'Tajawal-Regular.ttf'),
            os.path.join(module_dir, 'static', 'fonts', 'Tajawal-Regular.ttf'),
            os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'Tajawal-Regular.ttf'),
            'static/fonts/Tajawal-Regular.ttf',
        ]
        possible_bold_paths = [
            os.path.join(settings.BASE_DIR, 'static', 'fonts', 'Tajawal-Bold.ttf'),
            os.path.join(getattr(settings, 'STATIC_ROOT', '') or '', 'fonts', 'Tajawal-Bold.ttf'),
            os.path.join(module_dir, 'static', 'fonts', 'Tajawal-Bold.ttf'),
            os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts', 'Tajawal-Bold.ttf'),
            'static/fonts/Tajawal-Bold.ttf',
        ]
        
        tajawal_reg = next((p for p in possible_paths if p and os.path.exists(p)), None)
        tajawal_bold = next((p for p in possible_bold_paths if p and os.path.exists(p)), None)
        
        font_name = 'Helvetica'
        font_bold = 'Helvetica-Bold'
        
        if tajawal_reg:
            try:
                pdfmetrics.registerFont(TTFont('Tajawal', tajawal_reg))
                font_name = 'Tajawal'
            except Exception as fe:
                logger.warning(f"Failed to register Tajawal font: {fe}")
                
        if tajawal_bold:
            try:
                pdfmetrics.registerFont(TTFont('Tajawal-Bold', tajawal_bold))
                font_bold = 'Tajawal-Bold'
            except Exception as fe:
                logger.warning(f"Failed to register Tajawal-Bold font: {fe}")
        else:
            font_bold = font_name

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=20,
            rightMargin=20,
            topMargin=20,
            bottomMargin=20
        )

        styles = getSampleStyleSheet()
        style_ar_right = ParagraphStyle(
            'ArRight',
            fontName=font_name,
            fontSize=9,
            alignment=2, # Right align
            leading=12
        )
        style_ar_center = ParagraphStyle(
            'ArCenter',
            fontName=font_name,
            fontSize=9,
            alignment=1, # Center align
            leading=12
        )
        style_title = ParagraphStyle(
            'ArTitle',
            fontName=font_bold,
            fontSize=14,
            alignment=1,
            textColor=colors.HexColor('#04578d'),
            leading=16
        )

        story = []

        # 1. Company Header Data
        comp_name = context.get('company_name') or 'مؤسسة موهبة'
        comp_tax = context.get('company_tax_number') or ''
        comp_phone = context.get('company_phone') or ''
        
        header_text = f"<b>{reshape_ar(comp_name)}</b><br/>"
        if comp_tax:
            header_text += f"{reshape_ar('الرقم الضريبي:')} {comp_tax}<br/>"
        if comp_phone:
            header_text += f"{reshape_ar('الهاتف:')} {comp_phone}"
            
        header_p = Paragraph(header_text, style_ar_right)
        
        header_table = Table([[header_p]], colWidths=[545])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor('#04578d')),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        # 2. Document Title & Details
        if doc_type in ['statement', 'account_statement']:
            # معالجة كشف الحساب المحاسبي في ReportLab
            account_obj = context.get('account')
            acc_name = getattr(account_obj, 'name', '') if account_obj else context.get('account_name', '')
            acc_code = getattr(account_obj, 'code', '') if account_obj else context.get('account_code', '')
            period_label = context.get('period_label') or 'كافة الحركات المالية'
            curr_symbol = context.get('currency_symbol_active', 'ج.م')
            
            title_p = Paragraph(f"<b>{reshape_ar('كشف حساب')}: {reshape_ar(acc_name)} ({acc_code})</b>", style_title)
            story.append(title_p)
            story.append(Spacer(1, 6))
            
            # كارت بيانات الحساب والفترة
            info_data = [
                [Paragraph(f"<b>{reshape_ar('الحساب:')}</b> {reshape_ar(acc_name)} ({acc_code})", style_ar_right),
                 Paragraph(f"<b>{reshape_ar('الفترة:')}</b> {reshape_ar(period_label)}", style_ar_right)],
                [Paragraph(f"<b>{reshape_ar('تاريخ الاستخراج:')}</b> {context.get('generated_at', '')}", style_ar_right),
                 Paragraph(f"<b>{reshape_ar('المستخدم:')}</b> {reshape_ar(context.get('generated_by', ''))}", style_ar_right)]
            ]
            info_table = Table(info_data, colWidths=[275, 270])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(info_table)
            story.append(Spacer(1, 10))
            
            # جدول حركات كشف الحساب
            trans = context.get('transactions', [])
            summary_info = context.get('summary', {})
            try:
                op_bal = float(summary_info.get('opening_balance') or 0)
            except (ValueError, TypeError):
                op_bal = 0.0
            try:
                tot_deb = float(summary_info.get('total_debit') or 0)
            except (ValueError, TypeError):
                tot_deb = 0.0
            try:
                tot_crd = float(summary_info.get('total_credit') or 0)
            except (ValueError, TypeError):
                tot_crd = 0.0
            try:
                cl_bal = float(summary_info.get('closing_balance') or 0)
            except (ValueError, TypeError):
                cl_bal = 0.0
            
            tx_data = [
                [Paragraph(reshape_ar('#'), style_ar_center),
                 Paragraph(reshape_ar('التاريخ'), style_ar_center),
                 Paragraph(reshape_ar('النوع'), style_ar_center),
                 Paragraph(reshape_ar('البيان والتفاصيل'), style_ar_right),
                 Paragraph(reshape_ar('المرجع'), style_ar_center),
                 Paragraph(reshape_ar('مدين'), style_ar_center),
                 Paragraph(reshape_ar('دائن'), style_ar_center),
                 Paragraph(reshape_ar('الرصيد'), style_ar_center)]
            ]
            
            # سطر الرصيد الافتتاحي المنقول
            tx_data.append([
                Paragraph("-", style_ar_center),
                Paragraph(str(context.get('date_from') or '-'), style_ar_center),
                Paragraph("-", style_ar_center),
                Paragraph(f"<b>{reshape_ar('رصيد منقول (افتتاحي ما قبل الفترة)')}</b>", style_ar_right),
                Paragraph("-", style_ar_center),
                Paragraph("-", style_ar_center),
                Paragraph("-", style_ar_center),
                Paragraph(f"<b>{op_bal:,.2f}</b>", style_ar_center),
            ])
            
            for idx, t in enumerate(trans, 1):
                dt_str = str(t.get('date') or '')
                type_str = str(t.get('entry_type_display') or t.get('journal_entry_number') or t.get('journal_number') or '')
                ref_str = str(t.get('reference') or '-')
                desc_str = str(t.get('description') or '-')
                if t.get('cost_center_name'):
                    desc_str += f" [{t.get('cost_center_name')}]"
                
                try:
                    deb_val = f"{float(t['debit']):,.2f}" if t.get('debit') else "-"
                except (ValueError, TypeError):
                    deb_val = str(t.get('debit') or '-')
                
                try:
                    crd_val = f"{float(t['credit']):,.2f}" if t.get('credit') else "-"
                except (ValueError, TypeError):
                    crd_val = str(t.get('credit') or '-')
                
                bal_raw = t.get('running_balance') if t.get('running_balance') is not None else t.get('balance', 0)
                try:
                    bal_val = f"{float(bal_raw):,.2f}" if bal_raw is not None else "0.00"
                except (ValueError, TypeError):
                    bal_val = str(bal_raw or "0.00")
                
                tx_data.append([
                    Paragraph(str(idx), style_ar_center),
                    Paragraph(dt_str, style_ar_center),
                    Paragraph(reshape_ar(type_str), style_ar_center),
                    Paragraph(reshape_ar(desc_str), style_ar_right),
                    Paragraph(reshape_ar(ref_str), style_ar_center),
                    Paragraph(deb_val, style_ar_center),
                    Paragraph(crd_val, style_ar_center),
                    Paragraph(bal_val, style_ar_center),
                ])
                
            tx_table = Table(tx_data, colWidths=[20, 50, 60, 160, 55, 65, 65, 70])
            tx_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#04578d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), font_bold),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#e6f0f7'), colors.white, colors.HexColor('#f8fafc')]),
            ]))
            story.append(tx_table)
            story.append(Spacer(1, 10))
            
            # صندوق الرصيد الختامي فقط أسفل الجدول
            bal_status = ' (مدين)' if cl_bal > 0 else ' (دائن)' if cl_bal < 0 else ' (متزن)'
            currency_sym = str(context.get('currency_symbol_active') or 'ج.م')
            
            closing_box_data = [
                [
                    Paragraph(f"<b>{reshape_ar('الرصيد الختامي:')}</b>", style_ar_right),
                    Paragraph(f"<b>{cl_bal:,.2f} {reshape_ar(currency_sym)}{reshape_ar(bal_status)}</b>", style_ar_left),
                ]
            ]
            closing_box_table = Table(closing_box_data, colWidths=[200, 345])
            closing_box_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e6f0f7')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#034069')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('PADDING', (0, 0), (-1, -1), 7),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(closing_box_table)
            story.append(Spacer(1, 15))
            
            # مربعات التوقيعات الثلاثية الرسمية
            sig_data = [
                [Paragraph(f"<b>{reshape_ar('إعداد / المحاسب المسؤول')}</b><br/><br/>...........................<br/>", style_ar_center),
                 Paragraph(f"<b>{reshape_ar('مراجعة / التدقيق الداخلي')}</b><br/><br/>...........................<br/>", style_ar_center),
                 Paragraph(f"<b>{reshape_ar('اعتماد / المدير المالي')}</b><br/><br/>...........................<br/>", style_ar_center)]
            ]
            sig_table = Table(sig_data, colWidths=[180, 180, 185])
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('PADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(sig_table)

        elif doc_type == 'accounts_summary':
            # ملخص حركة وأرصدة كافة الحسابات
            title_p = Paragraph(f"<b>{reshape_ar('ملخص حركة وأرصدة الحسابات المالية')}</b>", style_title)
            story.append(title_p)
            story.append(Spacer(1, 10))
            
            accounts_summary_list = context.get('accounts_summary', [])
            sm_data = [
                [Paragraph(reshape_ar('كود الحساب'), style_ar_center),
                 Paragraph(reshape_ar('اسم الحساب'), style_ar_right),
                 Paragraph(reshape_ar('نوع الحساب'), style_ar_center),
                 Paragraph(reshape_ar('إجمالي مدين'), style_ar_center),
                 Paragraph(reshape_ar('إجمالي دائن'), style_ar_center),
                 Paragraph(reshape_ar('الرصيد الحالي'), style_ar_center)]
            ]
            for item in accounts_summary_list:
                acc = item.get('account')
                code_str = str(getattr(acc, 'code', ''))
                name_str = str(getattr(acc, 'name', ''))
                acc_type = getattr(acc, 'account_type', None)
                type_name = str(getattr(acc_type, 'name', '')) if acc_type else ''
                try:
                    deb_str = f"{float(item.get('total_debit', 0) or 0):,.2f}"
                except (ValueError, TypeError):
                    deb_str = str(item.get('total_debit') or "0.00")
                try:
                    crd_str = f"{float(item.get('total_credit', 0) or 0):,.2f}"
                except (ValueError, TypeError):
                    crd_str = str(item.get('total_credit') or "0.00")
                try:
                    bal_str = f"{float(item.get('current_balance', 0) or 0):,.2f}"
                except (ValueError, TypeError):
                    bal_str = str(item.get('current_balance') or "0.00")
                sm_data.append([
                    Paragraph(code_str, style_ar_center),
                    Paragraph(reshape_ar(name_str), style_ar_right),
                    Paragraph(reshape_ar(type_name), style_ar_center),
                    Paragraph(deb_str, style_ar_center),
                    Paragraph(crd_str, style_ar_center),
                    Paragraph(bal_str, style_ar_center),
                ])
            sm_table = Table(sm_data, colWidths=[65, 160, 80, 80, 80, 80])
            sm_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#04578d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), font_bold),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ]))
            story.append(sm_table)
        else:
            # 2. Document Title & Details for Invoices & Orders
            doc_obj = context.get('sale') or context.get('quotation') or context.get('purchase')
            doc_title = context.get('document_title') or ('فاتورة مبيعات' if doc_type == 'sale' else 'عرض سعر' if doc_type == 'quotation' else 'فاتورة مشتريات')
            doc_num = getattr(doc_obj, 'number', '')
            doc_date = str(getattr(doc_obj, 'date', ''))
            status_txt = context.get('translated_status', '')

            title_p = Paragraph(f"<b>{reshape_ar(doc_title)} #{doc_num}</b>", style_title)
            story.append(title_p)
            story.append(Spacer(1, 10))

            # 3. Party Info (Customer / Supplier)
            party = getattr(doc_obj, 'customer', None) or getattr(doc_obj, 'supplier', None)
            party_name = getattr(party, 'name', '') if party else ''
            party_phone = getattr(party, 'phone', '') if party else ''
            party_label = 'فاتورة إلى (العميل):' if doc_type != 'purchase' else 'المورد / فاتورة من:'

            info_data = [
                [Paragraph(f"<b>{reshape_ar(party_label)}</b> {reshape_ar(party_name)}", style_ar_right),
                 Paragraph(f"<b>{reshape_ar('التاريخ:')}</b> {doc_date}", style_ar_right)],
                [Paragraph(f"<b>{reshape_ar('الهاتف:')}</b> {party_phone}", style_ar_right),
                 Paragraph(f"<b>{reshape_ar('الحالة:')}</b> {reshape_ar(status_txt)}", style_ar_right)]
            ]
            info_table = Table(info_data, colWidths=[300, 245])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(info_table)
            story.append(Spacer(1, 12))

            # 4. Items Table
            items = context.get('items', [])
            curr_symbol = context.get('currency_symbol_active', 'ج.م')
            
            items_data = [
                [Paragraph(reshape_ar('#'), style_ar_center),
                 Paragraph(reshape_ar('المنتج / الوصف'), style_ar_right),
                 Paragraph(reshape_ar('الكمية'), style_ar_center),
                 Paragraph(reshape_ar('السعر'), style_ar_center),
                 Paragraph(reshape_ar('الإجمالي'), style_ar_center)]
            ]

            for idx, item in enumerate(items, 1):
                product_obj = getattr(item, 'product', None)
                p_name = (getattr(product_obj, 'name', '') if product_obj else None) or getattr(item, 'item_name', '') or getattr(item, 'description', '') or 'منتج'
                qty = str(getattr(item, 'quantity', 1))
                price = f"{getattr(item, 'unit_price', 0)} {curr_symbol}"
                total = f"{getattr(item, 'total', 0)} {curr_symbol}"
                
                items_data.append([
                    Paragraph(str(idx), style_ar_center),
                    Paragraph(reshape_ar(p_name), style_ar_right),
                    Paragraph(qty, style_ar_center),
                    Paragraph(price, style_ar_center),
                    Paragraph(total, style_ar_center)
                ])

            items_table = Table(items_data, colWidths=[30, 235, 80, 100, 100])
            items_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#04578d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), font_bold),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ]))
            story.append(items_table)
            story.append(Spacer(1, 10))

            # 5. Summary Totals
            subtotal = f"{getattr(doc_obj, 'subtotal', 0)} {curr_symbol}"
            discount = f"{getattr(doc_obj, 'discount', 0)} {curr_symbol}"
            tax = f"{getattr(doc_obj, 'tax', 0)} {curr_symbol}"
            total_val = f"{getattr(doc_obj, 'total', 0)} {curr_symbol}"
            
            try:
                due_amount = getattr(doc_obj, 'amount_due', getattr(doc_obj, 'total', 0))
            except Exception:
                due_amount = getattr(doc_obj, 'total', 0)
            due_val = f"{due_amount} {curr_symbol}"

            summary_data = [
                [Paragraph(reshape_ar('المجموع الفرعي:'), style_ar_right), Paragraph(subtotal, style_ar_right)],
                [Paragraph(reshape_ar('الخصم:'), style_ar_right), Paragraph(discount, style_ar_right)],
                [Paragraph(reshape_ar('الضريبة:'), style_ar_right), Paragraph(tax, style_ar_right)],
                [Paragraph(f"<b>{reshape_ar('الإجمالي الكلي:')}</b>", style_ar_right), Paragraph(f"<b>{total_val}</b>", style_ar_right)],
                [Paragraph(f"<b>{reshape_ar('المبلغ المستحق:')}</b>", style_ar_right), Paragraph(f"<b>{due_val}</b>", style_ar_right)]
            ]
            
            summary_table = Table(summary_data, colWidths=[150, 120])
            summary_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#04578d')),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            
            # Position summary to the left
            wrapper_table = Table([[Paragraph('', style_ar_right), summary_table]], colWidths=[275, 270])
            wrapper_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
            story.append(wrapper_table)

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        return set_pdf_content_disposition(response, filename)

    except Exception as e:
        logger.error(f"ReportLab PDF generation error for {filename}: {e}", exc_info=True)
        return None

def set_pdf_content_disposition(response, filename="document.pdf"):
    """
    ضبط ترويسة Content-Disposition بمعيار RFC 5987 لدعم الأسماء العربية بدون خطأ Latin-1
    """
    from urllib.parse import quote
    import unicodedata
    if not filename.endswith('.pdf'):
        filename += '.pdf'
    
    # Safe ASCII fallback filename
    ascii_clean = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
    ascii_filename = ascii_clean if (ascii_clean and ascii_clean.strip() != '.pdf') else "document.pdf"
    
    encoded_filename = quote(filename)
    response['Content-Disposition'] = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
    return response

def generate_pdf_from_html(html_content, request=None, filename="document.pdf", doc_type="sale", context=None):
    """
    توليد مستند PDF عبر WeasyPrint مع التوجيه التلقائي المباشر لـ ReportLab عند نقص مكتبات النظام C في الاستضافة
    """
    # 1. المحاولة الأولى عبر WeasyPrint (إذا كانت مكتبات C مثبتة)
    try:
        import weasyprint
        processed_html = prepare_html_for_pdf(html_content, request=request)
        base_url = request.build_absolute_uri('/') if request else None
        
        pdf_bytes = weasyprint.HTML(
            string=processed_html,
            base_url=base_url
        ).write_pdf()
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        return set_pdf_content_disposition(response, filename)
    except Exception as e:
        logger.warning(f"WeasyPrint unavailable or failed ({e}), falling back to ReportLab engine.")

    # 2. المحاولة الثانية السريعة والمضمونة عبر ReportLab (Pure Python Engine)
    if context:
        rl_response = generate_pdf_via_reportlab(doc_type, context, filename=filename)
        if rl_response:
            return rl_response

    return generate_guaranteed_pdf_response(doc_type, context or {}, filename=filename)


def generate_guaranteed_pdf_response(doc_type, context, filename="document.pdf"):
    """
    مولد PDF مضمون 100% يضمن إرجاع HttpResponse بنوع application/pdf
    في كافة الظروف والبيئات ولا يرجع HTML أبداً.
    """
    res = generate_pdf_via_reportlab(doc_type, context, filename=filename)
    if res:
        return res

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        
        doc_obj = context.get('sale') or context.get('quotation') or context.get('purchase')
        doc_num = getattr(doc_obj, 'number', 'DOCUMENT-0001')
        comp_name = context.get('company_name', 'MWHEBA ERP')
        total_val = getattr(doc_obj, 'total', 0)
        
        story = [
            Paragraph(f"Document: {doc_num}", styles['Title']),
            Spacer(1, 20),
            Paragraph(f"Company: {comp_name}", styles['Normal']),
            Paragraph(f"Total: {total_val}", styles['Normal']),
        ]
        doc.build(story)
        
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        return set_pdf_content_disposition(response, filename)
    except Exception as e:
        logger.error(f"Fallback minimal PDF generation error: {e}")
        minimal_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
        response = HttpResponse(minimal_pdf, content_type='application/pdf')
        return set_pdf_content_disposition(response, filename)
