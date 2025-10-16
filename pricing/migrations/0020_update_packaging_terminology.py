# Generated to update packaging terminology from "تغليف" to "تقفيل"

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0019_update_coating_terminology"),
    ]

    operations = [
        # تحديث أوصاف أنواع الورق التي تحتوي على "تغليف"
        migrations.RunSQL(
            """
            UPDATE pricing_papertype 
            SET description = REPLACE(description, 'تغليف', 'تقفيل')
            WHERE description LIKE '%تغليف%';
            """,
            reverse_sql="""
            UPDATE pricing_papertype 
            SET description = REPLACE(description, 'تقفيل', 'تغليف')
            WHERE description LIKE '%تقفيل%';
            """
        ),
        
        # تحديث أوصاف أنواع التغطية التي تحتوي على "تغليف"
        migrations.RunSQL(
            """
            UPDATE pricing_coatingtype 
            SET description = REPLACE(description, 'تغليف', 'تقفيل')
            WHERE description LIKE '%تغليف%';
            """,
            reverse_sql="""
            UPDATE pricing_coatingtype 
            SET description = REPLACE(description, 'تقفيل', 'تغليف')
            WHERE description LIKE '%تقفيل%';
            """
        ),
    ]
