import pytest
import json
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import SystemSetting
from core.forms import OperationsSettingsForm, SystemSettingsForm

User = get_user_model()


@pytest.mark.django_db
class TestSettingsArchitecture:
    """
    اختبارات معمارية الإعدادات الثلاثية، المحرك المطور، وتفريغ الكاش
    """

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.superuser = User.objects.create_superuser(
            username="admin_test",
            email="admin@test.com",
            password="Password123!"
        )

    def test_invalidate_all_system_caches(self):
        """اختبار تفريغ كافة الكاشات الموحدة"""
        SystemSetting.set_setting("site_name", "موهبة ERP Test")
        assert SystemSetting.get_setting("site_name") == "موهبة ERP Test"
        
        SystemSetting.invalidate_all_system_caches()
        assert SystemSetting.get_setting("site_name") == "موهبة ERP Test"

    def test_timezone_fallback(self):
        """اختبار دعم get_timezone للمفتاحين بالتبادل"""
        SystemSetting.objects.all().delete()
        SystemSetting.invalidate_all_system_caches()
        
        SystemSetting.objects.create(key="system_timezone", value="Asia/Riyadh", is_active=True)
        SystemSetting.invalidate_all_system_caches()
        assert SystemSetting.get_timezone() == "Asia/Riyadh"

    def test_operations_settings_form_validation(self):
        """اختبار نموذج سياسات التشغيل والفواتير والطباعة"""
        form_data = {
            "sale_invoice_item_types": "both",
            "purchase_invoice_item_types": "products",
            "invoice_product_code_display": "sku",
            "enable_custom_fields": True,
            "custom_fields_display_mode": "expanded",
            "default_quotation_validity_days": 20,
            "default_sale_invoice_notes": "شروط عربية <script>alert(1)</script>",
            "default_sale_invoice_notes_en": "English terms",
            "default_quotation_notes": "شروط عروض عربية",
            "default_quotation_notes_en": "English quote terms",
            "default_print_language": "ar",
            "invoice_title_sale_en": "TAX INVOICE",
            "invoice_title_quotation_en": "QUOTATION",
            "enable_thermal_printing": True,
            "receipt_paper_width": "80",
            "show_foreign_currency_exchange_rate": True,
        }
        form = OperationsSettingsForm(data=form_data)
        assert form.is_valid(), form.errors
        # التأكد من تعقيم وسوم script
        assert "<script>" not in form.cleaned_data["default_sale_invoice_notes"]

    def test_operations_settings_view_get_and_post(self, client):
        """اختبار شاشة سياسات التشغيل GET و POST"""
        client.force_login(self.superuser)
        url = reverse("core:operations_settings")
        
        response = client.get(url)
        assert response.status_code == 200
        assert "سياسات التشغيل" in response.content.decode("utf-8")
        
        post_data = {
            "sale_invoice_item_types": "services",
            "purchase_invoice_item_types": "both",
            "invoice_product_code_display": "both",
            "enable_custom_fields": "on",
            "custom_fields_display_mode": "collapsed",
            "default_quotation_validity_days": 30,
            "default_sale_invoice_notes": "شروط مبيعات معتمدة",
            "default_sale_invoice_notes_en": "Approved terms",
            "default_quotation_notes": "شروط عروض",
            "default_quotation_notes_en": "Quotation terms",
            "default_print_language": "en",
            "invoice_title_sale_en": "COMMERCIAL INVOICE",
            "invoice_title_quotation_en": "PRICE OFFER",
            "enable_thermal_printing": "on",
            "receipt_paper_width": "58",
            "show_foreign_currency_exchange_rate": "on",
            "active_tab": "printing",
        }
        post_res = client.post(url, post_data)
        assert post_res.status_code == 302
        assert "tab=printing" in post_res.url
        
        assert SystemSetting.get_setting("sale_invoice_item_types") == "services"
        assert SystemSetting.get_setting("receipt_paper_width") == "58"
        assert SystemSetting.get_setting("show_foreign_currency_exchange_rate") is True

    def test_system_settings_password_preservation(self, client):
        """اختبار الحفاظ على كلمة المرور القديمة عند إرسال حقل فارغ"""
        from financial.models import Currency
        curr, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "EGP", "is_functional": True, "is_active": True})
        
        client.force_login(self.superuser)
        SystemSetting.objects.create(key="email_password", value="SecretP@ss123", is_active=True)
        SystemSetting.invalidate_all_system_caches()

        url = reverse("core:system_settings")
        post_data = {
            "site_name": "موهبة ERP المحدث",
            "language": "ar",
            "timezone": "Africa/Cairo",
            "date_format": "d/m/Y",
            "time_format": "12",
            "default_currency": curr.id,
            "session_timeout": 45,
            "password_policy": "strong",
            "failed_login_attempts": 4,
            "account_lockout_time": 25,
            "email_host": "smtp.example.com",
            "email_port": 587,
            "email_username": "test_erp@example.com",
            "email_password": "",  # فارغ عمداً
            "email_encryption": "tls",
            "email_from": "test_erp@example.com",
            "active_tab": "integration",
        }
        response = client.post(url, post_data)
        assert response.status_code == 302
        
        # التأكد من بقاء كلمة المرور دون مسح
        assert SystemSetting.get_setting("email_password") == "SecretP@ss123"
        assert SystemSetting.get_setting("site_name") == "موهبة ERP المحدث"

    def test_foreign_currency_invoice_print_setting_toggle(self):
        """اختبار تأثير إعداد إظهار/إخفاء سعر الصرف والمعادل بالجنيه في قوالب الطباعة"""
        from django.template import Context, Template
        
        template_str = """
        {% if sale.currency and not sale.currency.is_functional %}
        {% if settings.show_foreign_currency_exchange_rate %}
        <tr><td>سعر الصرف: {{ sale.exchange_rate }}</td></tr>
        <tr><td>المعادل بالعملة المحلية (ج.م)</td></tr>
        {% endif %}
        {% endif %}
        """
        
        class FakeCurrency:
            code = "USD"
            is_functional = False
            
        class FakeSale:
            currency = FakeCurrency()
            exchange_rate = 50.0
            
        t = Template(template_str)
        
        # 1. مفعل (True)
        ctx_enabled = Context({
            "sale": FakeSale(),
            "settings": {"show_foreign_currency_exchange_rate": True}
        })
        rendered_enabled = t.render(ctx_enabled)
        assert "سعر الصرف" in rendered_enabled
        assert "المعادل بالعملة المحلية" in rendered_enabled
        
        # 2. معطل (False)
        ctx_disabled = Context({
            "sale": FakeSale(),
            "settings": {"show_foreign_currency_exchange_rate": False}
        })
        rendered_disabled = t.render(ctx_disabled)
        assert "سعر الصرف" not in rendered_disabled
        assert "المعادل بالعملة المحلية" not in rendered_disabled

    def test_admin_sidebar_settings_visibility_and_module_management_restriction(self, client):
        """
        التحقق من ظهور الإعدادات لمدير النظام (admin) في القائمة الجانبية
        مع حجب تطبيقات النظام (module_management) عنه وقصرها على superuser
        """
        from users.models import Role
        from django.template.loader import render_to_string
        
        admin_role, _ = Role.objects.get_or_create(
            name="admin",
            defaults={"display_name": "مدير النظام", "is_system_role": True}
        )
        admin_user = User.objects.create_user(
            username="system_admin_no_super",
            email="sysadmin@example.com",
            password="Password123!",
            role=admin_role,
            is_staff=True,
            is_superuser=False
        )

        assert admin_user.is_admin is True
        assert admin_user.is_superuser is False

        from django.test import RequestFactory
        rf = RequestFactory()

        # 1. فحص القالب الجانبي لمدير النظام
        req_admin = rf.get("/")
        req_admin.user = admin_user
        rendered_admin = render_to_string("partials/sidebar.html", {"user": admin_user, "request": req_admin})
        assert "إعدادات المنشـأة" in rendered_admin
        assert "سياسات التشغيل" in rendered_admin
        assert "إعدادات النظام" in rendered_admin
        assert "إدارة النسخ الاحتياطية" in rendered_admin
        # تطبيقات النظام محجوبة عن مدير النظام
        assert "تطبيقات النظام" not in rendered_admin

        # 2. فحص القالب الجانبي للمدير العام (Superuser)
        req_super = rf.get("/")
        req_super.user = self.superuser
        rendered_super = render_to_string("partials/sidebar.html", {"user": self.superuser, "request": req_super})
        assert "إعدادات المنشـأة" in rendered_super
        assert "تطبيقات النظام" in rendered_super

        # 3. محاولة الدخول المباشر لرابط تطبيقات النظام بواسطة مدير النظام
        client.force_login(admin_user)
        mod_res = client.get(reverse("core:module_management"))
        assert mod_res.status_code == 302  # تم الحظر وإعادة التوجيه

        # 4. دخول المدير العام للرابط
        client.force_login(self.superuser)
        mod_super_res = client.get(reverse("core:module_management"))
        assert mod_super_res.status_code == 200

