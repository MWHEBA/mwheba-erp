"""
أمر Django لإصلاح العقود الفعالة التي لم تُنسخ بنودها للموظفين
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from hr.models import Contract, ContractSalaryComponent, SalaryComponent


class Command(BaseCommand):
    help = 'نسخ بنود الراتب للموظفين من العقود الفعالة التي فاتتها عملية النسخ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض ما سيتم نسخه بدون تطبيق التغييرات',
        )
        parser.add_argument(
            '--contract',
            type=str,
            help='رقم عقد محدد (اختياري)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        contract_number = options.get('contract')

        if dry_run:
            self.stdout.write(self.style.WARNING('[ تشغيل تجريبي - لن يتم حفظ أي تغييرات ]'))

        # جلب العقود الفعالة
        contracts_qs = Contract.objects.filter(status='active').select_related('employee')
        if contract_number:
            contracts_qs = contracts_qs.filter(contract_number=contract_number)

        if not contracts_qs.exists():
            self.stdout.write(self.style.WARNING('لا توجد عقود فعالة.'))
            return

        total_contracts = contracts_qs.count()
        self.stdout.write(f'عدد العقود الفعالة: {total_contracts}')

        total_copied = 0
        fixed_contracts = 0

        for contract in contracts_qs:
            employee = contract.employee
            contract_components = ContractSalaryComponent.objects.filter(
                contract=contract
            ).order_by('order')

            if not contract_components.exists():
                self.stdout.write(
                    self.style.WARNING(f'  [{contract.contract_number}] لا توجد بنود في العقد - تخطي')
                )
                continue

            # البنود الموجودة فعلاً عند الموظف من هذا العقد
            existing_employee_components = SalaryComponent.objects.filter(
                employee=employee,
                source_contract_component__in=contract_components,
                is_from_contract=True,
                is_active=True
            ).values_list('source_contract_component_id', flat=True)

            # البنود المفقودة
            missing = contract_components.exclude(id__in=existing_employee_components)

            if not missing.exists():
                self.stdout.write(
                    self.style.SUCCESS(f'  [{contract.contract_number}] {employee.get_full_name_ar()} - مكتمل ✓')
                )
                continue

            self.stdout.write(
                self.style.WARNING(
                    f'  [{contract.contract_number}] {employee.get_full_name_ar()} - '
                    f'{missing.count()} بند مفقود من أصل {contract_components.count()}'
                )
            )

            for comp in missing:
                self.stdout.write(f'    → {comp.component_type}: {comp.name} ({comp.amount})')

            if not dry_run:
                try:
                    with transaction.atomic():
                        copied = 0
                        for comp in missing:
                            new_comp = comp.copy_to_employee_component(employee)
                            if new_comp:
                                copied += 1
                        total_copied += copied
                        fixed_contracts += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'    ✓ تم نسخ {copied} بند بنجاح')
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'    ✗ خطأ: {str(e)}')
                    )
            else:
                total_copied += missing.count()
                fixed_contracts += 1

        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[ تجريبي ] سيتم نسخ {total_copied} بند في {fixed_contracts} عقد'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ تم إصلاح {fixed_contracts} عقد - نُسخ {total_copied} بند بنجاح'
                )
            )
