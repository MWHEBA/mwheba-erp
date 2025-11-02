# financial/management/commands/create_balances_test_data.py
"""
أمر لإنشاء بيانات وهمية لاختبار تقارير أرصدة العملاء والموردين
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'إنشاء بيانات وهمية لاختبار تقارير أرصدة العملاء والموردين'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sales',
            type=int,
            default=20,
            help='عدد فواتير المبيعات (افتراضي: 20)'
        )
        parser.add_argument(
            '--purchases',
            type=int,
            default=15,
            help='عدد فواتير المشتريات (افتراضي: 15)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        sales_count = options['sales']
        purchases_count = options['purchases']
        
        self.stdout.write(self.style.SUCCESS('🚀 بدء إنشاء بيانات أرصدة العملاء والموردين...'))
        
        # الحصول على مستخدم
        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('❌ لا يوجد مستخدمين في النظام'))
            return
        
        # إنشاء فواتير المبيعات
        created_sales = self._create_sales_invoices(user, sales_count)
        
        # إنشاء فواتير المشتريات
        created_purchases = self._create_purchase_invoices(user, purchases_count)
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ تم إنشاء {created_sales} فاتورة مبيعات و {created_purchases} فاتورة مشتريات بنجاح!'
        ))
    
    def _create_sales_invoices(self, user, count):
        """إنشاء فواتير مبيعات وهمية"""
        try:
            from client.models import Customer
            from sale.models import Sale
        except ImportError:
            self.stdout.write(self.style.WARNING('⚠️ نماذج المبيعات غير متوفرة'))
            return 0
        
        # إنشاء عملاء وهميين
        customers = []
        for i in range(10):
            customer, _ = Customer.objects.get_or_create(
                code=f'CUST{i+1:03d}',
                defaults={
                    'name': f'عميل {i+1}',
                    'phone': f'0100000{i+1:04d}',
                    'is_active': True,
                }
            )
            customers.append(customer)
        
        created = 0
        today = timezone.now().date()
        
        for i in range(count):
            # تاريخ عشوائي في آخر 150 يوم
            days_ago = random.randint(1, 150)
            invoice_date = today - timedelta(days=days_ago)
            
            # مبلغ عشوائي
            total = Decimal(random.randint(1000, 50000))
            
            # نسبة الدفع (0% - 80%)
            payment_percentage = random.choice([0, 0, 0, 20, 30, 50, 80])  # معظمها غير مدفوعة
            paid_amount = total * Decimal(payment_percentage) / 100
            
            # تحديد الحالة
            if paid_amount == 0:
                status = 'pending'
            elif paid_amount < total:
                status = 'partial'
            else:
                status = 'paid'
            
            try:
                sale = Sale.objects.create(
                    number=f'INV-{i+1:05d}',
                    customer=random.choice(customers),
                    date=invoice_date,
                    total=total,
                    paid_amount=paid_amount,
                    status=status,
                    created_by=user,
                )
                created += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️ فشل إنشاء فاتورة مبيعات: {e}'))
        
        return created
    
    def _create_purchase_invoices(self, user, count):
        """إنشاء فواتير مشتريات وهمية"""
        try:
            from supplier.models import Supplier
            from purchase.models import Purchase
        except ImportError:
            self.stdout.write(self.style.WARNING('⚠️ نماذج المشتريات غير متوفرة'))
            return 0
        
        # إنشاء موردين وهميين
        suppliers = []
        for i in range(8):
            supplier, _ = Supplier.objects.get_or_create(
                code=f'SUPP{i+1:03d}',
                defaults={
                    'name': f'مورد {i+1}',
                    'phone': f'0120000{i+1:04d}',
                    'is_active': True,
                }
            )
            suppliers.append(supplier)
        
        created = 0
        today = timezone.now().date()
        
        for i in range(count):
            # تاريخ عشوائي في آخر 150 يوم
            days_ago = random.randint(1, 150)
            invoice_date = today - timedelta(days=days_ago)
            
            # مبلغ عشوائي
            total = Decimal(random.randint(2000, 80000))
            
            # نسبة الدفع (0% - 70%)
            payment_percentage = random.choice([0, 0, 0, 10, 30, 50, 70])  # معظمها غير مدفوعة
            paid_amount = total * Decimal(payment_percentage) / 100
            
            # تحديد الحالة
            if paid_amount == 0:
                status = 'pending'
            elif paid_amount < total:
                status = 'partial'
            else:
                status = 'paid'
            
            try:
                purchase = Purchase.objects.create(
                    number=f'PINV-{i+1:05d}',
                    supplier=random.choice(suppliers),
                    date=invoice_date,
                    total=total,
                    paid_amount=paid_amount,
                    status=status,
                    created_by=user,
                )
                created += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️ فشل إنشاء فاتورة مشتريات: {e}'))
        
        return created
