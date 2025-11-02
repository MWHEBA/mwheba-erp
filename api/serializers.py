"""
Serializers لنظام API
يحتوي على جميع الـ Serializers للنماذج الرئيسية في النظام
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from product.models import Product, Category, Stock, StockMovement, Warehouse
from supplier.models import Supplier, SupplierType
from client.models import Customer
from sale.models import Sale, SaleItem
from purchase.models import Purchase, PurchaseItem
from financial.models import ChartOfAccounts, JournalEntry, JournalEntryLine

User = get_user_model()


# ==================== User Serializers ====================

class UserSerializer(serializers.ModelSerializer):
    """Serializer للمستخدمين"""
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone', 'role', 'is_active', 'is_staff', 'date_joined'
        ]
        read_only_fields = ['id', 'date_joined']
        extra_kwargs = {
            'password': {'write_only': True}
        }


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer لإنشاء مستخدم جديد"""
    
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone', 'role'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "كلمات المرور غير متطابقة"})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


# ==================== Product Serializers ====================

class CategorySerializer(serializers.ModelSerializer):
    """Serializer للتصنيفات"""
    
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'parent', 'product_count', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_product_count(self, obj):
        return obj.products.count()


class ProductListSerializer(serializers.ModelSerializer):
    """Serializer لقائمة المنتجات (مختصر)"""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    total_stock = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'category', 'category_name',
            'unit_price', 'cost_price', 'total_stock', 'is_active'
        ]
        read_only_fields = ['id']
    
    def get_total_stock(self, obj):
        return obj.get_total_stock()


class ProductDetailSerializer(serializers.ModelSerializer):
    """Serializer لتفاصيل المنتج (كامل)"""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    total_stock = serializers.SerializerMethodField()
    stock_value = serializers.SerializerMethodField()
    recent_movements = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode', 'category', 'category_name',
            'description', 'unit_price', 'cost_price', 'min_stock_level',
            'max_stock_level', 'reorder_point', 'unit_of_measure',
            'total_stock', 'stock_value', 'is_active', 'recent_movements',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_stock(self, obj):
        return obj.get_total_stock()
    
    def get_stock_value(self, obj):
        return obj.get_total_stock() * obj.cost_price
    
    def get_recent_movements(self, obj):
        movements = StockMovement.objects.filter(product=obj).order_by('-created_at')[:5]
        return StockMovementSerializer(movements, many=True).data


class StockSerializer(serializers.ModelSerializer):
    """Serializer للمخزون"""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    
    class Meta:
        model = Stock
        fields = [
            'id', 'product', 'product_name', 'warehouse', 'warehouse_name',
            'quantity', 'reserved_quantity', 'available_quantity',
            'last_updated', 'created_at'
        ]
        read_only_fields = ['id', 'available_quantity', 'last_updated', 'created_at']


