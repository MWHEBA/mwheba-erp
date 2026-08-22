import uuid
from decimal import Decimal
from datetime import date
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.fiscal_year import FiscalYear
from financial.models.currency import Currency
from financial.services.opening_balance_balancing_service import SmartBalancingService
from financial.services.opening_balance_service import OpeningBalancePostingService

User = get_user_model()


@pytest.fixture
def setup_smart_balancing_env(db):
    uid = uuid.uuid4().hex[:6]
    user = User.objects.create_user(
        username=f"user_{uid}",
        email=f"user_{uid}@example.com",
        password="password123"
    )

    curr_egp, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
    )
    curr_usd, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "symbol": "$", "is_functional": False}
    )

    fy, _ = FiscalYear.objects.get_or_create(
        year_code=f"FY{uid}",
        defaults={
            "name": f"السنة المالية {uid}",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open"
        }
    )

    acc_type_asset, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "أصول", "category": "asset"})
    acc_type_liab, _ = AccountType.objects.get_or_create(code="LIAB", defaults={"name": "خصوم", "category": "liability"})
    acc_type_equity, _ = AccountType.objects.get_or_create(code="EQUITY", defaults={"name": "حقوق ملكية", "category": "equity"})

    # Accounts
    bank_acc = ChartOfAccounts.objects.create(
        code=f"111_{uid}",
        name="البنك الرئيسي",
        account_type=acc_type_asset,
        is_leaf=True,
        is_active=True
    )
    vendor_acc = ChartOfAccounts.objects.create(
        code=f"211_{uid}",
        name="الموردين العام",
        account_type=acc_type_liab,
        is_leaf=True,
        is_active=True
    )
    capital_acc = ChartOfAccounts.objects.create(
        code=f"30100_{uid}",
        name="رأس المال المدفوع",
        account_type=acc_type_equity,
        is_leaf=True,
        is_active=True
    )
    retained_acc = ChartOfAccounts.objects.create(
        code=f"30300_{uid}",
        name="الأرباح المبقاة",
        account_type=acc_type_equity,
        is_leaf=True,
        is_active=True
    )
    losses_acc = ChartOfAccounts.objects.create(
        code=f"30400_{uid}",
        name="الخسائر المرحلة",
        account_type=acc_type_equity,
        is_leaf=True,
        is_active=True
    )
    suspense_acc = ChartOfAccounts.objects.create(
        code=f"30900_{uid}",
        name="حساب وسيط الأرصدة الافتتاحية",
        account_type=acc_type_equity,
        is_leaf=True,
        is_active=True
    )
    partner_acc1 = ChartOfAccounts.objects.create(
        code=f"30201_{uid}",
        name="جاري الشريك أحمد",
        account_type=acc_type_equity,
        is_leaf=True,
        is_active=True
    )
    partner_acc2 = ChartOfAccounts.objects.create(
        code=f"30202_{uid}",
        name="جاري الشريك محمود",
        account_type=acc_type_equity,
        is_leaf=True,
        is_active=True
    )

    batch = OpeningBalanceBatch.objects.create(
        batch_number=f"OPN-{uid}",
        fiscal_year=fy,
        opening_date=date(2026, 1, 1),
        description="دفعة اختبار الموازنة الذكية",
        status="draft",
        created_by=user
    )

    return {
        "user": user,
        "batch": batch,
        "bank_acc": bank_acc,
        "vendor_acc": vendor_acc,
        "capital_acc": capital_acc,
        "retained_acc": retained_acc,
        "losses_acc": losses_acc,
        "suspense_acc": suspense_acc,
        "partner_acc1": partner_acc1,
        "partner_acc2": partner_acc2,
        "curr_egp": curr_egp,
        "curr_usd": curr_usd,
    }


