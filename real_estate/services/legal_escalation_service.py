# -*- coding: utf-8 -*-
"""
LegalEscalationPipeline - منظومة التصعيد القانوني والإنذارات الرسمية للعقود العقارية
MWHEBA ERP — Real Estate Legal Escalation & Meta WhatsApp Pipeline
"""
import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import UnifiedLog
from core.services.whatsapp_service import WhatsAppService
from sale.models.installments import InstallmentItem
from real_estate.models.contract import PropertyContract, ContractCoOwner
from real_estate.models.legal import LegalNotice
from real_estate.services.meta_whatsapp_payload_builder import MetaWhatsAppPayloadBuilder

logger = logging.getLogger(__name__)


class LegalEscalationPipeline:
    """
    محرك التصعيد القانوني لمتابعة الأقساط العقارية المتعثرة:
    - مرحلة 1 (T-7 / T-3): تذكير استباقي قبل تاريخ الاستحقاق عبر WhatsApp.
    - مرحلة 2 (T+10): إشعار تأخير واحتساب غرامة التأخير التعاقدية اليومية.
    - مرحلة 3 (T+30): إنذار رسمي بالسداد على يد محضر / مسجل بعلم الوصول مع مهلة 15 يوماً وتكافل الشركاء.
    - مرحلة 4 (T+60): محضر إنهاء وتصفية التعاقد لفسخ العقد وإسقاط الحيازة وإحالة الملف للشؤون القانونية.
    - التراجع التلقائي لـ SMS عند تعذر التسليم عبر WhatsApp (خطأ 131026 أو 131047).
    """

    # معدل غرامة التأخير التعاقدية اليومية الافتراضي (0.1% يومياً = 36.5% سنوياً وفق القانون المدني المصري)
    DEFAULT_DAILY_PENALTY_RATE = Decimal('0.001')

    # مهلة توفيق الأوضاع القانونية قبل الفسخ (15 يوماً)
    DEFAULT_CURE_PERIOD_DAYS = 15

    @classmethod
    def determine_escalation_stage(
        cls,
        installment: InstallmentItem,
        as_of_date: Optional[date] = None
    ) -> Tuple[Optional[str], int]:
        """
        تحديد مرحلة التصعيد القانوني وأيام التأخير بناءً على تاريخ الاستحقاق
        """
        if installment.cash_status in [
            InstallmentItem.CashStatus.COLLECTED,
            InstallmentItem.CashStatus.COLLECTED_CONTRA,
            InstallmentItem.CashStatus.WAIVED
        ]:
            return None, 0

        target_date = as_of_date or timezone.localdate()
        days_diff = (installment.due_date - target_date).days

        # استباقي قبل الاستحقاق (T-7 إلى T-1)
        if 1 <= days_diff <= 7:
            return LegalNotice.EscalationStage.STAGE_1_PRE_DUE, 0

        # مستحق اليوم
        if days_diff == 0:
            return None, 0

        # متعثر بعد تاريخ الاستحقاق
        overdue_days = abs(days_diff)

        # مرحلة 2: تأخير ودي واحتساب غرامة (T+1 إلى T+15)
        if 1 <= overdue_days <= 15:
            return LegalNotice.EscalationStage.STAGE_2_GRACE_EXPIRED, overdue_days

        # مرحلة 3: إنذار رسمي بالسداد على يد محضر (T+16 إلى T+45)
        if 16 <= overdue_days <= 45:
            return LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND, overdue_days

        # مرحلة 4: انفساخ العقد وإسقاط الحيازة (T > 45)
        return LegalNotice.EscalationStage.STAGE_4_RESCISSION_NOTICE, overdue_days

    @classmethod
    def calculate_contractual_penalty(
        cls,
        installment: InstallmentItem,
        overdue_days: int,
        daily_rate: Optional[Decimal] = None
    ) -> Decimal:
        """
        حساب غرامة التأخير التعاقدية اليومية وفق شروط التعاقد وأحكام المادتين 226 و 227 من القانون المدني
        """
        if overdue_days <= 0:
            return Decimal('0.00')

        rate = daily_rate if daily_rate is not None else cls.DEFAULT_DAILY_PENALTY_RATE
        remaining = installment.remaining_balance
        penalty = (remaining * rate * Decimal(str(overdue_days))).quantize(Decimal('0.01'))
        return max(Decimal('0.00'), penalty)

    @classmethod
    def format_legal_demand_letter_text(
        cls,
        contract: PropertyContract,
        installment: InstallmentItem,
        overdue_days: int,
        overdue_amount: Decimal,
        penalty_amount: Decimal,
        cure_deadline_date: date,
        verification_token: str
    ) -> str:
        """
        توليد الصيغة القانونية المعتمدة لـ «إنذار رسمي بالسداد على يد محضر / مسجل بعلم الوصول»
        تتضمن بنود التضامن والتكافل للشركاء والكفلاء الغارمين وفق أحكام قانون التجارة 17 لسنة 1999
        """
        customer = contract.customer
        co_owners = list(contract.co_owners.select_related('co_owner').all())

        co_owners_lines = []
        for co in co_owners:
            co_owners_lines.append(
                f"- السيد/ة: {co.co_owner.name} (الرقم القومي: {co.co_owner.national_id or 'غير مسجل'}) "
                f"— بصفته شريكاً بحصة {co.share_percentage}% وكفيلاً غارماً متضامناً متكافلاً."
            )
        co_owners_text = "\n".join(co_owners_lines) if co_owners_lines else "لا يوجد شركاء متضامنون إضافيون."

        total_demanded = overdue_amount + penalty_amount
        currency_code = contract.currency.code if contract.currency else "EGP"

        letter = f"""
جمهورية مصر العربية
وزارة العدل — محكمة الاستئناف
مكتب السادة المحضرين

إنذار رسمي بالسداد على يد محضر مع التنبيه بفسخ العقد وإسقاط الحيازة
--------------------------------------------------------------------------------
بناءً على طلب شركة التطوير والاستثمار العقاري (الدائن والمنذر)،
أنا ................................. محضر محكمة ............................. الجزئية قد انتقلت وأعلنت:

أولاً: المنذر إليه الأصيل:
السيد/ {customer.name}
الرقم القومي: {customer.national_id or 'غير مسجل'}
المقيم في: {customer.address or 'العنوان التعاقدي المثبت بالعقد'}

ثانياً: الشركاء والكفلاء الغارمون المتضامنون:
{co_owners_text}

الموضوع:
بموجب عقد البيع والتطوير العقاري رقم ({contract.contract_number}) المؤرخ في {contract.contract_date}،
والمبرم بشأن الوحدة العقارية كود ({contract.unit.unit_code}) بمشروع ({contract.project.name}).

وحيث إن المنذر إليهم قد ترصد في ذمتهم القسط رقم ({installment.installment_number})
المستحق بتاريخ {installment.due_date}، وقد امتنعوا عن الوفاء به حتى تاريخه رغم انقضاء مواعيد السداد
بمدة تأخير بلغت ({overdue_days}) يوماً، مما ترتب عليه احتساب غرامة تأخير تعاقدية قدرها ({penalty_amount:,.2f} {currency_code}).

البيان المالي للمديونية المطالب بها:
1. أصل القسط المستحق: {overdue_amount:,.2f} {currency_code}
2. غرامة التأخير التعاقدية المحسوبة: {penalty_amount:,.2f} {currency_code}
--------------------------------------------------------------------------------
الإجمالي المستحق فوراً: {total_demanded:,.2f} {currency_code}

التنبيه والإنذار القانوني الصريح:
يُنذر الطالب المنذر إليهم والكفلاء الغارمين بالتضامن والتكافل عملاً بأحكام قانون التجارة رقم 17 لسنة 1999،
بضرورة سداد كامل المديونية الموضحة أعلاه في موعد أقصاه ({cure_deadline_date}) (مهلة 15 يوماً من تاريخ الإعلان).

وفي حالة انقضاء هذه المهلة دون الوفاء التام، يعتبر العقد العقاري مفسوخاً من تلقاء نفسه بقوة القانون وبإعمال
الشرط الفاسخ الصريح (Pacte Commissoire) ودون حاجة إلى تنبيه أو إنذار قضائي لاحق أو استصدار حكم قضائي،
مع حق الشركة في إسقاط الحيازة وإعادة طرح الوحدة للبيع وخصم المصاريف الإدارية والتعويضات الاتفاقية.

بصمة التحقق التشفيرية المعتمدة (SHA-256):
{verification_token}

ولأجل العلم وإعمال مقتضاه القانوني ،،،
"""
        return letter.strip()

    @classmethod
    def format_rescission_notice_text(
        cls,
        contract: PropertyContract,
        installment: InstallmentItem,
        overdue_days: int,
        total_overdue: Decimal,
        verification_token: str
    ) -> str:
        """
        توليد الصيغة القانونية المعتمدة لـ «محضر إنهاء وتصفية التعاقد لفسخ العقد وإسقاط الحيازة»
        """
        customer = contract.customer
        currency_code = contract.currency.code if contract.currency else "EGP"

        return f"""
محضر رسمي لإنهاء وتصفية التعاقد وإعمال الشرط الفاسخ الصريح
--------------------------------------------------------------------------------
المشروع: {contract.project.name}
كود الوحدة: {contract.unit.unit_code}
رقم العقد المفسوخ: {contract.contract_number}
اسم العميل: {customer.name} (الرقم القومي: {customer.national_id or 'غير مسجل'})
تاريخ التحرير: {timezone.localdate()}

إنه في يوم {timezone.localdate().strftime('%A')} الموافق {timezone.localdate()}،
نظراً لثبوت تعثر المنذر إليه عن سداد مستحقات القسط رقم ({installment.installment_number})
البالغة قيمته مع الغرامات ({total_overdue:,.2f} {currency_code})، واستنفاد كافة مراحل الإعذار والإنذار
الرسمي وانقضاء المهلة القانونية المقررة (تجاوز {overdue_days} يوماً من تاريخ الاستحقاق):

قررت الإدارة القانونية وإدارة المشروعات:
1. إعمال الشرط الفاسخ الصريح واعتبار العقد رقم ({contract.contract_number}) مفسوخاً حكماً من تاريخه.
2. إسقاط حيازة الطرف الثاني عن الوحدة العقارية كود ({contract.unit.unit_code}) وتجريدها من أي حقوق عينية.
3. قيد الحساب في السجل الدائن المعلق لإعادة الطرح وتطبيق الخصومات والمصروفات الإدارية التعاقدية.
4. إحالة الملف للشؤون القانونية للبدء في إجراءات المطالبة القضائية بفروق الأسعار والتعويضات.

بصمة التحقق التشفيرية المعتمدة (SHA-256):
{verification_token}
""".strip()

    @classmethod
    def execute_escalation_for_installment(
        cls,
        installment: InstallmentItem,
        as_of_date: Optional[date] = None,
        user: Any = None,
        force_stage: Optional[str] = None,
        simulate_meta_error: Optional[int] = None
    ) -> LegalNotice:
        """
        تنفيذ دورة التصعيد القانوني لقسط محدد مع الحراسة وإرسال WhatsApp ومعالجة التراجع لـ SMS
        """
        target_date = as_of_date or timezone.localdate()

        # استخراج العقد المرتبط بخطة التقسيط
        contract = getattr(installment.plan, 'property_contract', None)
        if not contract:
            raise ValueError(_("خطة التقسيط هذه غير مرتبطة بعقد عقاري (PropertyContract)."))

        customer = contract.customer

        # تحديد المرحلة
        if force_stage:
            stage = force_stage
            overdue_days = max(0, (target_date - installment.due_date).days)
        else:
            stage, overdue_days = cls.determine_escalation_stage(installment, as_of_date=target_date)
            if not stage:
                raise ValueError(_("هذا القسط غير مؤهل للتصعيد القانوني (مسدد أو غير مستحق)."))

        # حساب المبالغ
        overdue_amount = installment.remaining_balance
        penalty_amount = cls.calculate_contractual_penalty(installment, overdue_days) if overdue_days > 0 else Decimal('0.00')
        total_demanded = overdue_amount + penalty_amount
        currency_code = contract.currency.code if contract.currency else "EGP"

        cure_days = cls.DEFAULT_CURE_PERIOD_DAYS
        cure_deadline_date = target_date + timedelta(days=cure_days)

        # استخراج رقم الهاتف
        phone = customer.phone_primary or customer.phone or ""

        # إنشاء سجل LegalNotice المبدئي
        notice = LegalNotice(
            contract=contract,
            installment_item=installment,
            customer=customer,
            stage=stage,
            channel=LegalNotice.NoticeChannel.WHATSAPP,
            status=LegalNotice.NoticeStatus.DRAFT,
            recipient_phone=phone,
            overdue_amount=overdue_amount,
            overdue_days=overdue_days,
            penalty_amount=penalty_amount,
            total_demanded_amount=total_demanded,
            cure_deadline_days=cure_days,
            cure_deadline_date=cure_deadline_date,
            created_by=user
        )
        notice.ensure_notice_number()
        notice.verification_token = notice.compute_verification_token()

        # صياغة محتوى الخطابات للمراحل المتقدمة
        if stage == LegalNotice.EscalationStage.STAGE_3_FORMAL_DEMAND:
            notice.legal_letter_text = cls.format_legal_demand_letter_text(
                contract=contract,
                installment=installment,
                overdue_days=overdue_days,
                overdue_amount=overdue_amount,
                penalty_amount=penalty_amount,
                cure_deadline_date=cure_deadline_date,
                verification_token=notice.verification_token
            )
        elif stage == LegalNotice.EscalationStage.STAGE_4_RESCISSION_NOTICE:
            notice.legal_letter_text = cls.format_rescission_notice_text(
                contract=contract,
                installment=installment,
                overdue_days=overdue_days,
                total_overdue=total_demanded,
                verification_token=notice.verification_token
            )

        # بناء حمولة WhatsApp المعتمدة من Meta Graph API v21.0
        if stage in [LegalNotice.EscalationStage.STAGE_1_PRE_DUE, LegalNotice.EscalationStage.STAGE_2_GRACE_EXPIRED]:
            notice.template_name = MetaWhatsAppPayloadBuilder.TEMPLATE_INSTALLMENT_REMINDER
            statement_url = f"/real-estate/statements/{contract.id}/"
            meta_payload = MetaWhatsAppPayloadBuilder.build_installment_reminder_payload(
                recipient_phone=phone,
                customer_name=customer.name,
                unit_code=contract.unit.unit_code,
                due_date=str(installment.due_date),
                amount=total_demanded,
                currency_code=currency_code,
                statement_url=statement_url,
                statement_token=notice.verification_token[:16]
            )
        else:
            notice.template_name = MetaWhatsAppPayloadBuilder.TEMPLATE_LEGAL_NOTICE_DEMAND
            meta_payload = MetaWhatsAppPayloadBuilder.build_legal_demand_payload(
                recipient_phone=phone,
                customer_name=customer.name,
                unit_code=contract.unit.unit_code,
                contract_number=contract.contract_number,
                overdue_days=overdue_days,
                total_overdue_amount=total_demanded,
                cure_deadline=str(cure_deadline_date),
                currency_code=currency_code
            )

        notice.meta_payload = meta_payload

        # إرسال الرسالة عبر محرك WhatsApp المركزي مع دعم المحاكاة للاختبارات
        meta_result: Dict[str, Any] = {}
        if simulate_meta_error:
            meta_result = {
                "success": False,
                "error_code": simulate_meta_error,
                "error": WhatsAppService.META_ERROR_GUIDANCE.get(simulate_meta_error, f"Error {simulate_meta_error}")
            }
        else:
            try:
                # استخراج المكونات وتمريرها لمحرك الواتساب
                components = meta_payload.get("template", {}).get("components", [])
                meta_result = WhatsAppService.send_template_message(
                    phone=phone,
                    template_name=notice.template_name,
                    language_code="ar",
                    components=components,
                    partner=customer,
                    content_object=contract,
                    created_by=user,
                    is_automatic=True
                )
            except Exception as ex:
                logger.warning(f"WhatsApp sending raised exception: {ex}")
                meta_result = {"success": False, "error_code": 999999, "error": str(ex)}

        # فحص نتيجة الإرسال وآلية التراجع التلقائي لـ SMS (Automated Fallback)
        if meta_result.get("success"):
            notice.status = LegalNotice.NoticeStatus.SENT
            notice.sent_at = timezone.now()
            notice.meta_message_id = meta_result.get("message_id", "")
            logger.info(f"✅ تم إرسال إشعار WhatsApp للمرحلة {stage} بنجاح إلى {phone}.")
        else:
            err_code = meta_result.get("error_code")
            # خطأ 131026: الرقم غير مسجل على واتساب، أو 131047: نفاد كوتا الخدمات
            if err_code in [131026, 131047] or simulate_meta_error in [131026, 131047]:
                notice.channel = LegalNotice.NoticeChannel.SMS
                notice.fallback_channel_used = 'SMS'
                notice.fallback_error_code = err_code or simulate_meta_error
                notice.status = LegalNotice.NoticeStatus.FALLBACK_TRIGGERED
                notice.sent_at = timezone.now()

                # توثيق عملية التراجع في السجل الموحد UnifiedLog
                try:
                    UnifiedLog.log_system(
                        level='WARNING',
                        category='integration',
                        message=(
                            f"⚠️ تفعيل قناة التراجع التلقائي لـ SMS للعميل {customer.name} ({phone}) "
                            f"نظراً لتعذر تسليم WhatsApp لخطأ ميتا رقم {notice.fallback_error_code}: "
                            f"{WhatsAppService.META_ERROR_GUIDANCE.get(notice.fallback_error_code, 'Meta Error')}"
                        ),
                        user=user,
                        contract_number=contract.contract_number,
                        stage=stage,
                        fallback_channel='SMS'
                    )
                except Exception as log_ex:
                    logger.warning(f"UnifiedLog creation error: {log_ex}")
            else:
                notice.status = LegalNotice.NoticeStatus.FAILED
                notice.fallback_error_code = err_code

        # تحديث بيانات القسط والعقد
        installment.last_reminder_sent_at = timezone.now()
        installment.reminder_count = (installment.reminder_count or 0) + 1
        if penalty_amount > Decimal('0.00'):
            installment.penalty_amount = penalty_amount

        if stage == LegalNotice.EscalationStage.STAGE_4_RESCISSION_NOTICE:
            installment.cash_status = InstallmentItem.CashStatus.LEGAL_ACTION
            installment.legal_referral_date = target_date
            installment.court_case_number = notice.notice_number or f"NOT-{contract.contract_number}"

        installment.save(update_fields=[
            'last_reminder_sent_at',
            'reminder_count',
            'penalty_amount',
            'cash_status',
            'legal_referral_date',
            'court_case_number'
        ])

        notice.save()
        return notice

    @classmethod
    def get_certified_demand_letter_context(cls, notice: LegalNotice) -> Dict[str, Any]:
        """
        تجهيز سياق البيانات الكامل لطباعة الإنذار الرسمي أو تصديره إلى PDF
        """
        contract = notice.contract
        customer = notice.customer
        installment = notice.installment_item

        co_owners_data = []
        for co in contract.co_owners.select_related('co_owner').all():
            co_owners_data.append({
                'name': co.co_owner.name,
                'national_id': co.co_owner.national_id or 'غير مسجل',
                'share_percentage': co.share_percentage,
                'is_guarantor': co.is_joint_and_several_guarantor,
                'phone': co.co_owner.phone_primary or co.co_owner.phone or ''
            })

        return {
            'notice_number': notice.notice_number,
            'contract_number': contract.contract_number,
            'contract_date': contract.contract_date,
            'project_name': contract.project.name,
            'unit_code': contract.unit.unit_code,
            'customer_name': customer.name,
            'customer_national_id': customer.national_id or 'غير مسجل',
            'customer_address': customer.address or 'العنوان التعاقدي المثبت بالعقد',
            'customer_phone': notice.recipient_phone,
            'co_owners': co_owners_data,
            'installment_number': installment.installment_number if installment else 1,
            'due_date': installment.due_date if installment else timezone.localdate(),
            'overdue_days': notice.overdue_days,
            'overdue_amount': notice.overdue_amount,
            'penalty_amount': notice.penalty_amount,
            'total_demanded_amount': notice.total_demanded_amount,
            'currency_code': contract.currency.code if contract.currency else "EGP",
            'cure_deadline_days': notice.cure_deadline_days,
            'cure_deadline_date': notice.cure_deadline_date,
            'verification_token': notice.verification_token,
            'stage': notice.stage,
            'stage_display': notice.get_stage_display(),
            'legal_letter_text': notice.legal_letter_text,
            'created_at': notice.created_at,
        }
