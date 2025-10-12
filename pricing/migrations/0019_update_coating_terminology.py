# Generated to update coating terminology from "تغليف" to "تغطية"

from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0018_update_paper_size_to_product_size'),
    ]

    operations = [
        # هذا Migration يوثق تحديث المصطلحات من "تغليف" إلى "تغطية"
        # التغييرات تمت في:
        # 1. pricing/models.py - verbose_name و verbose_name_plural
        # 2. pricing/views.py - التوثيق والتعليقات
        # 3. templates - النصوص العربية
        # 4. JavaScript - التعليقات العربية
        # 5. supplier/models.py - خيارات الخدمات
        
        # لا توجد تغييرات في بنية قاعدة البيانات
        # جميع التغييرات في النصوص والواجهات فقط
    ]
