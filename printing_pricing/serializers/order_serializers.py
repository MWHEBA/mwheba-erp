from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from ..models import PrintingOrder, OrderMaterial, OrderService, PaperSpecification, PrintingSpecification
from client.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    """
    مسلسل العميل للاستخدام في APIs
    """
    class Meta:
        model = Customer
        fields = ['id', 'name', 'company_name', 'phone', 'email']


class OrderMaterialSerializer(serializers.ModelSerializer):
    """
    مسلسل مواد الطلب
    """
    class Meta:
        model = OrderMaterial
        fields = [
            'id', 'material_type', 'material_name', 'quantity',
            'unit', 'unit_cost', 'total_cost', 'waste_percentage'
        ]
        read_only_fields = ['total_cost']


class OrderServiceSerializer(serializers.ModelSerializer):
    """
    مسلسل خدمات الطلب
    """
    class Meta:
        model = OrderService
        fields = [
            'id', 'service_category', 'service_name', 'service_description',
            'quantity', 'unit', 'unit_price', 'setup_cost', 'total_cost',
            'is_optional', 'execution_time'
        ]
        read_only_fields = ['total_cost']


class PaperSpecificationSerializer(serializers.ModelSerializer):
    """
    مسلسل مواصفات الورق
    """
    class Meta:
        model = PaperSpecification
        fields = [
            'paper_type_name', 'paper_weight', 'paper_size_name',
            'sheet_width', 'sheet_height', 'sheets_needed',
            'montage_count', 'sheet_cost', 'total_paper_cost'
        ]
        read_only_fields = ['total_paper_cost']


class PrintingSpecificationSerializer(serializers.ModelSerializer):
    """
    مسلسل مواصفات الطباعة
    """
    class Meta:
        model = PrintingSpecification
        fields = [
            'printing_type', 'colors_front', 'colors_back',
            'is_cmyk', 'has_spot_colors', 'spot_colors_count',
            'resolution_dpi', 'print_quality', 'plates_cost',
            'printing_cost', 'special_requirements'
        ]


class PrintingOrderListSerializer(serializers.ModelSerializer):
    """
    مسلسل قائمة طلبات التسعير (عرض مبسط)
    """
    customer = CustomerSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_type_display = serializers.CharField(source='get_order_type_display', read_only=True)
    
    class Meta:
        model = PrintingOrder
        fields = [
            'id', 'order_number', 'customer', 'title', 'status',
            'status_display', 'order_type', 'order_type_display',
            'quantity', 'estimated_cost', 'created_at', 'due_date'
        ]


class PrintingOrderDetailSerializer(serializers.ModelSerializer):
    """
    مسلسل تفاصيل طلب التسعير (عرض شامل)
    """
    customer = CustomerSerializer(read_only=True)
    materials = OrderMaterialSerializer(many=True, read_only=True)
    services = OrderServiceSerializer(many=True, read_only=True)
    paper_spec = PaperSpecificationSerializer(read_only=True)
    printing_spec = PrintingSpecificationSerializer(read_only=True)
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_type_display = serializers.CharField(source='get_order_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    
    total_pages = serializers.ReadOnlyField()
    total_items = serializers.ReadOnlyField()
    
    class Meta:
        model = PrintingOrder
        fields = [
            'id', 'order_number', 'customer', 'title', 'description',
            'order_type', 'order_type_display', 'status', 'status_display',
            'quantity', 'pages_count', 'copies_count', 'total_pages', 'total_items',
            'width', 'height', 'estimated_cost', 'final_price', 'profit_margin',
            'priority', 'priority_display', 'is_rush_order', 'rush_fee',
            'due_date', 'approved_at', 'created_at', 'updated_at',
            'materials', 'services', 'paper_spec', 'printing_spec', 'notes'
        ]


class PrintingOrderCreateSerializer(serializers.ModelSerializer):
    """
    مسلسل إنشاء طلب تسعير جديد
    """
    customer_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = PrintingOrder
        fields = [
            'customer_id', 'title', 'description', 'order_type',
            'quantity', 'pages_count', 'copies_count',
            'width', 'height', 'priority', 'due_date',
            'is_rush_order', 'rush_fee', 'profit_margin', 'notes'
        ]
    
    def validate_customer_id(self, value):
        """التحقق من صحة معرف العميل"""
        try:
            customer = Customer.objects.get(id=value, is_active=True)
            return value
        except Customer.DoesNotExist:
            raise serializers.ValidationError(_('العميل غير موجود أو غير نشط'))
    
    def validate_quantity(self, value):
        """التحقق من الكمية"""
        if value <= 0:
            raise serializers.ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        return value
    
    def validate_profit_margin(self, value):
        """التحقق من هامش الربح"""
        if value < 0 or value > 100:
            raise serializers.ValidationError(_('هامش الربح يجب أن يكون بين 0 و 100%'))
        return value
    
    def create(self, validated_data):
        """إنشاء طلب تسعير جديد"""
        customer_id = validated_data.pop('customer_id')
        customer = Customer.objects.get(id=customer_id)
        
        order = PrintingOrder.objects.create(
            customer=customer,
            created_by=self.context['request'].user,
            updated_by=self.context['request'].user,
            **validated_data
        )
        
        return order


class PrintingOrderUpdateSerializer(serializers.ModelSerializer):
    """
    مسلسل تحديث طلب التسعير
    """
    class Meta:
        model = PrintingOrder
        fields = [
            'title', 'description', 'order_type', 'quantity',
            'pages_count', 'copies_count', 'width', 'height',
            'priority', 'due_date', 'is_rush_order', 'rush_fee',
            'profit_margin', 'notes'
        ]
    
    def validate_quantity(self, value):
        """التحقق من الكمية"""
        if value <= 0:
            raise serializers.ValidationError(_('الكمية يجب أن تكون أكبر من صفر'))
        return value
    
    def update(self, instance, validated_data):
        """تحديث طلب التسعير"""
        # تحديث المستخدم
        instance.updated_by = self.context['request'].user
        
        # تحديث الحقول
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


__all__ = [
    'CustomerSerializer', 'OrderMaterialSerializer', 'OrderServiceSerializer',
    'PaperSpecificationSerializer', 'PrintingSpecificationSerializer',
    'PrintingOrderListSerializer', 'PrintingOrderDetailSerializer',
    'PrintingOrderCreateSerializer', 'PrintingOrderUpdateSerializer'
]
