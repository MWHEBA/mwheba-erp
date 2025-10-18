from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from ..models import CostCalculation, OrderSummary, CalculationType


class CostCalculationSerializer(serializers.ModelSerializer):
    """
    مسلسل حسابات التكلفة
    """
    calculation_type_display = serializers.CharField(source='get_calculation_type_display', read_only=True)
    
    class Meta:
        model = CostCalculation
        fields = [
            'id', 'calculation_type', 'calculation_type_display',
            'base_cost', 'additional_costs', 'total_cost',
            'calculation_details', 'parameters_used',
            'calculation_date', 'is_current'
        ]
        read_only_fields = ['calculation_date', 'total_cost']


class OrderSummarySerializer(serializers.ModelSerializer):
    """
    مسلسل ملخص الطلب
    """
    cost_breakdown = serializers.ReadOnlyField()
    
    class Meta:
        model = OrderSummary
        fields = [
            'material_cost', 'printing_cost', 'finishing_cost',
            'design_cost', 'other_costs', 'subtotal',
            'discount_amount', 'tax_amount', 'rush_fee',
            'total_cost', 'profit_margin_percentage',
            'profit_amount', 'final_price', 'last_calculated',
            'calculation_notes', 'cost_breakdown'
        ]
        read_only_fields = [
            'subtotal', 'total_cost', 'profit_amount',
            'final_price', 'last_calculated'
        ]


class CalculationRequestSerializer(serializers.Serializer):
    """
    مسلسل طلب حساب التكلفة
    """
    order_id = serializers.IntegerField()
    calculation_types = serializers.ListField(
        child=serializers.ChoiceField(choices=CalculationType.choices),
        allow_empty=False
    )
    parameters = serializers.DictField(required=False, default=dict)
    
    def validate_order_id(self, value):
        """التحقق من صحة معرف الطلب"""
        from ..models import PrintingOrder
        
        try:
            order = PrintingOrder.objects.get(id=value, is_active=True)
            return value
        except PrintingOrder.DoesNotExist:
            raise serializers.ValidationError(_('طلب التسعير غير موجود أو غير نشط'))
    
    def validate_calculation_types(self, value):
        """التحقق من أنواع الحسابات"""
        if not value:
            raise serializers.ValidationError(_('يجب تحديد نوع واحد على الأقل من الحسابات'))
        
        valid_types = [choice[0] for choice in CalculationType.choices]
        for calc_type in value:
            if calc_type not in valid_types:
                raise serializers.ValidationError(
                    _('نوع الحساب {} غير صحيح').format(calc_type)
                )
        
        return value


class CalculationResultSerializer(serializers.Serializer):
    """
    مسلسل نتائج الحساب
    """
    success = serializers.BooleanField()
    calculation_type = serializers.ChoiceField(choices=CalculationType.choices)
    base_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    additional_costs = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    details = serializers.DictField()
    error = serializers.CharField(required=False)


class MaterialCalculationSerializer(serializers.Serializer):
    """
    مسلسل حساب تكلفة المواد
    """
    material_type = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0.001)
    unit_cost = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    waste_percentage = serializers.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        min_value=0, 
        max_value=50,
        default=5.0
    )
    
    def validate_quantity(self, value):
        """التحقق من الكمية"""
        if value <= 0:
            raise serializers.ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        return value


class PrintingCalculationSerializer(serializers.Serializer):
    """
    مسلسل حساب تكلفة الطباعة
    """
    quantity = serializers.IntegerField(min_value=1)
    colors_front = serializers.IntegerField(min_value=0, max_value=10, default=1)
    colors_back = serializers.IntegerField(min_value=0, max_value=10, default=0)
    spot_colors_count = serializers.IntegerField(min_value=0, max_value=5, default=0)
    plates_cost_per_color = serializers.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        min_value=0,
        default=50.0
    )
    printing_cost_per_thousand = serializers.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        min_value=0,
        default=100.0
    )


class FinishingCalculationSerializer(serializers.Serializer):
    """
    مسلسل حساب تكلفة التشطيبات
    """
    finishing_type = serializers.ChoiceField(choices=[
        ('cutting', _('تقطيع')),
        ('folding', _('طي')),
        ('binding', _('تجليد')),
        ('lamination', _('تقفيل')),
        ('coating', _('تغطية')),
        ('embossing', _('بصمة')),
        ('perforation', _('ثقب')),
        ('numbering', _('ترقيم'))
    ])
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0.001)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    setup_cost = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        min_value=0,
        default=0.0
    )
    complexity_factor = serializers.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        min_value=0.5, 
        max_value=3.0,
        default=1.0
    )


class DesignCalculationSerializer(serializers.Serializer):
    """
    مسلسل حساب تكلفة التصميم
    """
    design_hours = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    hourly_rate = serializers.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        min_value=0,
        default=50.0
    )
    complexity_factor = serializers.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        min_value=0.5, 
        max_value=3.0,
        default=1.0
    )


class TotalCalculationSerializer(serializers.Serializer):
    """
    مسلسل حساب التكلفة الإجمالية
    """
    discount_percentage = serializers.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        min_value=0, 
        max_value=100,
        default=0.0
    )
    tax_percentage = serializers.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        min_value=0, 
        max_value=100,
        default=0.0
    )
    rush_fee = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        min_value=0,
        default=0.0
    )


__all__ = [
    'CostCalculationSerializer', 'OrderSummarySerializer',
    'CalculationRequestSerializer', 'CalculationResultSerializer',
    'MaterialCalculationSerializer', 'PrintingCalculationSerializer',
    'FinishingCalculationSerializer', 'DesignCalculationSerializer',
    'TotalCalculationSerializer'
]
