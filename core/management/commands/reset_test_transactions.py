import sys
from django.core.management.base import BaseCommand
from core.services.system_reset_service import SystemResetService


class Command(BaseCommand):
    help = "تفريغ وتصفير كافة الحركات والمعاملات التجريبية (مبيعات، مشتريات، مخزن، قيود) مع الحفاظ على الإعدادات والمستخدمين وشجرة الحسابات."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            "--yes",
            "-y",
            action="store_true",
            help="تخطي رسالة التأكيد وتنفيذ التصفير مباشرة",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("=" * 70))
        self.stdout.write(self.style.WARNING("⚠️  تحذير: سيتم تفريغ كافة الحركات والمعاملات والقيود التجريبية!"))
        self.stdout.write(self.style.NOTICE("✅ سيتم الحفاظ على: الإعدادات، المستخدمين، شجرة الحسابات، العملات، والمخازن."))
        self.stdout.write(self.style.WARNING("=" * 70))

        if not options.get("no_input"):
            confirm = input("لتأكيد العملية، اكتب 'تأكيد' أو 'RESET' واضغط Enter: ")
            if confirm.strip() not in ["تأكيد", "RESET", "reset", "yes", "y"]:
                self.stdout.write(self.style.ERROR("❌ تم إلغاء العملية."))
                return

        self.stdout.write("جاري تفريغ الحركات والمعاملات...")
        summary = SystemResetService.reset_test_transactions()
        total_wiped = sum(summary.values())

        self.stdout.write(self.style.SUCCESS(f"✅ تم تفريغ الحركات بنجاح! إجمالي السجلات المحذوفة: {total_wiped} سجل."))
        for model_name, count in summary.items():
            if count > 0:
                self.stdout.write(f"  - {model_name}: {count}")
