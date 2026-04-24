"""
خدمة توليد رسائل الخطأ للتحقق من المعاملات المالية

هذه الخدمة توفر رسائل خطأ واضحة ومفصلة بالعربية عند فشل التحقق من المعاملات المالية.
جميع الرسائل تتضمن تفاصيل الكيان واقتراحات لحل المشكلة.
"""
from datetime import date
from typing import List, Optional


class ErrorMessageGenerator:
    """
    مولد رسائل الخطأ الواضحة بالعربية
    
    يوفر دوال لتوليد رسائل خطأ مفصلة لكل نوع من أنواع فشل التحقق،
    مع تضمين اسم الكيان ونوعه واقتراحات لحل المشكلة.
    """
    
    # خريطة أنواع الكيانات إلى أسمائها بالعربية
    ENTITY_TYPE_NAMES = {
        'customer': 'العميل',
        'supplier': 'المورد',
        'employee': 'الموظف',
        'activity': 'النشاط',
        'transportation_route': 'خط النقل',
        'product': 'المنتج',
        'sale': 'المبيعات',
        'purchase': 'المشتريات',
        'other': 'الكيان',
    }
    
    @staticmethod
    def _get_entity_type_name(entity_type: str) -> str:
        """
        الحصول على اسم نوع الكيان بالعربية
        
        Args:
            entity_type: نوع الكيان بالإنجليزية
            
        Returns:
            str: اسم نوع الكيان بالعربية
        """
        return ErrorMessageGenerator.ENTITY_TYPE_NAMES.get(
            entity_type.lower(),
            'الكيان'
        )
    
    @staticmethod
    def chart_of_accounts_missing(entity_name: str, entity_type: str) -> str:
        """
        رسالة عدم وجود حساب محاسبي
        
        Args:
            entity_name: اسم الكيان
            entity_type: نوع الكيان
            
        Returns:
            str: رسالة الخطأ بالعربية
            
        Example:
            >>> ErrorMessageGenerator.chart_of_accounts_missing("أحمد محمد", "customer")
            'لا يوجد حساب محاسبي مرتبط بـ العميل: أحمد محمد.\\n\\nالإجراء المطلوب: يرجى ربط حساب محاسبي بهذا العميل من خلال إعدادات الحسابات المحاسبية.'
        """
        entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
        
        message = f"لا يوجد حساب محاسبي مرتبط بـ {entity_type_ar}: {entity_name}."
        suggestion = f"\n\nالإجراء المطلوب: يرجى ربط حساب محاسبي بهذا {entity_type_ar} من خلال إعدادات الحسابات المحاسبية."
        
        return message + suggestion
    
    @staticmethod
    def chart_of_accounts_inactive(account_code: str, account_name: str, entity_name: str = None, entity_type: str = None) -> str:
        """
        رسالة حساب محاسبي غير مفعّل
        
        Args:
            account_code: كود الحساب المحاسبي
            account_name: اسم الحساب المحاسبي
            entity_name: اسم الكيان (اختياري)
            entity_type: نوع الكيان (اختياري)
            
        Returns:
            str: رسالة الخطأ بالعربية
            
        Example:
            >>> ErrorMessageGenerator.chart_of_accounts_inactive("1010", "حساب العملاء", "أحمد محمد", "customer")
            'الحساب المحاسبي (1010 - حساب العملاء) المرتبط بـ العميل: أحمد محمد غير مفعّل.\\n\\nالإجراء المطلوب: يرجى تفعيل الحساب المحاسبي من خلال إعدادات دليل الحسابات.'
        """
        message = f"الحساب المحاسبي ({account_code} - {account_name})"
        
        if entity_name and entity_type:
            entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
            message += f" المرتبط بـ {entity_type_ar}: {entity_name}"
        
        message += " غير مفعّل."
        suggestion = "\n\nالإجراء المطلوب: يرجى تفعيل الحساب المحاسبي من خلال إعدادات دليل الحسابات."
        
        return message + suggestion
    
    @staticmethod
    def chart_of_accounts_not_leaf(account_code: str, account_name: str, entity_name: str = None, entity_type: str = None) -> str:
        """
        رسالة حساب محاسبي ليس نهائياً
        
        Args:
            account_code: كود الحساب المحاسبي
            account_name: اسم الحساب المحاسبي
            entity_name: اسم الكيان (اختياري)
            entity_type: نوع الكيان (اختياري)
            
        Returns:
            str: رسالة الخطأ بالعربية
            
        Example:
            >>> ErrorMessageGenerator.chart_of_accounts_not_leaf("1000", "الأصول المتداولة", "أحمد محمد", "customer")
            'الحساب المحاسبي (1000 - الأصول المتداولة) المرتبط بـ العميل: أحمد محمد ليس حساباً نهائياً (حساب رئيسي).\\n\\nالإجراء المطلوب: يجب استخدام حساب نهائي (فرعي) وليس حساب رئيسي. يرجى تغيير الحساب المحاسبي إلى حساب فرعي.'
        """
        message = f"الحساب المحاسبي ({account_code} - {account_name})"
        
        if entity_name and entity_type:
            entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
            message += f" المرتبط بـ {entity_type_ar}: {entity_name}"
        
        message += " ليس حساباً نهائياً (حساب رئيسي)."
        suggestion = "\n\nالإجراء المطلوب: يجب استخدام حساب نهائي (فرعي) وليس حساب رئيسي. يرجى تغيير الحساب المحاسبي إلى حساب فرعي."
        
        return message + suggestion
    
    @staticmethod
    def accounting_period_missing(transaction_date, entity_name: str = None, entity_type: str = None) -> str:
        """
        رسالة عدم وجود فترة محاسبية
        
        Args:
            transaction_date: تاريخ المعاملة (date object أو string)
            entity_name: اسم الكيان (اختياري)
            entity_type: نوع الكيان (اختياري)
            
        Returns:
            str: رسالة الخطأ بالعربية
            
        Example:
            >>> from datetime import date
            >>> ErrorMessageGenerator.accounting_period_missing(date(2024, 6, 15), "أحمد محمد", "customer")
            'لا توجد فترة محاسبية للتاريخ: 2024-06-15 للمعاملة المتعلقة بـ العميل: أحمد محمد.\\n\\nالإجراء المطلوب: يرجى إنشاء فترة محاسبية تشمل هذا التاريخ من خلال إعدادات الفترات المحاسبية.'
        """
        # تحويل التاريخ إلى string إذا كان date object
        if isinstance(transaction_date, date):
            date_str = transaction_date.strftime('%Y-%m-%d')
        else:
            date_str = str(transaction_date)
        
        message = f"لا توجد فترة محاسبية للتاريخ: {date_str}"
        
        if entity_name and entity_type:
            entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
            message += f" للمعاملة المتعلقة بـ {entity_type_ar}: {entity_name}"
        
        message += "."
        suggestion = "\n\nالإجراء المطلوب: يرجى إنشاء فترة محاسبية تشمل هذا التاريخ من خلال إعدادات الفترات المحاسبية."
        
        return message + suggestion
    
    @staticmethod
    def accounting_period_closed(period_name: str, transaction_date=None, entity_name: str = None, entity_type: str = None) -> str:
        """
        رسالة فترة محاسبية مغلقة
        
        Args:
            period_name: اسم الفترة المحاسبية
            transaction_date: تاريخ المعاملة (اختياري)
            entity_name: اسم الكيان (اختياري)
            entity_type: نوع الكيان (اختياري)
            
        Returns:
            str: رسالة الخطأ بالعربية
            
        Example:
            >>> ErrorMessageGenerator.accounting_period_closed("يناير 2024", None, "أحمد محمد", "customer")
            'الفترة المحاسبية (يناير 2024) مغلقة ولا يمكن إضافة معاملات جديدة فيها للمعاملة المتعلقة بـ العميل: أحمد محمد.\\n\\nالإجراء المطلوب: يرجى فتح الفترة المحاسبية أو استخدام تاريخ ضمن فترة مفتوحة.'
        """
        message = f"الفترة المحاسبية ({period_name}) مغلقة ولا يمكن إضافة معاملات جديدة فيها"
        
        if entity_name and entity_type:
            entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
            message += f" للمعاملة المتعلقة بـ {entity_type_ar}: {entity_name}"
        
        message += "."
        suggestion = "\n\nالإجراء المطلوب: يرجى فتح الفترة المحاسبية أو استخدام تاريخ ضمن فترة مفتوحة."
        
        return message + suggestion
    
    @staticmethod
    def generate_comprehensive_message(
        errors: List[str],
        entity_name: str,
        entity_type: str,
        transaction_date=None,
        transaction_type: str = None
    ) -> str:
        """
        توليد رسالة شاملة مع اقتراحات
        
        يجمع عدة أخطاء في رسالة واحدة مع اقتراحات شاملة لحل جميع المشاكل.
        
        Args:
            errors: قائمة رسائل الخطأ
            entity_name: اسم الكيان
            entity_type: نوع الكيان
            transaction_date: تاريخ المعاملة (اختياري)
            transaction_type: نوع المعاملة (اختياري)
            
        Returns:
            str: رسالة خطأ شاملة بالعربية
            
        Example:
            >>> errors = ["لا يوجد حساب محاسبي", "لا توجد فترة محاسبية"]
            >>> ErrorMessageGenerator.generate_comprehensive_message(errors, "أحمد محمد", "customer")
            'فشل التحقق من المعاملة المالية للعميل: أحمد محمد\\n\\nالأخطاء المكتشفة:\\n1. لا يوجد حساب محاسبي\\n2. لا توجد فترة محاسبية\\n\\nالإجراءات المطلوبة:\\n• تأكد من ربط حساب محاسبي صحيح ومفعّل بالكيان\\n• تأكد من وجود فترة محاسبية مفتوحة للتاريخ المحدد\\n• راجع إعدادات النظام المالي'
        """
        entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
        
        # بناء رأس الرسالة
        header = f"فشل التحقق من المعاملة المالية ل{entity_type_ar}: {entity_name}"
        
        # إضافة معلومات إضافية إذا كانت متوفرة
        if transaction_date:
            if isinstance(transaction_date, date):
                date_str = transaction_date.strftime('%Y-%m-%d')
            else:
                date_str = str(transaction_date)
            header += f"\nتاريخ المعاملة: {date_str}"
        
        if transaction_type:
            header += f"\nنوع المعاملة: {transaction_type}"
        
        # بناء قائمة الأخطاء
        errors_section = "\n\nالأخطاء المكتشفة:"
        for i, error in enumerate(errors, 1):
            # إزالة الاقتراحات من الأخطاء الفردية لتجنب التكرار
            error_text = error.split('\n\n')[0] if '\n\n' in error else error
            errors_section += f"\n{i}. {error_text}"
        
        # بناء قائمة الاقتراحات
        suggestions = ErrorMessageGenerator._generate_suggestions(errors, entity_type)
        suggestions_section = "\n\nالإجراءات المطلوبة:"
        for suggestion in suggestions:
            suggestions_section += f"\n• {suggestion}"
        
        return header + errors_section + suggestions_section
    
    @staticmethod
    def _generate_suggestions(errors: List[str], entity_type: str) -> List[str]:
        """
        توليد اقتراحات بناءً على الأخطاء
        
        Args:
            errors: قائمة رسائل الخطأ
            entity_type: نوع الكيان
            
        Returns:
            List[str]: قائمة الاقتراحات
        """
        suggestions = []
        entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
        
        # تحليل الأخطاء وإضافة الاقتراحات المناسبة
        errors_text = ' '.join(errors).lower()
        
        if 'لا يوجد حساب محاسبي' in errors_text or 'missing' in errors_text:
            suggestions.append(f"تأكد من ربط حساب محاسبي صحيح ومفعّل ب{entity_type_ar}")
        
        if 'غير مفعّل' in errors_text or 'inactive' in errors_text:
            suggestions.append("تأكد من تفعيل الحساب المحاسبي من خلال إعدادات دليل الحسابات")
        
        if 'ليس حساباً نهائياً' in errors_text or 'not_leaf' in errors_text or 'not leaf' in errors_text:
            suggestions.append("استخدم حساب محاسبي نهائي (فرعي) وليس حساب رئيسي")
        
        if 'لا توجد فترة محاسبية' in errors_text or 'missing' in errors_text:
            suggestions.append("تأكد من وجود فترة محاسبية مفتوحة للتاريخ المحدد")
        
        if 'مغلقة' in errors_text or 'closed' in errors_text:
            suggestions.append("افتح الفترة المحاسبية أو استخدم تاريخ ضمن فترة مفتوحة")
        
        # إضافة اقتراح عام إذا لم يتم إضافة اقتراحات محددة
        if not suggestions:
            suggestions.append("راجع إعدادات النظام المالي وتأكد من صحة البيانات")
        else:
            suggestions.append("راجع إعدادات النظام المالي")
        
        return suggestions
    
    @staticmethod
    def validation_bypass_warning(
        entity_name: str,
        entity_type: str,
        bypass_reason: str,
        user_name: str = None
    ) -> str:
        """
        رسالة تحذير عند تجاوز التحقق
        
        Args:
            entity_name: اسم الكيان
            entity_type: نوع الكيان
            bypass_reason: سبب التجاوز
            user_name: اسم المستخدم (اختياري)
            
        Returns:
            str: رسالة التحذير بالعربية
        """
        entity_type_ar = ErrorMessageGenerator._get_entity_type_name(entity_type)
        
        message = f"⚠️ تحذير: تم تجاوز التحقق من المعاملة المالية ل{entity_type_ar}: {entity_name}"
        
        if user_name:
            message += f"\nالمستخدم: {user_name}"
        
        message += f"\nالسبب: {bypass_reason}"
        message += "\n\nتنبيه: تجاوز التحقق قد يؤدي إلى مشاكل في البيانات المحاسبية."
        
        return message
    
    @staticmethod
    def special_transaction_info(transaction_type: str) -> str:
        """
        رسالة معلومات للمعاملات الخاصة
        
        Args:
            transaction_type: نوع المعاملة (opening, adjustment, etc.)
            
        Returns:
            str: رسالة معلومات بالعربية
        """
        messages = {
            'opening': "ℹ️ قيد افتتاحي - تم تجاوز التحقق من الفترة المحاسبية",
            'adjustment': "ℹ️ تسوية محاسبية - تم التجاوز بصلاحيات خاصة",
            'system_generated': "ℹ️ معاملة مولدة من النظام - تم التحقق مع تسجيل خاص",
        }
        
        return messages.get(transaction_type, f"ℹ️ معاملة خاصة: {transaction_type}")