@pytest.mark.django_db
def test_smart_balancing_analysis_credit_needed_and_dual_keys(setup_smart_balancing_env):
    """اختبار تحليل الفارق المالي وتوافقية المفاتيح المزدوجة (abs_diff و abs_difference و description و desc)"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    # إضافة سطر مدين في البنك = 1,000,000 وسطر دائن للموردين = 200,000 (فارق 800,000 يحتاج دائن)
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("1000000.00"),
        credit=Decimal("0.00")
    )
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["vendor_acc"],
        line_type="GL",
        debit=Decimal("0.00"),
        credit=Decimal("200000.00")
    )

    analysis = SmartBalancingService.get_balancing_analysis(batch)
    assert analysis["is_balanced"] is False
    assert analysis["direction"] == "CREDIT_NEEDED"
    assert Decimal(str(analysis["abs_diff"])) == Decimal("800000.00")
    assert Decimal(str(analysis["abs_difference"])) == Decimal("800000.00")
    assert len(analysis["scenarios"]) >= 2

    # التحقق من أن المفاتيح المزدوجة والأثر المحاسبي موجودان في كل سيناريو
    for sc in analysis["scenarios"]:
        assert "description" in sc
        assert "desc" in sc
        assert "consequences" in sc
        assert sc["description"] == sc["desc"]

    keys = [s["key"] for s in analysis["scenarios"]]
    assert "CAPITAL" in keys
    assert "RETAINED_EARNINGS" in keys


@pytest.mark.django_db
def test_smart_balancing_single_apply_capital(setup_smart_balancing_env):
    """اختبار الموازنة الكاملة 100% برأس المال وتصفير الفارق وترحيل الدفعة"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("500000.00"),
        credit=Decimal("0.00")
    )

    result = SmartBalancingService.apply_balancing(
        batch=batch,
        mode="SINGLE",
        data={"account_id": env["capital_acc"].id, "action_type": "AUTO"},
        user=env["user"]
    )

    assert result["success"] is True
    assert result["is_balanced"] is True
    assert Decimal(str(result["balance_diff"])) == Decimal("0.00")

    # التحقق من سطر حقوق الملكية
    eq_line = batch.lines.filter(account=env["capital_acc"]).first()
    assert eq_line is not None
    assert eq_line.line_type == "EQUITY"
    assert eq_line.credit == Decimal("500000.00")

    # اختبار الترحيل المحاسبي
    posted_batch = OpeningBalancePostingService.post(batch.id, env["user"])
    assert posted_batch.status == "posted"
    assert posted_batch.journal_entry is not None


@pytest.mark.django_db
def test_smart_balancing_algebraic_netting_prevents_mutual_exclusivity_error(setup_smart_balancing_env):
    """اختبار الترصيد الصافي الجبري (Algebraic Netting) عند وجود سطر سابق مدين وتحويله لدائن دون كسر قاعدة التنافي"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    # سطر بنك مدين 100,000 وسطر رأس مال مدين 10,000 (إجمالي المدين 110,000 والفارق 110,000 دائن مطلوب)
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("100000.00"),
        credit=Decimal("0.00")
    )
    cap_line = OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["capital_acc"],
        line_type="EQUITY",
        debit=Decimal("10000.00"),
        credit=Decimal("0.00")
    )

    # تطبيق الموازنة على حساب رأس المال
    result = SmartBalancingService.apply_balancing(
        batch=batch,
        mode="SINGLE",
        data={"account_id": env["capital_acc"].id},
        user=env["user"]
    )

    assert result["success"] is True
    assert result["is_balanced"] is True

    # يجب أن يصبح السطر دائناً بصافي 100,000 فقط ومدينه 0.00 دون أي خطأ تحقق
    cap_line.refresh_from_db()
    assert cap_line.debit == Decimal("0.00")
    assert cap_line.credit == Decimal("100000.00")


@pytest.mark.django_db
def test_smart_balancing_zero_netting_deletes_line(setup_smart_balancing_env):
    """اختبار حذف السطر تلقائياً إذا أدى الترصيد الصافي إلى الصفر تماماً"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    # سطر بنك مدين 50,000 وسطر موردين دائن 50,000 (الدفعة متزنة أساساً)
    # لنفترض وجود سطر رأس مال سابق بقيمة 10,000 دائن وسطح بنك 60,000 مدين
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("50000.00"),
        credit=Decimal("0.00")
    )
    # موردين دائن بـ 60,000 ورأس مال دائن بـ 10,000 -> المدين 50,000 والدائن 70,000 (نحتاج مدين بـ 20,000)
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["vendor_acc"],
        line_type="GL",
        debit=Decimal("0.00"),
        credit=Decimal("60000.00")
    )
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["capital_acc"],
        line_type="EQUITY",
        debit=Decimal("0.00"),
        credit=Decimal("10000.00")
    )

    # لو وازنا 10,000 على رأس المال كمدين، يجب أن يتصفر رأس المال ويحذف
    # لنطبق دالة الترصيد مباشرة لاختبار التصفير:
    SmartBalancingService._apply_netted_line(
        batch=batch,
        account=env["capital_acc"],
        needed_debit=Decimal("10000.00"),
        needed_credit=Decimal("0.00")
    )

    assert batch.lines.filter(account=env["capital_acc"]).count() == 0