class StockMovementSerializer(serializers.ModelSerializer):
    """Serializer لحركات المخزون"""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'warehouse', 'warehouse_name',
            'movement_type', 'quantity', 'reference_type', 'reference_id',
            'notes', 'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class WarehouseSerializer(serializers.ModelSerializer):
    """Serializer للمخازن"""
    
    total_products = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()
    
    class Meta:
        model = Warehouse
        fields = [
            'id', 'name', 'code', 'location', 'description',
            'is_active', 'total_products', 'total_value', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_total_products(self, obj):
        return obj.stocks.count()
    
    def get_total_value(self, obj):
        total = 0
        for stock in obj.stocks.all():
            total += stock.quantity * stock.product.cost_price
        return total


# ==================== Supplier Serializers ====================

class SupplierTypeSerializer(serializers.ModelSerializer):
    """Serializer لأنواع الموردين"""
    
    supplier_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SupplierType
        fields = ['id', 'name', 'slug', 'description', 'supplier_count']
        read_only_fields = ['id', 'slug']
    
    def get_supplier_count(self, obj):
        return obj.suppliers.count()


class SupplierListSerializer(serializers.ModelSerializer):
    """Serializer لقائمة الموردين (مختصر)"""
    
    type_name = serializers.CharField(source='type.name', read_only=True)
    total_purchases = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'type', 'type_name', 'phone', 'email',
            'total_purchases', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_total_purchases(self, obj):
        return obj.purchases.count()


class SupplierDetailSerializer(serializers.ModelSerializer):
    """Serializer لتفاصيل المورد (كامل)"""
    
    type_name = serializers.CharField(source='type.name', read_only=True)
    total_purchases = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    account_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'type', 'type_name', 'phone', 'email',
            'address', 'city', 'country', 'tax_number', 'account',
            'payment_terms', 'credit_limit', 'notes',
            'total_purchases', 'total_amount', 'account_balance',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_purchases(self, obj):
        return obj.purchases.count()
    
    def get_total_amount(self, obj):
        return sum(p.total_amount for p in obj.purchases.all())
    
    def get_account_balance(self, obj):
        if obj.account:
            return obj.account.get_balance()
        return 0


# ==================== Customer Serializers ====================

class CustomerListSerializer(serializers.ModelSerializer):
    """Serializer لقائمة العملاء (مختصر)"""
    
    total_sales = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'total_sales',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_total_sales(self, obj):
        return obj.sales.count()


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Serializer لتفاصيل العميل (كامل)"""
    
    total_sales = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    account_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'address', 'city',
            'country', 'tax_number', 'account', 'credit_limit',
            'payment_terms', 'notes', 'total_sales', 'total_amount',
            'account_balance', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_sales(self, obj):
        return obj.sales.count()
    
    def get_total_amount(self, obj):
        return sum(s.total_amount for s in obj.sales.all())
    
    def get_account_balance(self, obj):
        if obj.account:
            return obj.account.get_balance()
        return 0


# ==================== Sale Serializers ====================

class SaleItemSerializer(serializers.ModelSerializer):
    """Serializer لعناصر المبيعات"""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = SaleItem
        fields = [
            'id', 'product', 'product_name', 'quantity',
            'unit_price', 'discount', 'tax_rate', 'total'
        ]
        read_only_fields = ['id', 'total']


class SaleListSerializer(serializers.ModelSerializer):
    """Serializer لقائمة المبيعات (مختصر)"""
    
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Sale
        fields = [
            'id', 'invoice_number', 'customer', 'customer_name',
            'date', 'total_amount', 'status', 'items_count', 'created_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at']
    
    def get_items_count(self, obj):
        return obj.items.count()


class SaleDetailSerializer(serializers.ModelSerializer):
    """Serializer لتفاصيل المبيعات (كامل)"""
    
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    items = SaleItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Sale
        fields = [
            'id', 'invoice_number', 'customer', 'customer_name',
            'date', 'due_date', 'subtotal', 'discount', 'tax',
            'total_amount', 'paid_amount', 'status', 'payment_method',
            'notes', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at']


# ==================== Purchase Serializers ====================

class PurchaseItemSerializer(serializers.ModelSerializer):
    """Serializer لعناصر المشتريات"""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = PurchaseItem
        fields = [
            'id', 'product', 'product_name', 'quantity',
            'unit_price', 'discount', 'tax_rate', 'total'
        ]
        read_only_fields = ['id', 'total']


class PurchaseListSerializer(serializers.ModelSerializer):
    """Serializer لقائمة المشتريات (مختصر)"""
    
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Purchase
        fields = [
            'id', 'invoice_number', 'supplier', 'supplier_name',
            'date', 'total_amount', 'status', 'items_count', 'created_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at']
    
    def get_items_count(self, obj):
        return obj.items.count()


class PurchaseDetailSerializer(serializers.ModelSerializer):
    """Serializer لتفاصيل المشتريات (كامل)"""
    
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = PurchaseItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Purchase
        fields = [
            'id', 'invoice_number', 'supplier', 'supplier_name',
            'date', 'due_date', 'subtotal', 'discount', 'tax',
            'total_amount', 'paid_amount', 'status', 'payment_method',
            'notes', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at']


# ==================== Financial Serializers ====================

class ChartOfAccountsSerializer(serializers.ModelSerializer):
    """Serializer لدليل الحسابات"""
    
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    balance = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChartOfAccounts
        fields = [
            'id', 'code', 'name', 'name_en', 'account_type',
            'parent', 'parent_name', 'level', 'balance',
            'children_count', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'level', 'created_at']
    
    def get_balance(self, obj):
        return obj.get_balance()
    
    def get_children_count(self, obj):
        return obj.children.count()


class JournalEntryLineSerializer(serializers.ModelSerializer):
    """Serializer لسطور القيد المحاسبي"""
    
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = JournalEntryLine
        fields = [
            'id', 'account', 'account_name', 'debit', 'credit', 'description'
        ]
        read_only_fields = ['id']


class JournalEntryListSerializer(serializers.ModelSerializer):
    """Serializer لقائمة القيود المحاسبية (مختصر)"""
    
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    lines_count = serializers.SerializerMethodField()
    
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'date', 'description',
            'total_debit', 'total_credit', 'status',
            'lines_count', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['id', 'entry_number', 'created_at']
    
    def get_lines_count(self, obj):
        return obj.lines.count()


class JournalEntryDetailSerializer(serializers.ModelSerializer):
    """Serializer لتفاصيل القيد المحاسبي (كامل)"""
    
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    lines = JournalEntryLineSerializer(many=True, read_only=True)
    
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'date', 'description',
            'reference_type', 'reference_id', 'total_debit',
            'total_credit', 'status', 'notes', 'lines',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'entry_number', 'created_by', 'created_at', 'updated_at']
