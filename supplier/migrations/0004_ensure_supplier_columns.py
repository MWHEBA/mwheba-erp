from django.db import migrations

def ensure_columns_and_tables_exist(apps, schema_editor):
    try:
        from django.apps import apps as global_apps
        supplier_models = [
            'SupplierType', 'Supplier', 'SupplierTypeSettings', 'ServiceType', 
            'SupplierService', 'ServicePriceTier', 'ServicePriceHistory', 
            'SupplierTransaction', 'SupplierAdvancePayment', 'SupplierAllocationAudit'
        ]
        with schema_editor.connection.cursor() as cursor:
            for model_name in supplier_models:
                try:
                    model = apps.get_model('supplier', model_name)
                    table_name = model._meta.db_table
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.TABLES 
                        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                    """, [table_name])
                    if cursor.fetchone()[0] == 0:
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
                        existing_cols = {row[0] for row in cursor.fetchall()}
                        for field in model._meta.local_fields:
                            col_name = field.column
                            if col_name and col_name not in existing_cols:
                                try:
                                    schema_editor.add_field(model, field)
                                except Exception:
                                    pass

                    for m2m in model._meta.local_many_to_many:
                        try:
                            m2m_table = m2m.m2m_db_table()
                            cursor.execute("""
                                SELECT COUNT(*) 
                                FROM information_schema.TABLES 
                                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                            """, [m2m_table])
                            if cursor.fetchone()[0] == 0:
                                schema_editor.create_model(m2m.remote_field.through)
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception:
        pass

class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0003_supplier_whatsapp_opt_out_and_more'),
    ]

    operations = [
        migrations.RunPython(ensure_columns_and_tables_exist, migrations.RunPython.noop),
    ]
