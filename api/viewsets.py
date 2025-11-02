"""
ViewSets لنظام API
يحتوي على جميع الـ ViewSets للنماذج الرئيسية في النظام
"""

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q, F

from product.models import Product, Category, Stock, StockMovement, Warehouse
from supplier.models import Supplier, SupplierType
from client.models import Customer
from sale.models import Sale, SaleItem
from purchase.models import Purchase, PurchaseItem
from financial.models import ChartOfAccounts, JournalEntry, JournalEntryLine

from .serializers import (
    UserSerializer, UserCreateSerializer,
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    StockSerializer, StockMovementSerializer, WarehouseSerializer,
    SupplierTypeSerializer, SupplierListSerializer, SupplierDetailSerializer,
    CustomerListSerializer, CustomerDetailSerializer,
    SaleListSerializer, SaleDetailSerializer, SaleItemSerializer,
    PurchaseListSerializer, PurchaseDetailSerializer, PurchaseItemSerializer,
    ChartOfAccountsSerializer, JournalEntryListSerializer, JournalEntryDetailSerializer
)
from .permissions import IsManagerOrReadOnly, IsAdminOrReadOnly

User = get_user_model()


# ==================== User ViewSets ====================

class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet للمستخدمين
    يوفر عمليات CRUD كاملة للمستخدمين
    """
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['date_joined', 'username']
    ordering = ['-date_joined']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """الحصول على معلومات المستخدم الحالي"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات المستخدمين"""
        total = User.objects.count()
        active = User.objects.filter(is_active=True).count()
        staff = User.objects.filter(is_staff=True).count()
        by_role = User.objects.values('role').annotate(count=Count('id'))
        
        return Response({
            'total': total,
            'active': active,
            'staff': staff,
            'by_role': list(by_role)
        })


# ==================== Product ViewSets ====================

class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet للتصنيفات"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet للمنتجات"""
    queryset = Product.objects.select_related('category').all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'sku', 'barcode', 'description']
    ordering_fields = ['name', 'unit_price', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """المنتجات منخفضة المخزون"""
        products = Product.objects.filter(
            is_active=True
        ).annotate(
            total_stock=Sum('stocks__quantity')
        ).filter(
            Q(total_stock__lte=F('reorder_point')) | Q(total_stock__isnull=True)
        )
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات المنتجات"""
        total = Product.objects.count()
        active = Product.objects.filter(is_active=True).count()
        low_stock = Product.objects.filter(
            stocks__quantity__lte=F('reorder_point')
        ).distinct().count()
        total_value = sum(
            p.get_total_stock() * p.cost_price 
            for p in Product.objects.all()
        )
        
        return Response({
            'total': total,
            'active': active,
            'low_stock': low_stock,
            'total_value': total_value
        })
    
    @action(detail=True, methods=['get'])
    def stock_history(self, request, pk=None):
        """سجل حركات المخزون للمنتج"""
        product = self.get_object()
        movements = StockMovement.objects.filter(product=product).order_by('-created_at')
        serializer = StockMovementSerializer(movements, many=True)
        return Response(serializer.data)


class StockViewSet(viewsets.ModelViewSet):
    """ViewSet للمخزون"""
    queryset = Stock.objects.select_related('product', 'warehouse').all()
    serializer_class = StockSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'warehouse']
    ordering_fields = ['quantity', 'last_updated']
    ordering = ['-last_updated']
    
    @action(detail=False, methods=['get'])
    def by_warehouse(self, request):
        """المخزون حسب المخزن"""
        warehouse_id = request.query_params.get('warehouse_id')
        if warehouse_id:
            stocks = self.queryset.filter(warehouse_id=warehouse_id)
            serializer = self.get_serializer(stocks, many=True)
            return Response(serializer.data)
        return Response({'error': 'warehouse_id مطلوب'}, status=400)


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet لحركات المخزون (قراءة فقط)"""
    queryset = StockMovement.objects.select_related(
        'product', 'warehouse', 'created_by'
    ).all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'warehouse', 'movement_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']


class WarehouseViewSet(viewsets.ModelViewSet):
    """ViewSet للمخازن"""
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code', 'location']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    @action(detail=True, methods=['get'])
    def inventory(self, request, pk=None):
        """جرد المخزن"""
        warehouse = self.get_object()
        stocks = Stock.objects.filter(warehouse=warehouse).select_related('product')
        serializer = StockSerializer(stocks, many=True)
        return Response(serializer.data)


# ==================== Supplier ViewSets ====================

class SupplierTypeViewSet(viewsets.ModelViewSet):
    """ViewSet لأنواع الموردين"""
    queryset = SupplierType.objects.all()
    serializer_class = SupplierTypeSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']