@pytest.mark.django_db
def test_smart_balancing_split_apply(setup_smart_balancing_env):
    """اختبار التوزيع المزدوج (Split Balancing) رأس مال + أرباح مبقاة معاً"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("1000000.00"),
        credit=Decimal("0.00")
    )

    # تقسيم: 300,000 رأس مال و 700,000 أرباح مبقاة
    result = SmartBalancingService.apply_balancing(
        batch=batch,
        mode="SPLIT",
        data={
            "capital_account_id": env["capital_acc"].id,
            "retained_account_id": env["retained_acc"].id,
            "capital_amount": "300000.00"
        },
        user=env["user"]
    )

    assert result["success"] is True
    assert result["is_balanced"] is True

    cap_line = batch.lines.filter(account=env["capital_acc"]).first()
    ret_line = batch.lines.filter(account=env["retained_acc"]).first()

    assert cap_line.credit == Decimal("300000.00")
    assert ret_line.credit == Decimal("700000.00")


@pytest.mark.django_db
def test_smart_balancing_split_rejects_duplicate_account(setup_smart_balancing_env):
    """اختبار رفض اختيار نفس الحساب لرأس المال والأرباح المبقاة في نمط Split"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("100000.00"),
        credit=Decimal("0.00")
    )

    with pytest.raises(ValidationError, match="لا يمكن اختيار نفس الحساب"):
        SmartBalancingService.apply_balancing(
            batch=batch,
            mode="SPLIT",
            data={
                "capital_account_id": env["capital_acc"].id,
                "retained_account_id": env["capital_acc"].id,
                "capital_amount": "50000.00"
            },
            user=env["user"]
        )


@pytest.mark.django_db
def test_smart_balancing_multi_partner_selection(setup_smart_balancing_env):
    """اختبار سيناريو اختيار شريك محدد عند تعدد الشركاء في الدليل"""
    env = setup_smart_balancing_env
    batch = env["batch"]

    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("250000.00"),
        credit=Decimal("0.00")
    )

    analysis = SmartBalancingService.get_balancing_analysis(batch)
    partner_scenario = next((s for s in analysis["scenarios"] if s.get("is_partner_selector")), None)
    assert partner_scenario is not None
    assert len(partner_scenario["partner_accounts"]) >= 2

    # تطبيق الموازنة على الشريك الثاني تحديداً
    result = SmartBalancingService.apply_balancing(
        batch=batch,
        mode="SINGLE",
        data={"account_id": env["partner_acc2"].id},
        user=env["user"]
    )

    assert result["success"] is True
    p2_line = batch.lines.filter(account=env["partner_acc2"]).first()
    assert p2_line is not None
    assert p2_line.credit == Decimal("250000.00")


