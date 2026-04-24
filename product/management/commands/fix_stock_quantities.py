"""
Management command to fix doubled stock quantities caused by double-update bug.
The bug: MovementService updated Stock directly AND the signal also updated it.
Fix: Reset all Stock quantities to 0, then recalculate from StockMovement records.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from product.models import Stock, StockMovement
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fix doubled stock quantities by recalculating from StockMovement records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually changing anything',
        )
        parser.add_argument(
            '--warehouse',
            type=int,
            help='Fix only a specific warehouse by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        warehouse_id = options.get('warehouse')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made\n'))

        # Build queryset
        movements_qs = StockMovement.objects.all().order_by('timestamp')
        stocks_qs = Stock.objects.all()

        if warehouse_id:
            movements_qs = movements_qs.filter(warehouse_id=warehouse_id)
            stocks_qs = stocks_qs.filter(warehouse_id=warehouse_id)
            self.stdout.write(f'Filtering to warehouse ID: {warehouse_id}\n')

        self.stdout.write(f'Total movements: {movements_qs.count()}')
        self.stdout.write(f'Total stock records: {stocks_qs.count()}\n')

        # Calculate correct quantities from movements
        correct_quantities = {}  # (product_id, warehouse_id) -> quantity

        for movement in movements_qs:
            key = (movement.product_id, movement.warehouse_id)
            if key not in correct_quantities:
                correct_quantities[key] = Decimal('0')

            if movement.movement_type in ['in', 'return_in']:
                correct_quantities[key] += Decimal(movement.quantity)
            elif movement.movement_type in ['out', 'return_out']:
                correct_quantities[key] = max(Decimal('0'), correct_quantities[key] - Decimal(movement.quantity))
            elif movement.movement_type == 'adjustment':
                correct_quantities[key] = Decimal(movement.quantity)
            # transfer handled by separate in/out movements

        # Compare and fix
        fixed_count = 0
        for stock in stocks_qs.select_related('product', 'warehouse'):
            key = (stock.product_id, stock.warehouse_id)
            correct_qty = correct_quantities.get(key, Decimal('0'))
            current_qty = Decimal(str(stock.quantity))

            if current_qty != correct_qty:
                self.stdout.write(
                    f'  {stock.product.name} @ {stock.warehouse.name}: '
                    f'{current_qty} → {correct_qty}'
                )
                if not dry_run:
                    stock.quantity = correct_qty
                    stock.save(update_fields=['quantity'])
                fixed_count += 1

        if fixed_count == 0:
            self.stdout.write(self.style.SUCCESS('All stock quantities are correct - nothing to fix'))
        elif dry_run:
            self.stdout.write(self.style.WARNING(f'\n{fixed_count} records would be fixed (dry run)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nFixed {fixed_count} stock records'))
