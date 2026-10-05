from django.db import migrations

def ensure_pricing_tables_exist(apps, schema_editor):
    model_names = [
        'OffsetMachineType',
        'DigitalMachineType',
        'OffsetSheetSize',
        'DigitalSheetSize',
        'PlateSize',
        'PrintingMachine',
        'MachineDimension',
        'PaperType',
        'PaperSize',
        'PaperWeight',
        'PaperOrigin',
        'PieceSize',
        'CoatingType',
        'FinishingType',
        'PackagingType',
        'ProductType',
        'ProductSize',
        'PrintingOrder',
        'PaperSpecification',
        'OrderMaterial',
        'OrderService',
        'CostCalculation',
        'OrderSummary',
    ]
    with schema_editor.connection.cursor() as cursor:
        for model_name in model_names:
            try:
                model = apps.get_model('printing_pricing', model_name)
                table_name = model._meta.db_table
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = DATABASE() 
                      AND TABLE_NAME = %s
                """, [table_name])
                row = cursor.fetchone()
                if row and row[0] == 0:
                    try:
                        schema_editor.create_model(model)
                    except Exception:
                        pass
                else:
                    cursor.execute("""
                        SELECT COLUMN_NAME 
                        FROM information_schema.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                    """, [table_name])
                    existing_cols = {r[0] for r in cursor.fetchall()}
                    for field in model._meta.local_fields:
                        col_name = field.column
                        if col_name and col_name not in existing_cols:
                            try:
                                schema_editor.add_field(model, field)
                            except Exception:
                                pass
            except Exception:
                pass

class Migration(migrations.Migration):

    dependencies = [
        ('printing_pricing', '0004_alter_printingorder_options'),
    ]

    operations = [
        migrations.RunPython(ensure_pricing_tables_exist, migrations.RunPython.noop),
    ]
