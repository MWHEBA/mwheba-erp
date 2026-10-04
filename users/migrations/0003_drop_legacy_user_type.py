from django.db import migrations


def drop_or_nullify_legacy_user_type(apps, schema_editor):
    """
    Remove or allow NULL for legacy user_type column if it still exists in the MySQL table.
    """
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'mysql':
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                  AND TABLE_NAME = 'users_user' 
                  AND COLUMN_NAME = 'user_type'
            """)
            row = cursor.fetchone()
            if row and row[0] > 0:
                cursor.execute("ALTER TABLE `users_user` MODIFY COLUMN `user_type` VARCHAR(50) NULL DEFAULT NULL")
                try:
                    cursor.execute("ALTER TABLE `users_user` DROP COLUMN `user_type`")
                except Exception:
                    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_role_parent_role_user_revoked_permissions_and_more'),
    ]

    operations = [
        migrations.RunPython(
            drop_or_nullify_legacy_user_type,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