class SupplierViewSet(viewsets.ModelViewSet):
    """ViewSet للموردين"""
    queryset = Supplier.objects.select_related('type', 'account').all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'is_active']
    search_fields = ['name', 'phone', 'email', 'tax_number']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierListSerializer
        return SupplierDetailSerializer
    
    @action(detail=True, methods=['get'])
    def purchases(self, request, pk=None):
        """مشتريات المورد"""
        supplier = self.get_object()
        purchases = Purchase.objects.filter(supplier=supplier).order_by('-date')
        serializer = PurchaseListSerializer(purchases, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات الموردين"""
        total = Supplier.objects.count()
        active = Supplier.objects.filter(is_active=True).count()
        by_type = Supplier.objects.values('type__name').annotate(count=Count('id'))
        
        return Response({
            'total': total,
            'active': active,
            'by_type': list(by_type)
        })


# ==================== Customer ViewSets ====================

class CustomerViewSet(viewsets.ModelViewSet):
    """ViewSet للعملاء"""
    queryset = Customer.objects.select_related('account').all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'phone', 'email', 'tax_number']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        return CustomerDetailSerializer
    
    @action(detail=True, methods=['get'])
    def sales(self, request, pk=None):
        """مبيعات العميل"""
        customer = self.get_object()
        sales = Sale.objects.filter(customer=customer).order_by('-date')
        serializer = SaleListSerializer(sales, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات العملاء"""
        total = Customer.objects.count()
        active = Customer.objects.filter(is_active=True).count()
        total_sales = Sale.objects.aggregate(total=Sum('total_amount'))['total'] or 0
        
        return Response({
            'total': total,
            'active': active,
            'total_sales': total_sales
        })


# ==================== Sale ViewSets ====================

class SaleViewSet(viewsets.ModelViewSet):
    """ViewSet للمبيعات"""
    queryset = Sale.objects.select_related('customer').prefetch_related('items').all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer', 'status', 'payment_method']
    search_fields = ['invoice_number', 'customer__name']
    ordering_fields = ['date', 'total_amount', 'created_at']
    ordering = ['-date']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SaleListSerializer
        return SaleDetailSerializer
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات المبيعات"""
        total_count = Sale.objects.count()
        total_amount = Sale.objects.aggregate(total=Sum('total_amount'))['total'] or 0
        paid_amount = Sale.objects.aggregate(paid=Sum('paid_amount'))['paid'] or 0
        by_status = Sale.objects.values('status').annotate(count=Count('id'))
        
        return Response({
            'total_count': total_count,
            'total_amount': total_amount,
            'paid_amount': paid_amount,
            'outstanding': total_amount - paid_amount,
            'by_status': list(by_status)
        })
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """آخر المبيعات"""
        limit = int(request.query_params.get('limit', 10))
        sales = self.queryset.order_by('-created_at')[:limit]
        serializer = self.get_serializer(sales, many=True)
        return Response(serializer.data)


# ==================== Purchase ViewSets ====================

class PurchaseViewSet(viewsets.ModelViewSet):
    """ViewSet للمشتريات"""
    queryset = Purchase.objects.select_related('supplier').prefetch_related('items').all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier', 'status', 'payment_method']
    search_fields = ['invoice_number', 'supplier__name']
    ordering_fields = ['date', 'total_amount', 'created_at']
    ordering = ['-date']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseListSerializer
        return PurchaseDetailSerializer
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات المشتريات"""
        total_count = Purchase.objects.count()
        total_amount = Purchase.objects.aggregate(total=Sum('total_amount'))['total'] or 0
        paid_amount = Purchase.objects.aggregate(paid=Sum('paid_amount'))['paid'] or 0
        by_status = Purchase.objects.values('status').annotate(count=Count('id'))
        
        return Response({
            'total_count': total_count,
            'total_amount': total_amount,
            'paid_amount': paid_amount,
            'outstanding': total_amount - paid_amount,
            'by_status': list(by_status)
        })
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """آخر المشتريات"""
        limit = int(request.query_params.get('limit', 10))
        purchases = self.queryset.order_by('-created_at')[:limit]
        serializer = self.get_serializer(purchases, many=True)
        return Response(serializer.data)


# ==================== Financial ViewSets ====================

class ChartOfAccountsViewSet(viewsets.ModelViewSet):
    """ViewSet لدليل الحسابات"""
    queryset = ChartOfAccounts.objects.select_related('parent').all()
    serializer_class = ChartOfAccountsSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['account_type', 'is_active']
    search_fields = ['code', 'name', 'name_en']
    ordering_fields = ['code', 'name']
    ordering = ['code']
    
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """شجرة الحسابات"""
        root_accounts = ChartOfAccounts.objects.filter(parent__isnull=True)
        serializer = self.get_serializer(root_accounts, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def transactions(self, request, pk=None):
        """معاملات الحساب"""
        account = self.get_object()
        lines = JournalEntryLine.objects.filter(
            account=account
        ).select_related('journal_entry').order_by('-journal_entry__date')
        
        transactions = []
        for line in lines:
            transactions.append({
                'date': line.journal_entry.date,
                'entry_number': line.journal_entry.entry_number,
                'description': line.description or line.journal_entry.description,
                'debit': line.debit,
                'credit': line.credit
            })
        
        return Response(transactions)


class JournalEntryViewSet(viewsets.ModelViewSet):
    """ViewSet للقيود المحاسبية"""
    queryset = JournalEntry.objects.prefetch_related('lines').all()
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'reference_type']
    search_fields = ['entry_number', 'description']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JournalEntryListSerializer
        return JournalEntryDetailSerializer
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات القيود المحاسبية"""
        total = JournalEntry.objects.count()
        posted = JournalEntry.objects.filter(status='posted').count()
        draft = JournalEntry.objects.filter(status='draft').count()
        total_debit = JournalEntry.objects.aggregate(
            total=Sum('total_debit')
        )['total'] or 0
        
        return Response({
            'total': total,
            'posted': posted,
            'draft': draft,
            'total_debit': total_debit
        })
    
    @action(detail=True, methods=['post'])
    def post_entry(self, request, pk=None):
        """ترحيل القيد"""
        entry = self.get_object()
        if entry.status == 'posted':
            return Response(
                {'error': 'القيد مرحل بالفعل'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        entry.status = 'posted'
        entry.save()
        serializer = self.get_serializer(entry)
        return Response(serializer.data)
