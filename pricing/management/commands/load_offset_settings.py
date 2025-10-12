from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from django.utils.translation import gettext as _


class Command(BaseCommand):
    help = "تحميل إعدادات ماكينات الأوفست الأولية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--separate",
            action="store_true",
            help="تحميل من ملفات منفصلة بدلاً من ملف واحد",
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("🏭 تحميل إعدادات ماكينات الأوفست"))
        self.stdout.write("=" * 60)

        try:
            with transaction.atomic():
                if options["separate"]:
                    # تحميل من ملفات منفصلة
                    self.stdout.write("📥 تحميل أنواع ماكينات الأوفست...")
                    call_command(
                        "loaddata",
                        "pricing/fixtures/offset_machine_types.json",
                        verbosity=0,
                    )

                    self.stdout.write("📥 تحميل مقاسات ماكينات الأوفست...")
                    call_command(
                        "loaddata",
                        "pricing/fixtures/offset_sheet_sizes.json",
                        verbosity=0,
                    )
                else:
                    # تحميل من ملف واحد
                    self.stdout.write("📥 تحميل جميع إعدادات ماكينات الأوفست...")
                    call_command(
                        "loaddata",
                        "pricing/fixtures/offset_settings_initial_data.json",
                        verbosity=0,
                    )

                self.stdout.write(
                    self.style.SUCCESS("✅ تم تحميل إعدادات ماكينات الأوفست بنجاح!")
                )
                self.stdout.write("\n📊 البيانات المحملة:")
                self.stdout.write("   • 2 نوع ماكينة أوفست (هايدلبرج SM52 و GTO52)")
                self.stdout.write("   • 3 مقاسات ورق (ربع فرخ، نصف فرخ، فرخ كامل)")

                self.stdout.write("\n🌐 يمكنك الآن زيارة:")
                self.stdout.write(
                    "   • http://127.0.0.1:8000/pricing/settings/offset-machine-types/"
                )
                self.stdout.write(
                    "   • http://127.0.0.1:8000/pricing/settings/offset-sheet-sizes/"
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ خطأ في تحميل البيانات: {e}"))
            raise
