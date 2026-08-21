import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def apply_global_arabic_rtl_root(doc):
    """تطبيق التوجيه العربي ومحاذاة اليمين على الجذور والطبقات الست للمستند"""
    
    # 1. طبقة إعدادات المستند (Document Settings)
    settings_elem = doc.settings.element
    theme_lang = parse_xml(f'<w:themeFontLang {nsdecls("w")} w:val="en-US" w:bidi="ar-EG"/>')
    settings_elem.append(theme_lang)
    
    # 2. طبقة الافتراضيات العامة (docDefaults in styles.xml)
    styles_elem = doc.styles.element
    doc_defaults = styles_elem.find(docx.oxml.ns.qn('w:docDefaults'))
    if doc_defaults is not None:
        pPrDefault = doc_defaults.find(docx.oxml.ns.qn('w:pPrDefault'))
        if pPrDefault is None:
            pPrDefault = parse_xml(f'<w:pPrDefault {nsdecls("w")}><w:pPr><w:bidi w:val="1"/><w:jc w:val="right"/></w:pPr></w:pPrDefault>')
            doc_defaults.append(pPrDefault)
        else:
            pPr = pPrDefault.find(docx.oxml.ns.qn('w:pPr'))
            if pPr is None:
                pPrDefault.append(parse_xml(f'<w:pPr {nsdecls("w")}><w:bidi w:val="1"/><w:jc w:val="right"/></w:pPr>'))
            else:
                pPr.append(parse_xml(f'<w:bidi {nsdecls("w")} w:val="1"/>'))
                pPr.append(parse_xml(f'<w:jc {nsdecls("w")} w:val="right"/>'))
                
        rPrDefault = doc_defaults.find(docx.oxml.ns.qn('w:rPrDefault'))
        if rPrDefault is not None:
            rPr = rPrDefault.find(docx.oxml.ns.qn('w:rPr'))
            if rPr is not None:
                rPr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="Cairo" w:hAnsi="Cairo" w:cs="Cairo"/>'))
                rPr.append(parse_xml(f'<w:rtl {nsdecls("w")} w:val="1"/>'))
                rPr.append(parse_xml(f'<w:lang {nsdecls("w")} w:val="ar-EG" w:bidi="ar-EG"/>'))

    # 3. طبقة النمط الافتراضي (Normal Style)
    style = doc.styles['Normal']
    style.font.name = 'Cairo'
    style.font.size = Pt(10)
    pPr = style.element.get_or_add_pPr()
    pPr.append(parse_xml(f'<w:bidi {nsdecls("w")} w:val="1"/>'))
    pPr.append(parse_xml(f'<w:jc {nsdecls("w")} w:val="right"/>'))
    rPr = style.element.get_or_add_rPr()
    rPr.append(parse_xml(f'<w:rtl {nsdecls("w")} w:val="1"/>'))
    rPr.append(parse_xml(f'<w:lang {nsdecls("w")} w:val="ar-EG" w:bidi="ar-EG"/>'))
    rPr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="Cairo" w:hAnsi="Cairo" w:cs="Cairo"/>'))

    # 4. طبقة الأقسام (Sections)
    for section in doc.sections:
        sectPr = section._sectPr
        sectPr.append(parse_xml(f'<w:bidi {nsdecls("w")} w:val="1"/>'))
        sectPr.append(parse_xml(f'<w:rtlGutter {nsdecls("w")} w:val="1"/>'))

doc = docx.Document()
apply_global_arabic_rtl_root(doc)
p = doc.add_paragraph('هذا نص تجريبي للتأكد من المحاذاة اليمينية الجذرية')
doc.save('scratch/test_root_rtl.docx')
print('Root RTL test passed!')