@pytest.mark.django_db
def test_smart_balancing_ajax_endpoints(client, setup_smart_balancing_env):
    """اختبار استدعاء نقاط الـ AJAX لجلب خيارات الموازنة وتطبيقها والتحديث التفاعلي"""
    env = setup_smart_balancing_env
    batch = env["batch"]
    client.force_login(env["user"])

    OpeningBalanceLine.objects.create(
        batch=batch,
        account=env["bank_acc"],
        line_type="GL",
        debit=Decimal("150000.00"),
        credit=Decimal("0.00")
    )

    # 1. GET balancing-options
    url_get = reverse("financial:opening_balance_get_balancing_options", kwargs={"pk": batch.pk})
    resp_get = client.get(url_get)
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert data_get["success"] is True
    assert data_get["data"]["abs_diff"] == 150000.0
    assert data_get["data"]["abs_difference"] == 150000.0

    # 2. POST apply-balancing
    url_apply = reverse("financial:opening_balance_apply_balancing_action", kwargs={"pk": batch.pk})
    resp_apply = client.post(
        url_apply,
        data={"mode": "SINGLE", "data": {"account_id": env["capital_acc"].id}},
        content_type="application/json"
    )
    assert resp_apply.status_code == 200
    data_apply = resp_apply.json()
    assert data_apply["success"] is True
    assert data_apply["is_balanced"] is True
    assert "table_html" in data_apply
    assert "summary_html" in data_apply


@pytest.mark.django_db
def test_dynamic_ajax_add_and_delete_line(setup_smart_balancing_env, client):
    """التحقق من أن إضافة وحذف السطور عبر AJAX تعيد HTML ديناميكي ولا تتطلب ريفرش للصفحة"""
    env = setup_smart_balancing_env
    client.force_login(env["user"])

    batch = OpeningBalanceBatch.objects.create(
        batch_number=f"OPB_AJAX_{env['user'].id}",
        fiscal_year=env["batch"].fiscal_year,
        opening_date=date(2026, 1, 1),
        status="draft",
        created_by=env["user"]
    )

    # 1. إضافة سطر مدين
    add_url = reverse("financial:opening_balance_add_line_action", kwargs={"pk": batch.pk})
    resp_add1 = client.post(add_url, data={
        "line_type": "GL",
        "account_id": env["bank_acc"].id,
        "debit": "75000.00",
        "credit": "0.00",
        "exchange_rate": "1.000000"
    })
    assert resp_add1.status_code == 200
    data1 = resp_add1.json()
    assert data1["success"] is True
    assert "table_html" in data1
    assert "summary_html" in data1
    assert data1["lines_count"] == 1
    assert data1["is_balanced"] is False

    # 2. إضافة سطر دائن موازن
    resp_add2 = client.post(add_url, data={
        "line_type": "EQUITY",
        "account_id": env["capital_acc"].id,
        "debit": "0.00",
        "credit": "75000.00",
        "exchange_rate": "1.000000"
    })
    assert resp_add2.status_code == 200
    data2 = resp_add2.json()
    assert data2["success"] is True
    assert data2["lines_count"] == 2
    assert data2["is_balanced"] is True

    # 3. حذف السطر
    first_line = batch.lines.first()
    delete_url = reverse("financial:opening_balance_delete_line_action", kwargs={"pk": batch.pk, "line_pk": first_line.pk})
    resp_del = client.post(delete_url)
    assert resp_del.status_code == 200
    data_del = resp_del.json()
    assert data_del["success"] is True
    assert data_del["lines_count"] == 1
    assert data_del["is_balanced"] is False
    assert "table_html" in data_del
    assert "summary_html" in data_del


@pytest.mark.django_db
def test_opening_balance_wizard_get_view(setup_smart_balancing_env, client):
    """التحقق من أن عرض صفحة المعالج GET يعمل بنجاح بدون أخطاء قوالب"""
    env = setup_smart_balancing_env
    client.force_login(env["user"])
    wizard_url = reverse("financial:opening_balance_wizard_detail", kwargs={"pk": env["batch"].pk})
    resp = client.get(wizard_url)
    assert resp.status_code == 200
    assert "batch-lines-table" in resp.content.decode('utf-8')
    assert "summary-debit" in resp.content.decode('utf-8')
