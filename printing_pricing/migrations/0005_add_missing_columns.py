# Generated manually to add missing columns
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('printing_pricing', '0004_create_missing_tables'),
    ]

    operations = [
        # إضافة عمود is_default لجدول PaperSize
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_papersize ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_papersize DROP COLUMN is_default;"
        ),
        
        # إضافة عمود is_default لجداول أخرى إذا لزم الأمر
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_papertype ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_papertype DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_paperweight ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_paperweight DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_paperorigin ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_paperorigin DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_productsize ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_productsize DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_producttype ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_producttype DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_piecesize ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_piecesize DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_coatingtype ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_coatingtype DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_finishingtype ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_finishingtype DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_printdirection ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_printdirection DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_printside ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_printside DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_platesize ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_platesize DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_offsetmachinetype ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_offsetmachinetype DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_offsetsheetsize ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_offsetsheetsize DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_digitalmachinetype ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_digitalmachinetype DROP COLUMN is_default;"
        ),
        
        migrations.RunSQL(
            "ALTER TABLE printing_pricing_digitalsheetsize ADD COLUMN is_default bool DEFAULT 0;",
            reverse_sql="ALTER TABLE printing_pricing_digitalsheetsize DROP COLUMN is_default;"
        ),
    ]
