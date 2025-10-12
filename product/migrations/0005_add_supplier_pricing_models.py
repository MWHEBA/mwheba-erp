# Generated manually for supplier pricing models

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("supplier", "0004_supplier_financial_account"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("product", "0003_stockmovement_journal_entry"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="default_supplier",
            field=models.ForeignKey(
                blank=True,
                help_text="المورد الافتراضي لهذا المنتج",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="default_products",
                to="supplier.supplier",
                verbose_name="المورد الافتراضي",
            ),
        ),
        migrations.CreateModel(
            name="SupplierProductPrice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "cost_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                        verbose_name="سعر التكلفة",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="هل هذا هو المورد الافتراضي لهذا المنتج؟",
                        verbose_name="المورد الافتراضي",
                    ),
                ),
                (
                    "last_purchase_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="تاريخ آخر شراء"
                    ),
                ),
                (
                    "last_purchase_quantity",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="كمية آخر شراء"
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, null=True, verbose_name="ملاحظات"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ الإنشاء"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supplier_prices_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشئ بواسطة",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supplier_prices",
                        to="product.product",
                        verbose_name="المنتج",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_prices",
                        to="supplier.supplier",
                        verbose_name="المورد",
                    ),
                ),
            ],
            options={
                "verbose_name": "سعر المنتج للمورد",
                "verbose_name_plural": "أسعار المنتجات للموردين",
                "ordering": ["-is_default", "-last_purchase_date", "supplier__name"],
            },
        ),
        migrations.CreateModel(
            name="PriceHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "old_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="السعر القديم",
                    ),
                ),
                (
                    "new_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                        verbose_name="السعر الجديد",
                    ),
                ),
                (
                    "change_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="مقدار التغيير",
                    ),
                ),
                (
                    "change_percentage",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=8,
                        null=True,
                        verbose_name="نسبة التغيير",
                    ),
                ),
                (
                    "change_reason",
                    models.CharField(
                        choices=[
                            ("purchase", "شراء جديد"),
                            ("manual_update", "تحديث يدوي"),
                            ("supplier_notification", "إشعار من المورد"),
                            ("market_change", "تغيير السوق"),
                            ("bulk_update", "تحديث جماعي"),
                            ("system_sync", "مزامنة النظام"),
                        ],
                        default="manual_update",
                        max_length=30,
                        verbose_name="سبب التغيير",
                    ),
                ),
                (
                    "purchase_reference",
                    models.CharField(
                        blank=True,
                        help_text="رقم فاتورة الشراء إذا كان التغيير بسبب شراء جديد",
                        max_length=50,
                        null=True,
                        verbose_name="مرجع الشراء",
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, null=True, verbose_name="ملاحظات"),
                ),
                (
                    "change_date",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="تاريخ التغيير"
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="price_changes_made",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="غُير بواسطة",
                    ),
                ),
                (
                    "supplier_product_price",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_history",
                        to="product.supplierproductprice",
                        verbose_name="سعر المنتج للمورد",
                    ),
                ),
            ],
            options={
                "verbose_name": "تاريخ تغيير السعر",
                "verbose_name_plural": "تاريخ تغيير الأسعار",
                "ordering": ["-change_date"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="supplierproductprice",
            unique_together={("product", "supplier")},
        ),
        migrations.AddIndex(
            model_name="supplierproductprice",
            index=models.Index(
                fields=["product", "supplier"], name="product_sup_product_b7a8a6_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="supplierproductprice",
            index=models.Index(
                fields=["product", "is_default"], name="product_sup_product_f8c9d2_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="supplierproductprice",
            index=models.Index(
                fields=["is_active"], name="product_sup_is_acti_e3b4f1_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="pricehistory",
            index=models.Index(
                fields=["supplier_product_price", "-change_date"],
                name="product_pri_supplie_a2c5e8_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="pricehistory",
            index=models.Index(
                fields=["change_reason"], name="product_pri_change__d7f9b3_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="pricehistory",
            index=models.Index(
                fields=["change_date"], name="product_pri_change__e8a4c6_idx"
            ),
        ),
    ]
