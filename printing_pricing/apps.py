from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PrintingPricingConfig(AppConfig):
    """
    إعدادات وحدة التسعير الجديدة
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'printing_pricing'
    verbose_name = _('تسعير المطبوعات والخدمات الإعلانية')
    
    def ready(self):
        """
        تهيئة الوحدة عند بدء التشغيل وربط إشارة ترحيل قاعدة البيانات
        """
        from django.db.models.signals import post_migrate

        def on_post_migrate(sender, **kwargs):
            try:
                from core.models import SystemModule
                if SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists():
                    from printing_pricing.services.pricing_lookup_seeder_service import PricingLookupSeederService
                    from printing_pricing.services.supplier_seeder_service import PricingSupplierSeederService
                    PricingLookupSeederService.seed_all()
                    PricingSupplierSeederService.seed_all()
            except Exception:
                pass

        # Auto-heal: التحقق التلقائي والشامل من وجود جداول وأعمدة التسعير
        try:
            import sys
            from django.db import connection
            if 'migrate' not in sys.argv and 'test' not in sys.argv:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT DATABASE()")
                        db_name = cursor.fetchone()
                        if db_name and db_name[0]:
                            with connection.schema_editor() as schema_editor:
                                for model in self.get_models():
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

        post_migrate.connect(on_post_migrate, sender=self)
