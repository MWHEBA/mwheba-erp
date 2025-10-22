# Generated manually for partner settings

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0016_add_audit_trail_model'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PartnerSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_daily_contribution', models.DecimalField(decimal_places=2, default=Decimal('100000'), help_text='الحد الأقصى للمبلغ الذي يمكن للشريك المساهمة به في اليوم الواحد', max_digits=12, verbose_name='الحد الأقصى للمساهمة اليومية')),
                ('max_daily_withdrawal', models.DecimalField(decimal_places=2, default=Decimal('50000'), help_text='الحد الأقصى للمبلغ الذي يمكن للشريك سحبه في اليوم الواحد', max_digits=12, verbose_name='الحد الأقصى للسحب اليومي')),
                ('max_monthly_withdrawal', models.DecimalField(decimal_places=2, default=Decimal('200000'), help_text='الحد الأقصى للمبلغ الذي يمكن للشريك سحبه في الشهر الواحد', max_digits=12, verbose_name='الحد الأقصى للسحب الشهري')),
                ('min_balance_threshold', models.DecimalField(decimal_places=2, default=Decimal('0'), help_text='الحد الأدنى الذي يجب أن يبقى في رصيد الشريك', max_digits=12, verbose_name='الحد الأدنى للرصيد')),
                ('auto_approve_contributions', models.BooleanField(default=True, help_text='هل تتم الموافقة على المساهمات تلقائياً؟', verbose_name='موافقة تلقائية على المساهمات')),
                ('auto_approve_withdrawals', models.BooleanField(default=True, help_text='هل تتم الموافقة على السحوبات تلقائياً؟', verbose_name='موافقة تلقائية على السحوبات')),
                ('approval_required_amount', models.DecimalField(decimal_places=2, default=Decimal('10000'), help_text='المبلغ الذي يتطلب موافقة يدوية', max_digits=12, verbose_name='مبلغ يتطلب موافقة')),
                ('notify_on_contribution', models.BooleanField(default=True, verbose_name='إشعار عند المساهمة')),
                ('notify_on_withdrawal', models.BooleanField(default=True, verbose_name='إشعار عند السحب')),
                ('notify_on_low_balance', models.BooleanField(default=True, verbose_name='إشعار عند انخفاض الرصيد')),
                ('low_balance_threshold', models.DecimalField(decimal_places=2, default=Decimal('5000'), help_text='الحد الذي يتم إرسال إشعار عنده لانخفاض الرصيد', max_digits=12, verbose_name='حد الرصيد المنخفض')),
                ('monthly_report_enabled', models.BooleanField(default=True, verbose_name='تقرير شهري مفعل')),
                ('weekly_report_enabled', models.BooleanField(default=False, verbose_name='تقرير أسبوعي مفعل')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='حُدث بواسطة')),
            ],
            options={
                'verbose_name': 'إعدادات الشراكة',
                'verbose_name_plural': 'إعدادات الشراكة',
            },
        ),
        migrations.CreateModel(
            name='PartnerPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission_type', models.CharField(choices=[('view_dashboard', 'عرض لوحة التحكم'), ('create_contribution', 'إنشاء مساهمة'), ('create_withdrawal', 'إنشاء سحب'), ('view_transactions', 'عرض المعاملات'), ('view_balance', 'عرض الرصيد'), ('approve_transactions', 'الموافقة على المعاملات'), ('cancel_transactions', 'إلغاء المعاملات'), ('view_reports', 'عرض التقارير'), ('manage_settings', 'إدارة الإعدادات')], max_length=50, verbose_name='نوع الصلاحية')),
                ('granted_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ المنح')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
                ('granted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='granted_partner_permissions', to=settings.AUTH_USER_MODEL, verbose_name='منح بواسطة')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='partner_permissions', to=settings.AUTH_USER_MODEL, verbose_name='المستخدم')),
            ],
            options={
                'verbose_name': 'صلاحية الشريك',
                'verbose_name_plural': 'صلاحيات الشركاء',
            },
        ),
        migrations.CreateModel(
            name='PartnerAuditLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create_contribution', 'إنشاء مساهمة'), ('create_withdrawal', 'إنشاء سحب'), ('approve_transaction', 'الموافقة على معاملة'), ('cancel_transaction', 'إلغاء معاملة'), ('update_settings', 'تحديث الإعدادات'), ('grant_permission', 'منح صلاحية'), ('revoke_permission', 'إلغاء صلاحية'), ('view_dashboard', 'عرض لوحة التحكم'), ('view_reports', 'عرض التقارير')], max_length=50, verbose_name='الإجراء')),
                ('description', models.TextField(help_text='وصف تفصيلي للإجراء المنفذ', verbose_name='الوصف')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='عنوان IP')),
                ('user_agent', models.TextField(blank=True, null=True, verbose_name='معلومات المتصفح')),
                ('extra_data', models.JSONField(blank=True, help_text='بيانات إضافية متعلقة بالإجراء', null=True, verbose_name='بيانات إضافية')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='الوقت')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='partner_audit_logs', to=settings.AUTH_USER_MODEL, verbose_name='المستخدم')),
            ],
            options={
                'verbose_name': 'سجل تدقيق الشريك',
                'verbose_name_plural': 'سجلات تدقيق الشريك',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddConstraint(
            model_name='partnerpermission',
            constraint=models.UniqueConstraint(fields=('user', 'permission_type'), name='unique_user_permission'),
        ),
        migrations.AddIndex(
            model_name='partnerpermission',
            index=models.Index(fields=['user', 'permission_type', 'is_active'], name='financial_p_user_id_a8b9a8e_idx'),
        ),
        migrations.AddIndex(
            model_name='partnerauditlog',
            index=models.Index(fields=['user', 'action', 'timestamp'], name='financial_p_user_id_b8b9a8e_idx'),
        ),
        migrations.AddIndex(
            model_name='partnerauditlog',
            index=models.Index(fields=['action', 'timestamp'], name='financial_p_action_c8b9a8e_idx'),
        ),
    ]
