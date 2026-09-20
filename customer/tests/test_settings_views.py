"""اختبارات نظام إعدادات العملاء والشرائح التجارية وشروط السداد وسياسات الائتمان"""
from decimal import Decimal
import json
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.management import call_command

from customer.models import Customer, CustomerTier, PaymentTerm, CustomerGeneralSettings
from customer.forms import CustomerForm
from customer.forms_settings.customer_tier_forms import CustomerTierForm
from customer.forms_settings.payment_term_forms import PaymentTermForm
from customer.forms_settings.general_settings_forms import CustomerGeneralSettingsForm

User = get_user_model()


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        username="admin_test",
        email="admin@example.com",
        password="password123",
    )
    return user


@pytest.fixture
def sample_payment_terms(db):
    t1 = PaymentTerm.objects.create(
        name="سداد فوري",
        days=0,
        is_default=True,
        is_active=True,
    )
    t2 = PaymentTerm.objects.create(
        name="آجل 30 يوم",
        days=30,
        is_default=False,
        is_active=True,
    )
    return t1, t2


@pytest.fixture
def sample_tier(db, sample_payment_terms):
    t1, _ = sample_payment_terms
    return CustomerTier.objects.create(
        name="شركات كبرى",
        code="CORP",
        display_order=1,
        default_payment_term=t1,
        default_credit_limit=Decimal("50000.00"),
        default_risk_category="low",
        discount_percentage=Decimal("5.00"),
        is_active=True,
        is_system=False,
    )


@pytest.mark.django_db
class TestCustomerSettingsModels:
    """اختبار نماذج وقواعد أعمال إعدادات العملاء"""

    def test_payment_term_single_default(self):
        term1 = PaymentTerm.objects.create(name="Term 1", days=10, is_default=True)
        term2 = PaymentTerm.objects.create(name="Term 2", days=20, is_default=True)
        
        term1.refresh_from_db()
        term2.refresh_from_db()
        
        assert term2.is_default is True
        assert term1.is_default is False

    def test_customer_tier_creation_and_ordering(self, sample_payment_terms):
        t1, _ = sample_payment_terms
        tier1 = CustomerTier.objects.create(name="Tier A", code="TA", display_order=2)
        tier2 = CustomerTier.objects.create(name="Tier B", code="TB", display_order=1)

        tiers = list(CustomerTier.objects.filter(code__in=["TA", "TB"]).order_by("display_order"))
        assert tiers[0].code == "TB"
        assert tiers[1].code == "TA"

    def test_customer_general_settings_singleton(self):
        s1 = CustomerGeneralSettings.get_settings()
        s1.code_prefix = "TEST-"
        s1.code_digits = 5
        s1.save()

        s2 = CustomerGeneralSettings.get_settings()
        assert s2.code_prefix == "TEST-"
        assert s2.code_digits == 5
        assert CustomerGeneralSettings.objects.count() == 1

    def test_customer_tier_deletion_nullifies_customer_tier(self, sample_tier):
        cust = Customer.objects.create(
            name="عميل تجريبي",
            code="CUST-001",
            tier=sample_tier,
            customer_type="individual",
        )
        assert cust.tier == sample_tier

        sample_tier.delete()
        cust.refresh_from_db()
        assert cust.tier is None


@pytest.mark.django_db
class TestCustomerSettingsViews:
    """اختبار عروض وواجهات إعدادات العملاء (Views & Modals)"""

    def test_settings_index_view(self, client, admin_user, sample_tier):
        client.force_login(admin_user)
        url = reverse("customer:settings_index")
        response = client.get(url)
        assert response.status_code == 200
        assert "tiers" in response.context
        assert "payment_terms" in response.context
        assert "general_settings_form" in response.context

    def test_tier_create_and_edit_ajax(self, client, admin_user):
        client.force_login(admin_user)
        create_url = reverse("customer:tier_create")
        post_data = {
            "name": "وكالات جديدة",
            "code": "NEW_AGENCY",
            "display_order": 3,
            "description": "شريحة تجريبية",
            "discount_percentage": "12.50",
            "default_credit_limit": "25000.00",
            "default_risk_category": "medium",
            "is_active": "on",
        }
        response = client.post(create_url, data=post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 200
        res_json = response.json()
        assert res_json["success"] is True

        tier = CustomerTier.objects.get(code="NEW_AGENCY")
        assert tier.discount_percentage == Decimal("12.50")

        # Test Edit GET
        edit_url = reverse("customer:tier_edit", kwargs={"pk": tier.pk})
        edit_get_response = client.get(edit_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert edit_get_response.status_code == 200
        assert edit_get_response.json()["data"]["name"] == "وكالات جديدة"

        # Test Edit POST
        post_data["name"] = "وكالات محدثة"
        edit_post_response = client.post(edit_url, data=post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert edit_post_response.status_code == 200
        tier.refresh_from_db()
        assert tier.name == "وكالات محدثة"

    def test_tier_toggle_status(self, client, admin_user, sample_tier):
        client.force_login(admin_user)
        url = reverse("customer:tier_toggle_status", kwargs={"pk": sample_tier.pk})
        response = client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 200
        sample_tier.refresh_from_db()
        assert sample_tier.is_active is False

    def test_api_customer_tier_info(self, client, admin_user, sample_tier):
        client.force_login(admin_user)
        url = reverse("customer:api_tier_info", kwargs={"pk": sample_tier.pk})
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["tier"]["code"] == "CORP"
        assert data["tier"]["default_risk_category"] == "low"

    def test_payment_term_quick_add(self, client, admin_user):
        client.force_login(admin_user)
        url = reverse("customer:payment_term_quick_add")
        response = client.post(url, data={"name": "سريع 45 يوم", "days": 45}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 200
        res_json = response.json()
        assert res_json["success"] is True
        assert res_json["term"]["days"] == 45
        assert PaymentTerm.objects.filter(name="سريع 45 يوم").exists()

    def test_general_settings_update(self, client, admin_user):
        client.force_login(admin_user)
        url = reverse("customer:general_settings")
        post_data = {
            "code_prefix": "VIP-",
            "code_digits": 6,
            "default_credit_limit": "1000.00",
            "default_grace_period_days": 7,
            "credit_limit_enforcement": "HARD_STOP",
        }
        response = client.post(url, data=post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 200
        settings = CustomerGeneralSettings.get_settings()
        assert settings.code_prefix == "VIP-"
        assert settings.code_digits == 6
        assert settings.credit_limit_enforcement == "HARD_STOP"


    def test_seed_customer_settings_command(self, db):
        call_command("seed_customer_settings")
        assert CustomerTier.objects.count() >= 5
        assert PaymentTerm.objects.count() >= 6
        assert CustomerTier.objects.filter(code="B2B_CORP").exists()
        assert CustomerTier.objects.filter(code="B2C_RETAIL").exists()
