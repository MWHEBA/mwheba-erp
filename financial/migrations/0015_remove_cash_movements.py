# Generated manually to remove cash movements system

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0013_add_notes_to_journal_entry'),
        ('purchase', '0008_remove_purchasepayment_cash_movement'),
        ('sale', '0007_remove_salepayment_cash_movement_and_more'),
    ]

    operations = [
        # استخدام SeparateDatabaseAndState لحذف الجداول مباشرة
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # حذف الحقول المرتبطة من الـ state
                migrations.RemoveField(
                    model_name='cashmovement',
                    name='account',
                ),
                migrations.RemoveField(
                    model_name='cashmovement',
                    name='approved_by',
                ),
                migrations.RemoveField(
                    model_name='cashmovement',
                    name='created_by',
                ),
                migrations.RemoveField(
                    model_name='cashmovement',
                    name='executed_by',
                ),
                migrations.RemoveField(
                    model_name='cashmovement',
                    name='journal_entry',
                ),
                migrations.RemoveField(
                    model_name='cashmovement',
                    name='movement_type',
                ),
                migrations.RemoveField(
                    model_name='cashmovementattachment',
                    name='movement',
                ),
                migrations.RemoveField(
                    model_name='cashmovementattachment',
                    name='uploaded_by',
                ),
                migrations.RemoveField(
                    model_name='cashmovementtype',
                    name='created_by',
                ),
                # حذف النماذج من الـ state
                migrations.DeleteModel(
                    name='CashBalance',
                ),
                migrations.DeleteModel(
                    name='CashMovement',
                ),
                migrations.DeleteModel(
                    name='CashMovementAttachment',
                ),
                migrations.DeleteModel(
                    name='CashMovementType',
                ),
            ],
            database_operations=[
                # حذف الجداول مباشرة من قاعدة البيانات
                migrations.RunSQL(
                    sql="""
                        DROP TABLE IF EXISTS financial_cashmovementattachment;
                        DROP TABLE IF EXISTS financial_cashmovement;
                        DROP TABLE IF EXISTS financial_cashbalance;
                        DROP TABLE IF EXISTS financial_cashmovementtype;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
