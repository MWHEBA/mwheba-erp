"""
Management command: إصلاح قيم DateTimeField الغلط في جدول المستخدمين
الاستخدام: python manage.py fix_user_datetime_fields
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'إصلاح قيم DateTimeField الغلط (string بدل datetime) في جدول المستخدمين'

    def handle(self, *args, **options):
        self.stdout.write("🔍 فحص قيم DateTimeField في جدول المستخدمين...\n")

        fixed = 0
        errors = []

        # ── 1. فحص last_login و date_joined مباشرة من DB ──────────
        # جلب اسم الجدول الفعلي من الـ model
        user_table = User._meta.db_table  # users_user

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id, username, last_login, date_joined FROM {user_table}"
            )
            rows = cursor.fetchall()

        self.stdout.write(f"إجمالي المستخدمين: {len(rows)}\n")

        for user_id, username, last_login, date_joined in rows:
            issues = []

            # تحقق من last_login
            if last_login is not None and isinstance(last_login, str):
                issues.append(('last_login', last_login))

            # تحقق من date_joined
            if date_joined is not None and isinstance(date_joined, str):
                issues.append(('date_joined', date_joined))

            if issues:
                self.stdout.write(
                    f"  ❌ مستخدم #{user_id} ({username}) — قيم غلط: {issues}"
                )
                errors.append((user_id, username, issues))

        if not errors:
            self.stdout.write(self.style.SUCCESS(
                "✅ لا توجد قيم string في DateTimeFields — قاعدة البيانات سليمة!\n"
            ))
            self.stdout.write(
                "ℹ️  المشكلة ممكن تكون في جدول تاني. راجع الـ traceback بعناية:\n"
                "   → السطر: convert_datetimefield_value\n"
                "   → الجدول المحتمل: auth_user أو أي جدول بيتعمله JOIN مع User\n"
            )
            self._check_other_tables()
            return

        # ── 2. إصلاح القيم الغلط ──────────────────────────────────
        self.stdout.write(f"\n🔧 إصلاح {len(errors)} مستخدم...\n")

        from django.utils import timezone
        from datetime import datetime

        for user_id, username, issues in errors:
            for field, bad_value in issues:
                try:
                    # محاولة تحويل الـ string لـ datetime
                    if bad_value:
                        try:
                            # تجربة تحويل مباشر
                            dt = datetime.fromisoformat(str(bad_value).replace('Z', '+00:00'))
                        except ValueError:
                            # لو فشل، استخدم None
                            dt = None
                    else:
                        dt = None

                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"UPDATE {user_table} SET {field} = %s WHERE id = %s",
                            [dt, user_id]
                        )
                    fixed += 1
                    self.stdout.write(
                        f"  ✅ #{user_id} ({username}).{field}: '{bad_value}' → {dt}"
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  ❌ فشل إصلاح #{user_id}.{field}: {e}")
                    )

        self.stdout.write(self.style.SUCCESS(f"\n✅ تم إصلاح {fixed} قيمة\n"))

    def _check_other_tables(self):
        """فحص الجداول الأخرى المرتبطة بالـ User"""
        self.stdout.write("\n🔍 فحص جداول أخرى...\n")

        # الجداول الأكثر احتمالاً
        tables_to_check = [
            ('django_session', 'expire_date', None),
        ]

        with connection.cursor() as cursor:
            # جلب كل الجداول الموجودة
            cursor.execute("SHOW TABLES")
            all_tables = [row[0] for row in cursor.fetchall()]

        # فحص جدول django_session
        if 'django_session' in all_tables:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM django_session WHERE expire_date IS NOT NULL "
                    "AND expire_date NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}'"
                )
                bad_sessions = cursor.fetchone()[0]
                if bad_sessions > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠️  django_session: {bad_sessions} سجل بـ expire_date غلط"
                        )
                    )
                    # حذف الـ sessions الغلط
                    cursor.execute(
                        "DELETE FROM django_session WHERE expire_date IS NOT NULL "
                        "AND expire_date NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}'"
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✅ تم حذف {bad_sessions} session غلط")
                    )
                else:
                    self.stdout.write("  ✅ django_session: سليم")

        self.stdout.write(
            "\n💡 لو المشكلة لسه موجودة، شغّل:\n"
            "   python manage.py fix_user_datetime_fields --raw-sql\n"
            "   وشوف الـ error log بالكامل عشان تعرف الجدول الصح\n"
        )
