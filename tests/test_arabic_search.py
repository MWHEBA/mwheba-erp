import pytest
from django.db.models import Q
from utils.search import (
    normalize_arabic,
    get_canonical_variants,
    build_smart_search_query,
    smart_search_filter,
)
from client.models import Customer
from financial.models.currency import Currency


class TestArabicSearchNormalization:
    """Tests for individual Arabic text normalization features."""

    def test_alif_normalization(self):
        assert normalize_arabic("أحمد") == "احمد"
        assert normalize_arabic("إبراهيم") == "ابراهيم"
        assert normalize_arabic("آفاق") == "افاق"
        assert normalize_arabic("الأفق") == "الافق"

    def test_ta_marbuta_normalization(self):
        assert normalize_arabic("مؤسسة") == "موسسه"
        assert normalize_arabic("مؤسسه") == "موسسه"
        assert normalize_arabic("شركة") == "شركه"

    def test_ya_and_alif_maqsura_normalization(self):
        assert normalize_arabic("علي") == "علي"
        assert normalize_arabic("على") == "علي"
        assert normalize_arabic("مبتدئ") == "مبتدي"

    def test_hamza_waw_normalization(self):
        assert normalize_arabic("مؤسة") == "موسه"
        assert normalize_arabic("مؤسسة") == "موسسه"

    def test_eastern_digits_normalization(self):
        assert normalize_arabic("٠١٠١٢٣٤٥٦٧٨") == "01012345678"
        assert normalize_arabic("فاتورة رقم ٥٠") == "فاتوره رقم 50"

    def test_loanword_and_persian_chars(self):
        assert normalize_arabic("ڤودافون") == "فودافون"
        assert normalize_arabic("شرکة") == "شركه"  # Persian Kaf
        assert normalize_arabic("پيبسي") == "بيبسي"

    def test_diacritics_and_tatweel_stripping(self):
        assert normalize_arabic("مُؤَسَّـسَةٌ") == "موسسه"

    def test_consecutive_repeated_chars(self):
        assert normalize_arabic("مؤسسسة") == "موسه"
        assert normalize_arabic("أفففق") == "افق"


class TestCanonicalVariants:
    """Tests for targeted canonical variant generation."""

    def test_alif_and_definite_article_variants(self):
        variants = get_canonical_variants("افق")
        assert "افق" in variants
        assert "الافق" in variants or "الأفق" in variants or "أفق" in variants

        variants_al = get_canonical_variants("الأفق")
        assert "الافق" in variants_al or "افق" in variants_al or "الأفق" in variants_al

    def test_conjunction_waw_variants(self):
        variants = get_canonical_variants("والافق")
        assert any(v in variants for v in ["افق", "الافق", "الأفق"])

    def test_compound_name_variants(self):
        variants = get_canonical_variants("عبدالرحمن")
        assert "عبد الرحمن" in variants or "عبدالرحمن" in variants


from django.test import TestCase


class TestCustomerSmartSearchIntegration(TestCase):
    """Integration tests with Django ORM Customer model."""

    def setUp(self):
        super().setUp()
        self.currency, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
        )
        # Create test customers
        self.c1 = Customer.objects.create(
            name="مؤسة الأفق للتجارة",
            code="CUST-TEST-001",
            phone="01012345678",
            phone_primary="01012345678",
            default_currency=self.currency
        )
        self.c2 = Customer.objects.create(
            name="أحمد علي إبراهيم",
            company_name="مؤسسة الأفق للبرمجيات",
            contact_person="المهندس عبد الرحمن",
            code="CUST-TEST-002",
            phone="01198765432",
            phone_primary="01198765432",
            tax_number="123456789",
            default_currency=self.currency
        )
        self.c3 = Customer.objects.create(
            name="شركة ڤودافون مصر",
            code="CUST-TEST-003",
            phone="01099998888",
            phone_primary="01099998888",
            default_currency=self.currency
        )

    def test_search_by_plain_word_matches_hamza_and_al(self):
        # Searching 'افق' must find 'مؤسة الأفق للتجارة' and 'مؤسسة الأفق للبرمجيات'
        qs = Customer.objects.all()
        results = smart_search_filter(
            qs,
            "افق",
            text_fields=["name", "company_name", "contact_person"],
            code_fields=["code", "phone"]
        )
        assert results.filter(id=self.c1.id).exists()
        assert results.filter(id=self.c2.id).exists()
        assert not results.filter(id=self.c3.id).exists()

    def test_multi_token_search(self):
        # Searching 'مؤسسة افق' must find both despite 'الـ' separation
        qs = Customer.objects.all()
        results = smart_search_filter(
            qs,
            "مؤسسة افق",
            text_fields=["name", "company_name", "contact_person"],
            code_fields=["code", "phone"]
        )
        assert results.filter(id=self.c1.id).exists()
        assert results.filter(id=self.c2.id).exists()

    def test_search_in_company_name_and_contact_person(self):
        # Searching 'عبدالرحمن' must find c2 where contact_person is 'المهندس عبد الرحمن'
        qs = Customer.objects.all()
        results = smart_search_filter(
            qs,
            "عبدالرحمن",
            text_fields=["name", "company_name", "contact_person"],
            code_fields=["code", "phone"]
        )
        assert results.filter(id=self.c2.id).exists()
        assert not results.filter(id=self.c1.id).exists()

    def test_search_by_eastern_digits_phone(self):
        # Searching with Eastern digits '٠١٠١٢٣٤٥٦٧٨' must find c1 with '01012345678'
        qs = Customer.objects.all()
        results = smart_search_filter(
            qs,
            "٠١٠١٢٣٤٥٦٧٨",
            text_fields=["name", "company_name"],
            code_fields=["code", "phone", "phone_primary"]
        )
        assert results.filter(id=self.c1.id).exists()
        assert not results.filter(id=self.c2.id).exists()

    def test_loanword_vodafone_search(self):
        # Searching 'فودافون' finds 'شركة ڤودافون مصر'
        qs = Customer.objects.all()
        results = smart_search_filter(
            qs,
            "فودافون",
            text_fields=["name", "company_name"],
            code_fields=["code", "phone"]
        )
        assert results.filter(id=self.c3.id).exists()
