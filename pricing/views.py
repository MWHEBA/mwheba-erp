import logging

logger = logging.getLogger(__name__)
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    View,
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.template.loader import get_template
import json

from supplier.models import Supplier, PaperServiceDetails
from client.models import Customer as Client  # استخدام Customer بدلاً من Client
from .models import (
    PaperType,
    PaperSize,
    PrintSide,
    PrintDirection,
    CoatingType,
    FinishingType,
    PlateSize,
    PricingOrder,
    InternalContent,
    OrderFinishing,
    ExtraExpense,
    CtpPlates,
    OrderComment,
    VATSetting,
)

# تم استيراد جميع النماذج من models.py
# استيراد النماذج والفورمز
from .forms import (
    PricingOrderForm,
    InternalContentForm,
    OrderFinishingForm,
    ExtraExpenseForm,
    OrderCommentForm,
    CtpPlatesForm,
    PricingOrderApproveForm,
)

import json
import os
from decimal import Decimal
import datetime

# from weasyprint import HTML, CSS
from io import BytesIO


class PricingOrderListView(LoginRequiredMixin, ListView):
    """عرض قائمة طلبات التسعير"""

    model = PricingOrder
    template_name = "pricing/pricing_list.html"
    context_object_name = "orders"
    paginate_by = 10

    def get_queryset(self):
        """تخصيص الاستعلام حسب دور المستخدم"""
        queryset = super().get_queryset().select_related("client", "created_by")

        # تطبيق الفلاتر إذا تم تحديدها
        status = self.request.GET.get("status")
        client_id = self.request.GET.get("client")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")

        if status:
            queryset = queryset.filter(status=status)
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["clients"] = Client.objects.all()
        context["status_choices"] = PricingOrder.STATUS_CHOICES

        # تعريف headers للجدول الموحد
        headers = [
            {
                "key": "order_number",
                "label": "رقم الطلب",
                "sortable": True,
                "class": "text-center",
            },
            {
                "key": "created_at",
                "label": "تاريخ الإنشاء",
                "sortable": True,
                "class": "text-center",
                "format": "datetime_12h",
            },
            {
                "key": "client",
                "label": "العميل",
                "template": "pricing/columns/client_column.html",
            },
            {
                "key": "title",
                "label": "العنوان",
                "sortable": True,
                "class": "text-start",
            },
            {
                "key": "order_type",
                "label": "نوع الطباعة",
                "template": "pricing/columns/order_type_column.html",
            },
            {
                "key": "quantity",
                "label": "الكمية",
                "sortable": True,
                "class": "text-center",
            },
            {
                "key": "sale_price",
                "label": "سعر البيع",
                "sortable": True,
                "class": "text-center",
                "format": "currency",
                "decimals": 2,
            },
            {
                "key": "status",
                "label": "الحالة",
                "template": "pricing/columns/status_column.html",
            },
            {
                "key": "created_by.get_full_name",
                "label": "المنشئ",
                "sortable": True,
                "class": "text-center",
            },
        ]

        # بيانات الصفحة والبريدكرمب
        context["page_title"] = "قائمة طلبات التسعير"
        context["page_icon"] = "fas fa-list"
        context["breadcrumb_items"] = [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "قائمة الطلبات",
                "url": "",
                "icon": "fas fa-list",
                "active": True,
            },
        ]

        # تعريف أزرار الإجراءات للجدول
        order_actions = [
            {
                "url": "pricing:pricing_detail",
                "icon": "fa-eye",
                "label": "عرض",
                "class": "action-view",
            },
            {
                "url": "pricing:pricing_edit",
                "icon": "fa-edit",
                "label": "تعديل",
                "class": "action-edit",
                "condition": "user.is_staff or user == item.created_by",
            },
            {
                "url": "pricing:pricing_approve",
                "icon": "fa-check",
                "label": "اعتماد",
                "class": "action-approve",
                "condition": 'user.is_staff and item.status == "pending"',
            },
        ]

        # إضافة بيانات الجدول الموحد
        context["headers"] = headers
        context["data"] = context["orders"]
        context["table_id"] = "orders-table"
        context["clickable_rows"] = True
        context["row_click_url"] = "/pricing/0/"
        context["primary_key"] = "id"
        context["show_export"] = True
        context["export_filename"] = "pricing_orders"
        context["action_buttons"] = order_actions
        context["show_currency"] = True
        context["currency_symbol"] = "ج.م"

        return context


class PricingOrderCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء طلب تسعير جديد"""

    model = PricingOrder
    form_class = PricingOrderForm
    template_name = "pricing/pricing_form.html"
    success_url = reverse_lazy("pricing:pricing_order_list")

    def get_form_kwargs(self):
        """تمرير المستخدم الحالي إلى النموذج"""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        """تحديد القيم الافتراضية للنموذج"""
        initial = super().get_initial()

        try:
            # الحصول على مقاس المنتج الافتراضي (A4)
            if hasattr(PaperSize, "objects") and PaperSize.objects:
                default_paper_size = PaperSize.objects.filter(is_default=True).first()
                if default_paper_size:
                    initial["product_size"] = default_paper_size.pk

            # الحصول على اتجاه الطباعة الافتراضي (طولي)
            if hasattr(PrintDirection, "objects") and PrintDirection.objects:
                default_print_direction = PrintDirection.objects.filter(
                    is_default=True
                ).first()
                if default_print_direction:
                    initial["print_direction"] = default_print_direction.pk
        except Exception as e:
            # في حالة وجود خطأ، نتجاهله ونستمر
            pass

        # استرجاع البيانات المحفوظة في الجلسة إذا كانت موجودة
        if "pricing_form_data" in self.request.session:
            session_data = self.request.session["pricing_form_data"]

            # معالجة البيانات المحفوظة في الجلسة
            for key, value in session_data.items():
                # تحويل القيم الرقمية إلى النوع المناسب
                if key in [
                    "quantity",
                    "colors_front",
                    "colors_back",
                    "zinc_plates_count",
                    "internal_page_count",
                    "ctp_plates_count",
                ]:
                    try:
                        if value and str(value).strip():
                            initial[key] = int(value)
                    except (ValueError, AttributeError):
                        pass
                elif key in [
                    "custom_size_width",
                    "custom_size_height",
                ]:
                    try:
                        if value and str(value).strip():
                            initial[key] = float(value)
                    except (ValueError, AttributeError):
                        pass
                # معالجة مربعات الاختيار
                elif key == "has_internal_content":
                    initial[key] = value == "on" or value == "true" or value == True
                # معالجة القوائم المنسدلة
                elif key in [
                    "paper_type",
                    "product_size",
                    "print_direction",
                    "print_sides",
                    "coating_type",
                    "supplier",
                    "press",
                    "order_type",
                    "ctp_supplier",
                    "ctp_plate_size",
                ]:
                    try:
                        if value and str(value).strip():
                            initial[key] = int(value) if value.isdigit() else value
                    except (ValueError, AttributeError):
                        initial[key] = value
                # باقي الحقول تعامل كنصوص
                else:
                    initial[key] = value

        return initial

    def post(self, request, *args, **kwargs):
        """معالجة طلب POST"""
        # التحقق مما إذا كان الطلب هو AJAX لحفظ البيانات في الجلسة
        if request.headers.get(
            "X-Requested-With"
        ) == "XMLHttpRequest" and not request.POST.get("regular_submit"):
            # تخزين جميع البيانات من النموذج
            form_data = {}
            for key, value in request.POST.items():
                if key != "csrfmiddlewaretoken":
                    form_data[key] = value

            # تحديث بيانات الجلسة بدلاً من استبدالها
            if "pricing_form_data" not in request.session:
                request.session["pricing_form_data"] = {}

            # تحديث البيانات الموجودة مع البيانات الجديدة
            for key, value in form_data.items():
                request.session["pricing_form_data"][key] = value

            # طباعة البيانات للتأكد من تخزينها بشكل صحيح (للتصحيح فقط)
            # تم تخزين البيانات في الجلسة

            # التأكد من تعديل الجلسة
            request.session.modified = True

            return JsonResponse(
                {"status": "success", "message": "تم حفظ البيانات في الجلسة"}
            )

        # إذا لم يكن طلب AJAX، استمر في المعالجة العادية للنموذج
        # معالجة طلب POST العادي لحفظ التسعيرة

        try:
            # تنظيف البيانات قبل معالجة النموذج
            mutable_data = request.POST.copy()
            
            # معالجة حقل paper_type للتأكد من عدم إرسال قيم فارغة أو غير صحيحة
            paper_type_value = mutable_data.get('paper_type', '')
            if paper_type_value == '' or paper_type_value == 'undefined' or paper_type_value == 'null' or paper_type_value == 'None':
                # إزالة الحقل تماماً بدلاً من إرسال قيمة فارغة
                if 'paper_type' in mutable_data:
                    del mutable_data['paper_type']
                    print(f"تم حذف حقل paper_type بقيمة غير صحيحة: '{paper_type_value}'")
            else:
                # التحقق من أن القيمة رقم صحيح
                try:
                    paper_type_id = int(paper_type_value)
                    if paper_type_id <= 0:
                        if 'paper_type' in mutable_data:
                            del mutable_data['paper_type']
                            print(f"تم حذف حقل paper_type بقيمة رقمية غير صحيحة: {paper_type_id}")
                except (ValueError, TypeError):
                    if 'paper_type' in mutable_data:
                        del mutable_data['paper_type']
                        print(f"تم حذف حقل paper_type بقيمة غير رقمية: '{paper_type_value}'")
            
            # تحديث request.POST بالبيانات المنظفة
            request.POST = mutable_data
            
            # محاولة معالجة النموذج بشكل عادي
            form = self.get_form()
            
            if form.is_valid():
                # النموذج صالح - جاري حفظ التسعيرة
                return self.form_valid(form)
            else:
                # النموذج غير صالح - أخطاء التحقق
                return self.form_invalid(form)
        except Exception as e:
            # التقاط أي أخطاء قد تحدث أثناء معالجة النموذج
            # خطأ أثناء معالجة النموذج
            import traceback

            traceback.print_exc()
            messages.error(request, f"حدث خطأ أثناء حفظ التسعيرة: {e}")
            return redirect("pricing:pricing_order_list")

    def form_valid(self, form):
        """تعيين المستخدم الحالي كمنشئ للطلب وحفظ البيانات الإضافية"""
        try:
            # تعيين المستخدم الحالي كمنشئ للطلب
            form.instance.created_by = self.request.user

            # تعيين حالة الطلب إلى 'pending' بشكل تلقائي
            form.instance.status = "pending"

            # التأكد من أن العميل محدد بشكل صحيح
            if not form.instance.client_id and form.cleaned_data.get("client"):
                form.instance.client = form.cleaned_data.get("client")

            # حفظ النموذج أولاً لإنشاء الكائن (self.object)
            response = super().form_valid(form)

            # الآن يمكننا استخدام self.object بأمان لأنه تم تعيينه بواسطة super().form_valid(form)
            order_object = self.object

            # استخراج البيانات الإضافية من النموذج
            product_type = form.cleaned_data.get("product_type")
            custom_size_width = form.cleaned_data.get("custom_size_width")
            custom_size_height = form.cleaned_data.get("custom_size_height")
            open_size_width = form.cleaned_data.get("open_size_width")
            open_size_height = form.cleaned_data.get("open_size_height")
            binding_type = form.cleaned_data.get("binding_type")
            binding_side = form.cleaned_data.get("binding_side")
            paper_weight = form.cleaned_data.get("paper_weight")
            paper_supplier = form.cleaned_data.get("paper_supplier")
            paper_price = form.cleaned_data.get("paper_price")
            zinc_plates_count = form.cleaned_data.get("zinc_plates_count")
            internal_page_count = form.cleaned_data.get("internal_page_count")
            design_price = self.request.POST.get("design_price")

            # استخراج بيانات الزنكات من الطلب
            ctp_supplier_id = self.request.POST.get("ctp_supplier")
            ctp_plate_size_id = self.request.POST.get("ctp_plate_size")
            ctp_plates_count = self.request.POST.get("ctp_plates_count")
            ctp_plate_price = self.request.POST.get("ctp_plate_price")
            ctp_transportation = self.request.POST.get("ctp_transportation")

            # إنشاء سجل زنكات إذا توفرت البيانات اللازمة
            if (
                ctp_supplier_id
                and ctp_plate_size_id
                and ctp_plates_count
                and ctp_plate_price
            ):
                try:
                    supplier = Supplier.objects.get(pk=ctp_supplier_id)
                    plate_size = (
                        PlateSize.objects.get(pk=ctp_plate_size_id)
                        if hasattr(PlateSize, "objects")
                        else None
                    )

                    # إنشاء سجل الزنكات
                    CtpPlates.objects.create(
                        order=order_object,
                        is_internal=False,
                        supplier=supplier,
                        plate_size=plate_size,
                        plates_count=int(ctp_plates_count),
                        plate_price=Decimal(ctp_plate_price),
                        transportation_cost=Decimal(ctp_transportation or "0.00"),
                        total_cost=(Decimal(ctp_plate_price) * int(ctp_plates_count))
                        + Decimal(ctp_transportation or "0.00"),
                        notes="تم إنشاؤه تلقائيًا من نموذج التسعير",
                    )
                except (Supplier.DoesNotExist, PlateSize.DoesNotExist, ValueError) as e:
                    logger.error(f"خطأ في إنشاء سجل الزنكات: {str(e)}")
                    pass

            # استخراج بيانات خدمات ما بعد الطباعة
            finishing_services = {}

            # التغطية
            if self.request.POST.get("coating_service"):
                finishing_services["coating"] = {
                    "type": self.request.POST.get("coating_type"),
                    "supplier": self.request.POST.get("coating_supplier"),
                    "price": self.request.POST.get("coating_price"),
                    "notes": self.request.POST.get("coating_notes"),
                }

            # الريجة
            if self.request.POST.get("folding_service"):
                finishing_services["folding"] = {
                    "count": self.request.POST.get("folding_count"),
                    "supplier": self.request.POST.get("folding_supplier"),
                    "price": self.request.POST.get("folding_price"),
                    "notes": self.request.POST.get("folding_notes"),
                }

            # التكسير
            if self.request.POST.get("die_cut_service"):
                finishing_services["die_cut"] = {
                    "type": self.request.POST.get("die_cut_type"),
                    "supplier": self.request.POST.get("die_cut_supplier"),
                    "price": self.request.POST.get("die_cut_price"),
                    "notes": self.request.POST.get("die_cut_notes"),
                }

            # سبوت يوفي
            if self.request.POST.get("spot_uv_service"):
                finishing_services["spot_uv"] = {
                    "coverage": self.request.POST.get("spot_uv_coverage"),
                    "supplier": self.request.POST.get("spot_uv_supplier"),
                    "price": self.request.POST.get("spot_uv_price"),
                    "notes": self.request.POST.get("spot_uv_notes"),
                }

            # تخزين هذه البيانات في حقل الوصف
            additional_data = {
                "product_type": product_type,
                "custom_size": {
                    "width": str(custom_size_width),
                    "height": str(custom_size_height),
                }
                if custom_size_width and custom_size_height
                else None,
                "open_size": {
                    "width": str(open_size_width),
                    "height": str(open_size_height),
                }
                if open_size_width and open_size_height
                else None,
                "binding_type": binding_type,
                "binding_side": binding_side,
                "paper_weight": paper_weight,
                "paper_supplier": paper_supplier,
                "paper_price": paper_price,
                "zinc_plates_count": zinc_plates_count,
                "internal_page_count": internal_page_count,
                "finishing_services": finishing_services,
                "design_price": design_price,
            }

            # تحويل البيانات إلى تنسيق قابل للتحويل إلى JSON
            additional_data = json.dumps(additional_data, cls=DjangoJSONEncoder)
            # إذا كان هناك محتوى داخلي، نقوم بإنشاء كائن InternalContent
            if form.instance.has_internal_content and internal_page_count:
                try:
                    InternalContent.objects.create(
                        order=order_object,
                        paper_type=form.instance.paper_type,
                        product_size=form.instance.product_size,
                        page_count=internal_page_count,
                        print_sides=form.instance.print_sides,
                        colors_front=form.instance.colors_front,
                        colors_back=form.instance.colors_back,
                    )
                except Exception as e:
                    logger.error(f"خطأ في إنشاء سجل المحتوى الداخلي: {str(e)}")
                    pass

            # تحديث الوصف بالبيانات الإضافية إذا لم يكن مضبوطًا بالفعل
            if not form.instance.description:
                try:
                    order_object.description = json.dumps(additional_data)
                    order_object.save()
                except TypeError as e:
                    logger.error(f"خطأ في تحويل البيانات إلى JSON: {str(e)}")
                    pass

            # إنشاء خدمات الطباعة في قاعدة البيانات
            self.create_finishing_services(finishing_services, order_object)

            # مسح البيانات المحفوظة من الجلسة بعد الإنشاء الناجح
            if "pricing_form_data" in self.request.session:
                del self.request.session["pricing_form_data"]
                self.request.session.modified = True

            messages.success(self.request, "تم إنشاء طلب التسعير بنجاح.")
            return response

        except Exception as e:
            # معالجة شاملة للأخطاء
            logger.error(f"خطأ في form_valid: {str(e)}")
            import traceback
            traceback.print_exc()
            messages.error(self.request, f"حدث خطأ أثناء حفظ التسعيرة: {str(e)}")
            return self.form_invalid(form)

    def create_finishing_services(self, finishing_services, order_object=None):
        """إنشاء خدمات الطباعة في قاعدة البيانات"""
        # استخدام order_object المرسل بدلاً من self.object
        if not order_object:
            # تحذير: order_object غير موجود، لا يمكن إنشاء خدمات الطباعة
            return

        # قائمة بأنواع خدمات مابعد الطباعة وأسمائها
        finishing_types = {
            "coating": "تغطية",
            "folding": "ريجة",
            "die_cut": "تكسير",
            "spot_uv": "سبوت يوفي",
        }

        for service_type, service_data in finishing_services.items():
            # البحث عن نوع خدمات مابعد الطباعة في قاعدة البيانات أو إنشاؤه إذا لم يكن موجودًا
            try:
                finishing_type = FinishingType.objects.get(
                    name=finishing_types[service_type]
                )
            except FinishingType.DoesNotExist:
                # إنشاء نوع تشطيب جديد إذا لم يكن موجودًا
                finishing_type = FinishingType.objects.create(
                    name=finishing_types[service_type],
                    description=f"خدمة {finishing_types[service_type]}",
                    price_per_unit=0,
                    is_active=True,
                )

            # إنشاء خدمة خدمات مابعد الطباعة
            try:
                price = float(service_data.get("price", 0))
                notes = service_data.get("notes", "")

                # إنشاء كائن خدمة خدمات مابعد الطباعة
                finishing_service = OrderFinishing(
                    order=order_object,
                    finishing_type=finishing_type,
                    quantity=1,  # يمكن تعديلها حسب الحاجة
                    unit_price=price,
                    # total_price=price,  # تم إزالة هذا الحقل
                    notes=notes,
                )

                # إضافة مورد الخدمة إذا كان متوفراً
                supplier_id = service_data.get("supplier")
                if supplier_id:
                    try:
                        # محاولة تحويل supplier_id إلى قيمة عددية إذا كان نصياً
                        if isinstance(supplier_id, str) and supplier_id.isdigit():
                            supplier_id = int(supplier_id)

                        # إذا كان كائن Supplier، استخدم معرفه
                        if hasattr(supplier_id, "id"):
                            supplier_id = supplier_id.id

                        # البحث عن المورد في قاعدة البيانات
                        supplier = Supplier.objects.get(pk=supplier_id)
                        finishing_service.supplier = supplier
                    except (ValueError, Supplier.DoesNotExist) as e:
                        # تحذير: لم يتم العثور على مورد الخدمة
                        pass

                # حفظ خدمة خدمات مابعد الطباعة
                finishing_service.save()
                # تم إنشاء خدمة خدمات مابعد الطباعة بنجاح

            except Exception as e:
                # يمكن إضافة سجل خطأ هنا
                # خطأ في إنشاء خدمة خدمات مابعد الطباعة
                import traceback

                traceback.print_exc()
                messages.error(
                    self.request,
                    f"خطأ في إنشاء خدمة خدمات مابعد الطباعة {finishing_types[service_type]}: {str(e)}",
                )

    def form_invalid(self, form):
        """حفظ البيانات في الجلسة عند فشل التحقق من صحة النموذج"""
        # طباعة أخطاء النموذج للتشخيص
        # أخطاء النموذج
        for field, errors in form.errors.items():
            # إضافة رسائل خطأ للمستخدم
            for error in errors:
                field_name = form.fields[field].label if field in form.fields else field
                messages.error(self.request, f"خطأ في حقل '{field_name}': {error}")

        # طباعة البيانات التي تم إرسالها
        # البيانات المرسلة
        for key, value in form.data.items():
            if key != "csrfmiddlewaretoken":
                pass  # للتصحيح فقط

        # حفظ البيانات المدخلة في الجلسة
        form_data = {}
        for key, value in form.data.items():
            if key != "csrfmiddlewaretoken":
                form_data[key] = value

        # تحديث بيانات الجلسة بدلاً من استبدالها
        if "pricing_form_data" not in self.request.session:
            self.request.session["pricing_form_data"] = {}

        # تحديث البيانات الموجودة مع البيانات الجديدة
        for key, value in form_data.items():
            self.request.session["pricing_form_data"][key] = value

        # التأكد من تعديل الجلسة
        self.request.session.modified = True

        # إضافة رسالة خطأ عامة
        messages.error(
            self.request, "هناك أخطاء في النموذج. يرجى التحقق من البيانات المدخلة."
        )

        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["title"] = "إضافة طلب تسعير جديد"

        # إضافة المعلومات الضرورية للنموذج
        context["paper_type_weights_json"] = self.get_paper_type_weights_json()

        # استخدام الموردين المفلترين (الحل الجذري)
        from .supplier_filters import get_printing_suppliers, get_ctp_suppliers, get_coating_suppliers

        context["plate_suppliers"] = get_ctp_suppliers()
        context["coating_suppliers"] = get_coating_suppliers()
        context["plate_sizes"] = (
            PlateSize.objects.all() if hasattr(PlateSize, "objects") else []
        )

        # إضافة موردي المطابع المفلترين
        context["printing_suppliers"] = get_printing_suppliers()

        # تحديد ما إذا كانت هناك بيانات محفوظة في الجلسة
        context["has_saved_data"] = "pricing_form_data" in self.request.session

        # إضافة بيانات الجلسة إلى السياق إذا كانت موجودة
        if "pricing_form_data" in self.request.session:
            context["session_data"] = json.dumps(
                self.request.session["pricing_form_data"]
            )

        # إضافة موردي خدمات الطباعة إلى السياق
        context["finishing_suppliers"] = Supplier.objects.filter(
            is_active=True
        )  # مؤقت - جميع الموردين

        # بيانات الصفحة والبريدكرمب
        context["page_title"] = "إنشاء طلب تسعير جديد"
        context["page_icon"] = "fas fa-plus"
        context["breadcrumb_items"] = [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "قائمة الطلبات",
                "url": reverse("pricing:pricing_order_list"),
                "icon": "fas fa-list",
            },
            {"title": "طلب جديد", "url": "", "icon": "fas fa-plus", "active": True},
        ]

        return context

    def get_paper_type_weights_json(self):
        """تجهيز دكشنري أنواع الورق والأوزان مع تجميع الأنواع المتشابهة"""
        try:
            # التحقق من وجود النموذج وإمكانية الوصول إليه
            if hasattr(PaperType, "objects") and PaperType.objects is not None:
                paper_types = PaperType.objects.filter(is_active=True)
            else:
                # استخدام النموذج الحقيقي من models.py
                from .models import PaperType as RealPaperType

                paper_types = RealPaperType.objects.all()
        except Exception:
            # في حالة فشل كل شيء، إرجاع بيانات افتراضية
            paper_type_weights = {
                "1": [80, 90, 100, 120, 150, 170, 200, 250, 300, 350],  # ورق عادي
                "2": [80, 90, 100, 120, 150, 170],  # ورق مطبوع
                "3": [200, 250, 300, 350],  # كرتون
            }
            return json.dumps(paper_type_weights)

        # تجميع أنواع الورق حسب الاسم الأساسي
        grouped_paper_types = {}

        for pt in paper_types:
            try:
                # استخراج الاسم الأساسي (الكلمة الأولى من الاسم)
                base_name = (
                    pt.name.split()[0].strip()
                    if hasattr(pt, "name") and pt.name
                    else f"نوع {pt.id}"
                )

                # إنشاء مفتاح مركب من الاسم الأساسي
                key = base_name

                # إذا لم يكن المفتاح موجودًا، أنشئ قائمة جديدة
                if key not in grouped_paper_types:
                    # نستخدم أول معرف نجده لهذا النوع
                    grouped_paper_types[key] = {
                        "id": pt.id,
                        "name": base_name,
                        "weights": [],
                    }

                # إضافة الوزن إلى قائمة الأوزان إذا لم يكن موجودًا بالفعل
                gsm = getattr(pt, "gsm", None) or 100  # قيمة افتراضية
                if gsm not in grouped_paper_types[key]["weights"]:
                    grouped_paper_types[key]["weights"].append(gsm)
            except Exception:
                continue

        # تحويل القاموس إلى الصيغة المطلوبة للـ JSON
        paper_type_weights = {}
        for key, data in grouped_paper_types.items():
            pt_id = str(data["id"])
            paper_type_weights[pt_id] = sorted(
                data["weights"]
            )  # ترتيب الأوزان تصاعديًا

        # إذا لم نحصل على أي بيانات، إرجاع بيانات افتراضية
        if not paper_type_weights:
            paper_type_weights = {
                "1": [80, 90, 100, 120, 150, 170, 200, 250, 300, 350],
            }

        return json.dumps(paper_type_weights)


class PricingOrderDetailView(LoginRequiredMixin, DetailView):
    """عرض تفاصيل طلب التسعير"""

    model = PricingOrder
    template_name = "pricing/pricing_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["finishing_services"] = self.object.finishing_services.all()
        context["extra_expenses"] = self.object.extra_expenses.all()
        context["comments"] = self.object.comments.all().order_by("-created_at")
        context["comment_form"] = OrderCommentForm()

        # التحقق مما إذا كان للطلب محتوى داخلي
        try:
            context["internal_content"] = self.object.internal_content
        except InternalContent.DoesNotExist:
            context["internal_content"] = None

        return context


class PricingOrderUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """عرض تحديث طلب التسعير"""

    model = PricingOrder
    form_class = PricingOrderForm
    template_name = "pricing/pricing_form.html"

    def get_form_kwargs(self):
        """تمرير المستخدم الحالي إلى النموذج"""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def test_func(self):
        """التحقق من صلاحية المستخدم"""
        order = self.get_object()
        return (
            self.request.user.is_admin
            or self.request.user.is_supervisor
            or self.request.user == order.created_by
        )

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        """تحديث طلب التسعير"""
        # استخراج البيانات الإضافية من النموذج
        product_type = form.cleaned_data.get("product_type")
        custom_size_width = form.cleaned_data.get("custom_size_width")
        custom_size_height = form.cleaned_data.get("custom_size_height")
        open_size_width = form.cleaned_data.get("open_size_width")
        open_size_height = form.cleaned_data.get("open_size_height")
        binding_type = form.cleaned_data.get("binding_type")
        binding_side = form.cleaned_data.get("binding_side")
        paper_weight = form.cleaned_data.get("paper_weight")
        paper_supplier = form.cleaned_data.get("paper_supplier")
        paper_price = form.cleaned_data.get("paper_price")
        zinc_plates_count = form.cleaned_data.get("zinc_plates_count")
        internal_page_count = form.cleaned_data.get("internal_page_count")

        # تخزين هذه البيانات في حقل الوصف
        additional_data = {
            "product_type": product_type,
            "custom_size": {
                "width": str(custom_size_width),
                "height": str(custom_size_height),
            }
            if custom_size_width and custom_size_height
            else None,
            "open_size": {
                "width": str(open_size_width),
                "height": str(open_size_height),
            }
            if open_size_width and open_size_height
            else None,
            "binding_type": binding_type,
            "binding_side": binding_side,
            "paper_weight": paper_weight,
            "paper_supplier": paper_supplier,
            "paper_price": paper_price,
            "zinc_plates_count": zinc_plates_count,
            "internal_page_count": internal_page_count,
        }

        # تحويل البيانات إلى تنسيق قابل للتحويل إلى JSON
        additional_data = sanitize_for_json(additional_data)

        # إذا كان هناك محتوى داخلي، نقوم بإنشاء أو تحديث كائن InternalContent
        if form.instance.has_internal_content and internal_page_count:
            InternalContent.objects.update_or_create(
                order=self.get_object(),
                defaults={
                    "paper_type": form.instance.paper_type,
                    "product_size": form.instance.product_size,  # تم تصحيح الاسم من paper_size إلى product_size
                    "page_count": internal_page_count,
                    "print_sides": form.instance.print_sides,
                    "colors_front": form.instance.colors_front,
                    "colors_back": form.instance.colors_back,
                },
            )
        elif not form.instance.has_internal_content:
            # إذا تم إلغاء تحديد خيار المحتوى الداخلي، نقوم بحذف كائن InternalContent إذا كان موجوداً
            InternalContent.objects.filter(order=self.get_object()).delete()

        # تحديث الوصف بالبيانات الإضافية
        if form.instance.description and form.instance.description.startswith("{"):
            # إذا كان الوصف يحتوي على بيانات JSON، نقوم بتحديثها
            try:
                existing_data = json.loads(form.instance.description)

                if isinstance(existing_data, dict) and isinstance(
                    additional_data, dict
                ):
                    existing_data.update(additional_data)
                    form.instance.description = json.dumps(existing_data)
                else:
                    # إذا لم يكن أي من existing_data أو additional_data قاموسًا
                    # نستخدم additional_data فقط
                    form.instance.description = json.dumps(additional_data)
            except Exception as e:
                # خطأ في تحميل أو تحديث البيانات JSON
                form.instance.description = json.dumps(additional_data)
        else:
            # إذا كان الوصف نصياً عادياً، نحتفظ به ونضيف البيانات الإضافية
            original_description = form.instance.description

            # التعامل مع الحالة حيث قد تكون additional_data ليست قاموسًا بعد sanitize_for_json
            if isinstance(additional_data, dict):
                additional_data["original_description"] = original_description
                form.instance.description = json.dumps(additional_data)
            else:
                # إذا لم تكن additional_data قاموسًا، إنشاء قاموس جديد
                form.instance.description = json.dumps(
                    {
                        "data": additional_data,
                        "original_description": original_description,
                    }
                )

        messages.success(self.request, "تم تحديث طلب التسعير بنجاح.")
        return super().form_valid(form)

    def get_initial(self):
        """تعيين القيم الأولية للنموذج"""
        initial = super().get_initial()
        order = self.get_object()

        # استخراج البيانات الإضافية من الوصف إذا كانت موجودة
        if order.description and order.description.startswith("{"):
            try:
                additional_data = json.loads(order.description)

                # تعيين القيم الأولية للحقول الإضافية
                if "product_type" in additional_data:
                    initial["product_type"] = additional_data["product_type"]

                if "custom_size" in additional_data and additional_data["custom_size"]:
                    initial["custom_size_width"] = additional_data["custom_size"].get(
                        "width"
                    )
                    initial["custom_size_height"] = additional_data["custom_size"].get(
                        "height"
                    )

                if "open_size" in additional_data and additional_data["open_size"]:
                    initial["open_size_width"] = additional_data["open_size"].get(
                        "width"
                    )
                    initial["open_size_height"] = additional_data["open_size"].get(
                        "height"
                    )

                if "binding_type" in additional_data:
                    initial["binding_type"] = additional_data["binding_type"]

                if "binding_side" in additional_data:
                    initial["binding_side"] = additional_data["binding_side"]

                if "paper_weight" in additional_data:
                    initial["paper_weight"] = additional_data["paper_weight"]

                if "paper_supplier" in additional_data:
                    initial["paper_supplier"] = additional_data["paper_supplier"]

                if "paper_price" in additional_data:
                    initial["paper_price"] = additional_data["paper_price"]

                if "zinc_plates_count" in additional_data:
                    initial["zinc_plates_count"] = additional_data["zinc_plates_count"]

                if "internal_page_count" in additional_data:
                    initial["internal_page_count"] = additional_data[
                        "internal_page_count"
                    ]

                # إذا كان هناك وصف أصلي، نستخدمه بدلاً من البيانات المخزنة بتنسيق JSON
                if "original_description" in additional_data:
                    initial["description"] = additional_data["original_description"]
            except:
                # في حالة حدوث خطأ، نستخدم الوصف كما هو
                pass

        # تعيين عدد صفحات المحتوى الداخلي إذا كان موجوداً
        try:
            internal_content = order.internal_content
            if internal_content:
                initial["internal_page_count"] = internal_content.page_count
        except InternalContent.DoesNotExist:
            pass

        return initial

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["title"] = "تعديل طلب التسعير"

        # إضافة الحقول المتخصصة
        context["paper_type_weights_json"] = self.get_paper_type_weights_json()

        # استخدام الموردين المفلترين (الحل الجذري)
        from .supplier_filters import get_printing_suppliers, get_ctp_suppliers, get_coating_suppliers

        context["plate_suppliers"] = get_ctp_suppliers()
        context["coating_suppliers"] = get_coating_suppliers()
        context["plate_sizes"] = (
            PlateSize.objects.all() if hasattr(PlateSize, "objects") else []
        )

        # إضافة موردي المطابع المفلترين
        context["printing_suppliers"] = get_printing_suppliers()

        # إضافة موردي خدمات الطباعة إلى السياق
        context["finishing_suppliers"] = Supplier.objects.filter(
            is_active=True
        )  # مؤقت - جميع الموردين

        return context

    def get_paper_type_weights_json(self):
        """تجهيز دكشنري أنواع الورق والأوزان مع تجميع الأنواع المتشابهة"""
        try:
            if hasattr(PaperType, "objects") and PaperType.objects is not None:
                paper_types = PaperType.objects.all()
            else:
                from .models import PaperType as RealPaperType

                paper_types = RealPaperType.objects.all()
        except Exception:
            paper_types = []

        # تجميع أنواع الورق حسب الاسم
        grouped_paper_types = {}

        for pt in paper_types:
            # استخراج الاسم الأساسي (الكلمة الأولى من الاسم)
            base_name = pt.name.split()[0].strip()

            # إنشاء مفتاح مركب من الاسم الأساسي
            key = base_name

            # إذا لم يكن المفتاح موجودًا، أنشئ قائمة جديدة
            if key not in grouped_paper_types:
                # نستخدم أول معرف نجده لهذا النوع
                grouped_paper_types[key] = {
                    "id": pt.id,
                    "name": base_name,
                    "weights": [],
                }

            # إضافة الوزن إلى قائمة الأوزان إذا لم يكن موجودًا بالفعل
            if pt.gsm not in grouped_paper_types[key]["weights"]:
                grouped_paper_types[key]["weights"].append(pt.gsm)

        # تحويل القاموس إلى الصيغة المطلوبة للـ JSON
        paper_type_weights = {}
        for key, data in grouped_paper_types.items():
            pt_id = str(data["id"])
            paper_type_weights[pt_id] = sorted(
                data["weights"]
            )  # ترتيب الأوزان تصاعديًا

        return json.dumps(paper_type_weights)


class PricingOrderDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """عرض حذف طلب التسعير"""

    model = PricingOrder
    template_name = "pricing/pricing_confirm_delete.html"
    success_url = reverse_lazy("pricing:pricing_order_list")

    def test_func(self):
        """التحقق من صلاحية المستخدم"""
        return self.request.user.is_admin

    def delete(self, request, *args, **kwargs):
        """حذف طلب التسعير"""
        messages.success(request, "تم حذف طلب التسعير بنجاح.")
        return super().delete(request, *args, **kwargs)


class PricingOrderApproveView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """عرض اعتماد طلب التسعير"""

    model = PricingOrder
    form_class = PricingOrderApproveForm
    template_name = "pricing/pricing_approve.html"

    def test_func(self):
        """التحقق من صلاحية المستخدم"""
        return self.request.user.is_admin or self.request.user.is_supervisor

    def form_valid(self, form):
        """اعتماد طلب التسعير"""
        form.instance.is_approved = True
        form.instance.approved_by = self.request.user
        form.instance.approved_at = timezone.now()
        form.instance.status = "approved"
        messages.success(self.request, "تم اعتماد طلب التسعير بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.pk})


class PricingOrderExecuteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """عرض تنفيذ طلب التسعير"""

    def test_func(self):
        """التحقق من صلاحية المستخدم"""
        order = get_object_or_404(PricingOrder, pk=self.kwargs["pk"])
        return (
            self.request.user.is_admin
            or self.request.user.is_supervisor
            or self.request.user == order.created_by
        )

    def post(self, request, *args, **kwargs):
        """تنفيذ طلب التسعير"""
        order = get_object_or_404(PricingOrder, pk=kwargs["pk"])

        if not order.is_approved:
            messages.error(request, "يجب اعتماد الطلب قبل تنفيذه.")
            return redirect("pricing_detail", pk=order.pk)

        order.is_executed = True
        order.executed_at = timezone.now()
        order.status = "executed"
        order.save()

        messages.success(request, "تم تنفيذ طلب التسعير بنجاح.")
        return redirect("pricing_detail", pk=order.pk)


class PricingOrderPDFView(LoginRequiredMixin, DetailView):
    """عرض تصدير طلب التسعير بصيغة PDF"""

    model = PricingOrder

    def get(self, request, *args, **kwargs):
        """إنشاء ملف PDF للطلب"""
        order = self.get_object()

        # هنا يتم إنشاء ملف PDF باستخدام مكتبة ReportLab
        # يمكن تنفيذ هذا الجزء لاحقًا

        messages.info(request, "جاري تطوير ميزة تصدير PDF.")
        return redirect("pricing_detail", pk=order.pk)


class InternalContentCreateView(LoginRequiredMixin, CreateView):
    """عرض إنشاء محتوى داخلي للطلب"""

    model = InternalContent
    form_class = InternalContentForm
    template_name = "pricing/internal_content_form.html"

    def dispatch(self, request, *args, **kwargs):
        """التحقق من عدم وجود محتوى داخلي مسبق"""
        self.pricing_order = get_object_or_404(PricingOrder, pk=kwargs["pk"])

        try:
            if self.pricing_order.internal_content:
                messages.error(request, "يوجد بالفعل محتوى داخلي لهذا الطلب.")
                return redirect("pricing_detail", pk=self.pricing_order.pk)
        except InternalContent.DoesNotExist:
            pass

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """ربط المحتوى الداخلي بالطلب"""
        form.instance.order = self.pricing_order
        messages.success(self.request, "تم إضافة المحتوى الداخلي بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.pricing_order.pk})

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["pricing_order"] = self.pricing_order
        context["title"] = "إضافة محتوى داخلي"
        return context


class InternalContentUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث المحتوى الداخلي للطلب"""

    model = InternalContent
    form_class = InternalContentForm
    template_name = "pricing/internal_content_form.html"

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.order.pk})

    def form_valid(self, form):
        """تحديث المحتوى الداخلي"""
        messages.success(self.request, "تم تحديث المحتوى الداخلي بنجاح.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["pricing_order"] = self.object.order
        context["title"] = "تعديل المحتوى الداخلي"
        return context


class OrderFinishingCreateView(LoginRequiredMixin, CreateView):
    """عرض إضافة خدمات مابعد الطباعة للطلب"""

    model = OrderFinishing
    form_class = OrderFinishingForm
    template_name = "pricing/order_finishing_form.html"

    def dispatch(self, request, *args, **kwargs):
        """الحصول على طلب التسعير"""
        self.pricing_order = get_object_or_404(PricingOrder, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """ربط خدمة خدمات مابعد الطباعة بالطلب"""
        form.instance.order = self.pricing_order

        # حساب السعر الإجمالي (إذا كان الحقل موجود في النموذج)
        # form.instance.total_price = form.instance.quantity * form.instance.unit_price

        messages.success(self.request, "تم إضافة خدمة خدمات مابعد الطباعة بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.pricing_order.pk})

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["pricing_order"] = self.pricing_order
        context["title"] = "إضافة خدمات مابعد الطباعة"
        return context


class OrderFinishingUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث خدمات مابعد الطباعة للطلب"""

    model = OrderFinishing
    form_class = OrderFinishingForm
    template_name = "pricing/order_finishing_form.html"

    def form_valid(self, form):
        """تحديث خدمة خدمات مابعد الطباعة"""
        # حساب السعر الإجمالي (إذا كان الحقل موجود في النموذج)
        # form.instance.total_price = form.instance.quantity * form.instance.unit_price

        messages.success(self.request, "تم تحديث خدمة خدمات مابعد الطباعة بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.order.pk})

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["pricing_order"] = self.object.order
        context["title"] = "تعديل خدمات مابعد الطباعة"
        return context


class OrderFinishingDeleteView(LoginRequiredMixin, DeleteView):
    """عرض حذف خدمات مابعد الطباعة للطلب"""

    model = OrderFinishing
    template_name = "pricing/order_finishing_confirm_delete.html"

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.order.pk})

    def delete(self, request, *args, **kwargs):
        """حذف خدمة خدمات مابعد الطباعة"""
        messages.success(request, "تم حذف خدمة خدمات مابعد الطباعة بنجاح.")
        return super().delete(request, *args, **kwargs)


class ExtraExpenseCreateView(LoginRequiredMixin, CreateView):
    """عرض إضافة مصروف إضافي للطلب"""

    model = ExtraExpense
    form_class = ExtraExpenseForm
    template_name = "pricing/extra_expense_form.html"

    def dispatch(self, request, *args, **kwargs):
        """الحصول على طلب التسعير"""
        self.pricing_order = get_object_or_404(PricingOrder, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """ربط المصروف الإضافي بالطلب"""
        form.instance.order = self.pricing_order
        messages.success(self.request, "تم إضافة المصروف الإضافي بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.pricing_order.pk})

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["pricing_order"] = self.pricing_order
        context["title"] = "إضافة مصروف إضافي"
        return context


class ExtraExpenseUpdateView(LoginRequiredMixin, UpdateView):
    """عرض تحديث مصروف إضافي للطلب"""

    model = ExtraExpense
    form_class = ExtraExpenseForm
    template_name = "pricing/extra_expense_form.html"

    def form_valid(self, form):
        """تحديث المصروف الإضافي"""
        messages.success(self.request, "تم تحديث المصروف الإضافي بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.order.pk})

    def get_context_data(self, **kwargs):
        """إضافة سياق إضافي للقالب"""
        context = super().get_context_data(**kwargs)
        context["pricing_order"] = self.object.order
        context["title"] = "تعديل مصروف إضافي"
        return context


class ExtraExpenseDeleteView(LoginRequiredMixin, DeleteView):
    """عرض حذف مصروف إضافي للطلب"""

    model = ExtraExpense
    template_name = "pricing/extra_expense_confirm_delete.html"

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.object.order.pk})

    def delete(self, request, *args, **kwargs):
        """حذف المصروف الإضافي"""
        messages.success(request, "تم حذف المصروف الإضافي بنجاح.")
        return super().delete(request, *args, **kwargs)


class OrderCommentCreateView(LoginRequiredMixin, CreateView):
    """عرض إضافة تعليق على الطلب"""

    model = OrderComment
    form_class = OrderCommentForm

    def dispatch(self, request, *args, **kwargs):
        """الحصول على طلب التسعير"""
        self.pricing_order = get_object_or_404(PricingOrder, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """ربط التعليق بالطلب والمستخدم"""
        form.instance.order = self.pricing_order
        form.instance.user = self.request.user
        messages.success(self.request, "تم إضافة التعليق بنجاح.")
        return super().form_valid(form)

    def get_success_url(self):
        """تحديد عنوان URL بعد النجاح"""
        return reverse("pricing_detail", kwargs={"pk": self.pricing_order.pk})


@login_required
def calculate_cost(request):
    """حساب تكلفة الطباعة"""
    if request.method == "POST":
        try:
            # استقبال طلب حساب التكلفة
            data = json.loads(request.body)

            # طباعة البيانات المستلمة للتصحيح
            # البيانات المستلمة

            # استخراج البيانات الأساسية
            order_type = data.get("order_type", "")
            quantity_str = data.get("quantity", "0")
            quantity = (
                int(quantity_str) if quantity_str and str(quantity_str).strip() else 0
            )
            paper_type_id = data.get("paper_type", "")
            paper_size_id = data.get("product_size", "")
            print_sides = data.get("print_sides", "")

            colors_front_str = data.get("colors_front", "0")
            colors_front = (
                int(colors_front_str)
                if colors_front_str and str(colors_front_str).strip()
                else 0
            )

            colors_back_str = data.get("colors_back", "0")
            colors_back = (
                int(colors_back_str)
                if colors_back_str and str(colors_back_str).strip()
                else 0
            )

            coating_type = data.get("coating_type", "")
            supplier_id = data.get("supplier", "")

            # حساب تكلفة الخامات (الورق)
            material_cost = 0
            if paper_type_id and quantity:
                try:
                    # التحقق من صحة معرف نوع الورق
                    if not str(paper_type_id).strip():
                        raise ValueError("معرف نوع الورق فارغ")

                    # البحث عن نوع الورق وسعره
                    try:
                        if (
                            hasattr(PaperType, "objects")
                            and PaperType.objects is not None
                        ):
                            paper_type = PaperType.objects.get(id=paper_type_id)
                        else:
                            from .models import PaperType as RealPaperType

                            paper_type = RealPaperType.objects.get(id=paper_type_id)
                    except Exception:
                        raise ValueError(f"نوع الورق غير موجود: {paper_type_id}")
                    paper_price = float(getattr(paper_type, "price_per_unit", 0) or 0)
                    paper_weight = getattr(paper_type, "gsm", 0)

                    # حساب عدد الأفرخ المطلوبة (تقدير بسيط)
                    sheets_per_unit = 1  # عدد الأفرخ لكل وحدة
                    if print_sides == "2":  # طباعة على الوجهين
                        sheets_per_unit = 0.5  # نصف عدد الأفرخ

                    # حساب إجمالي عدد الأفرخ
                    total_sheets = quantity * sheets_per_unit

                    # حساب تكلفة الورق
                    material_cost = total_sheets * paper_price
                    print(
                        f"تكلفة الورق: {material_cost} (الكمية: {quantity}, السعر: {paper_price}, الجرام: {paper_weight})"
                    )
                except (PaperType.DoesNotExist, ValueError) as e:
                    print(f"خطأ في البحث عن نوع الورق: {str(e)}")
                    material_cost = quantity * 0.5  # قيمة افتراضية للتكلفة
                except Exception as e:
                    print(f"خطأ عام في حساب تكلفة الورق: {str(e)}")
                    material_cost = quantity * 0.5  # قيمة افتراضية للتكلفة

            # حساب تكلفة الطباعة
            printing_cost = 0
            if supplier_id and quantity:
                try:
                    # التحقق من صحة معرف المورد
                    if not str(supplier_id).strip():
                        raise ValueError("معرف المورد فارغ")

                    # الحصول على سعر الطباعة من المورد
                    supplier = Supplier.objects.get(id=supplier_id)

                    # تقدير بسيط لتكلفة الطباعة بناءً على الكمية وعدد الألوان
                    total_colors = colors_front + (
                        colors_back if print_sides == "2" else 0
                    )
                    base_price_per_1000 = 100.0  # سعر افتراضي للطباعة لكل 1000 وحدة

                    # محاولة الحصول على سعر الماكينة من الخدمات
                    # مؤقت - معطل حتى يتم حل مشكلة SupplierService
                    # press_service = SupplierService.objects.filter(
                    #     supplier=supplier,
                    #     service_type__in=['offset_printing', 'digital_printing'],
                    #     is_active=True
                    # ).first()

                    # if press_service:
                    #     base_price_per_1000 = float(press_service.unit_price or 100)

                    # حساب تكلفة الطباعة
                    printing_cost = (
                        (quantity / 1000) * base_price_per_1000 * max(1, total_colors)
                    )

                    # إضافة تكلفة الإعداد
                    # مؤقت - معطل حتى يتم حل مشكلة SupplierService
                    # setup_cost = getattr(press_service, 'setup_cost', 50)
                    # if setup_cost is not None:
                    #     printing_cost += float(setup_cost)
                    # else:
                    printing_cost += 50.0  # قيمة افتراضية

                    print(
                        f"تكلفة الطباعة: {printing_cost} (الكمية: {quantity}, الألوان: {total_colors}, السعر الأساسي: {base_price_per_1000})"
                    )
                except (Supplier.DoesNotExist, ValueError) as e:
                    print(f"خطأ في الحصول على المورد: {str(e)}")
                    # تقدير بسيط للتكلفة
                    printing_cost = quantity * 0.2 + (colors_front + colors_back) * 50
                except Exception as e:
                    print(f"خطأ عام في حساب تكلفة الطباعة: {str(e)}")
                    # تقدير بسيط للتكلفة
                    printing_cost = quantity * 0.2 + (colors_front + colors_back) * 50

            return JsonResponse(
                {
                    "success": True,
                    "material_cost": round(material_cost, 2),
                    "printing_cost": round(printing_cost, 2),
                    "message": "تم حساب التكلفة بنجاح",
                }
            )
        except json.JSONDecodeError as e:
            print(f"خطأ في تحليل البيانات JSON: {str(e)}")
            print(
                f"المحتوى المستلم: {request.body[:100]}"
            )  # طباعة جزء من المحتوى للتشخيص
            return JsonResponse(
                {"success": False, "error": "خطأ في تحليل البيانات المرسلة"}
            )
        except Exception as e:
            print(f"خطأ عام في حساب التكلفة: {str(e)}")
            import traceback

            traceback.print_exc()
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse(
        {"success": False, "error": "يجب استخدام طريقة POST لهذا الطلب"}
    )


@login_required
def get_plate_price(request):
    """الحصول على سعر الزنك تلقائيًا حسب المورد والمقاس"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")
            plate_size_id = request.GET.get("plate_size_id")

            if not supplier_id or not plate_size_id:
                return JsonResponse(
                    {"success": False, "error": "Missing required parameters"}
                )

            # البحث عن خدمة الزنكات المناسبة
            plate_service = PlateServiceDetails.find_plate_service(
                supplier_id, plate_size_id
            )

            if plate_service:
                return JsonResponse(
                    {
                        "success": True,
                        "plate_price": float(plate_service.price_per_plate),
                        "transportation_cost": float(plate_service.transportation_cost),
                        "min_plates_count": plate_service.min_plates_count,
                    }
                )
            else:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "No plate service found for the given supplier and plate size",
                    }
                )

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "Invalid request method"})


@login_required
def get_paper_weights(request):
    """الحصول على أوزان الورق المتاحة عند مورد محدد"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")
            paper_type_id = request.GET.get("paper_type_id")
            sheet_type = request.GET.get("sheet_type")

            if not supplier_id:
                return JsonResponse(
                    {"success": False, "error": "Missing supplier_id parameter"}
                )

            # البحث عن أوزان الورق المتاحة عند المورد
            paper_services_query = PaperServiceDetails.objects.filter(
                service__supplier_id=supplier_id, service__is_active=True
            )

            # تصفية حسب نوع الورق إذا تم تحديده
            if paper_type_id:
                # الحصول على نوع الورق الأساسي
                try:
                    if hasattr(PaperType, "objects") and PaperType.objects is not None:
                        base_paper_type = PaperType.objects.get(id=paper_type_id)
                    else:
                        from .models import PaperType as RealPaperType

                        base_paper_type = RealPaperType.objects.get(id=paper_type_id)
                    base_name = base_paper_type.name.split()[0].strip()

                    # البحث عن أنواع الورق التي تبدأ بنفس الاسم الأساسي
                    paper_services_query = paper_services_query.filter(
                        paper_type__icontains=base_name
                    )
                except PaperType.DoesNotExist:
                    pass

            # تصفية حسب مقاس الورق إذا تم تحديده
            if sheet_type:
                paper_services_query = paper_services_query.filter(
                    sheet_size=sheet_type
                )

            # استخراج الأوزان الفريدة
            paper_services = (
                paper_services_query.exclude(gsm__isnull=True).values("gsm").distinct()
            )

            # استخدام مجموعة للتأكد من عدم تكرار الأوزان
            unique_weights = set()
            weights = []

            for ps in paper_services:
                gsm = ps["gsm"]
                # التحقق من أن الوزن ليس فارغًا وأنه لم يتم إضافته من قبل
                if gsm and gsm not in unique_weights:
                    unique_weights.add(gsm)
                    weights.append({"gsm": gsm})

            # ترتيب الأوزان تصاعديًا
            weights = sorted(
                weights, key=lambda x: int(x["gsm"]) if x["gsm"].isdigit() else 0
            )

            return JsonResponse({"success": True, "weights": weights})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "Invalid request method"})


@login_required
def get_paper_sheet_types(request):
    """استرجاع مقاسات الورق المتاحة عند مورد محدد لنوع ورق محدد"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")
            paper_type_id = request.GET.get("paper_type_id")

            if not supplier_id or not paper_type_id:
                return JsonResponse(
                    {"success": False, "error": "Missing required parameters"}
                )

            # الحصول على نوع الورق الأساسي
            try:
                if hasattr(PaperType, "objects") and PaperType.objects is not None:
                    base_paper_type = PaperType.objects.get(id=paper_type_id)
                else:
                    from .models import PaperType as RealPaperType

                    base_paper_type = RealPaperType.objects.get(id=paper_type_id)
                base_name = base_paper_type.name.split()[0].strip()

                # البحث عن مقاسات الورق المتاحة عند المورد لنوع الورق المحدد
                paper_services = (
                    PaperServiceDetails.objects.filter(
                        service__supplier_id=supplier_id,
                        service__is_active=True,
                        paper_type__icontains=base_name,
                    )
                    .values("sheet_size")
                    .distinct()
                )

                # إعداد قائمة المقاسات مع أسماء العرض
                sheet_types = []
                unique_sheet_types = set()  # مجموعة للتأكد من عدم تكرار المقاسات

                for ps in paper_services:
                    sheet_type = ps["sheet_size"]
                    if sheet_type and sheet_type not in unique_sheet_types:
                        unique_sheet_types.add(
                            sheet_type
                        )  # إضافة المقاس إلى المجموعة لمنع التكرار
                        # الحصول على اسم العرض من الثنائيات المعرفة في النموذج
                        display_name = dict(PaperServiceDetails.SHEET_TYPE_CHOICES).get(
                            sheet_type, sheet_type
                        )
                        sheet_types.append(
                            {"sheet_type": sheet_type, "display_name": display_name}
                        )

                return JsonResponse({"success": True, "sheet_types": sheet_types})

            except PaperType.DoesNotExist:
                return JsonResponse({"success": False, "error": "Paper type not found"})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "Invalid request method"})


@login_required
def get_paper_origins(request):
    """استرجاع بلاد المنشأ المتاحة للورق بناءً على المورد ونوع الورق ومقاس الورق والجرام"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")
            paper_type_id = request.GET.get("paper_type_id")
            sheet_type = request.GET.get("sheet_type")
            gsm = request.GET.get("gsm")

            if not supplier_id or not paper_type_id or not sheet_type or not gsm:
                return JsonResponse(
                    {"success": False, "error": "Missing required parameters"}
                )

            # الحصول على نوع الورق الأساسي
            try:
                if hasattr(PaperType, "objects") and PaperType.objects is not None:
                    base_paper_type = PaperType.objects.get(id=paper_type_id)
                else:
                    from .models import PaperType as RealPaperType
                    base_paper_type = RealPaperType.objects.get(id=paper_type_id)
                base_name = base_paper_type.name.split()[0].strip()

                # بناء استعلام أكثر مرونة للبحث عن بلاد المنشأ المتاحة
                # نبدأ باستعلام أساسي
                query = Q(
                    service__supplier_id=supplier_id,
                    service__is_active=True,
                    sheet_size=sheet_type,
                    gsm=gsm,
                )

                # نضيف شرط البحث عن نوع الورق بشكل أكثر مرونة
                query &= Q(paper_type__icontains=base_name)

                # نستبعد القيم الفارغة لبلد المنشأ
                paper_services = (
                    PaperServiceDetails.objects.filter(query)
                    .exclude(
                        Q(country_of_origin="") | Q(country_of_origin__isnull=True)
                    )
                    .values("country_of_origin")
                    .distinct()
                )

                # استخدام Set للتأكد من عدم تكرار بلاد المنشأ
                unique_origins = set()

                # تجميع بلاد المنشأ الفريدة
                for ps in paper_services:
                    if ps["country_of_origin"]:
                        unique_origins.add(ps["country_of_origin"])

                # تحويل المجموعة إلى قائمة من القواميس
                origins = [{"country_of_origin": country} for country in unique_origins]

                # إذا لم يتم العثور على أي بلد منشأ، نحاول البحث بشكل أكثر مرونة
                if not origins:
                    # نبحث فقط حسب المورد والجرام ومقاس الورق
                    flexible_query = Q(
                        service__supplier_id=supplier_id,
                        service__is_active=True,
                        gsm=gsm,
                    )

                    paper_services = (
                        PaperServiceDetails.objects.filter(flexible_query)
                        .exclude(
                            Q(country_of_origin="") | Q(country_of_origin__isnull=True)
                        )
                        .values("country_of_origin")
                        .distinct()
                    )

                    # استخدام Set للتأكد من عدم تكرار بلاد المنشأ
                    unique_origins = set()

                    # تجميع بلاد المنشأ الفريدة
                    for ps in paper_services:
                        if ps["country_of_origin"]:
                            unique_origins.add(ps["country_of_origin"])

                    # تحويل المجموعة إلى قائمة من القواميس
                    origins = [
                        {"country_of_origin": country} for country in unique_origins
                    ]

                    # إذا لم نجد أي نتائج، نعرض جميع بلاد المنشأ المتاحة لهذا المورد
                    if not origins:
                        paper_services = (
                            PaperServiceDetails.objects.filter(
                                service__supplier_id=supplier_id,
                                service__is_active=True,
                            )
                            .exclude(
                                Q(country_of_origin="")
                                | Q(country_of_origin__isnull=True)
                            )
                            .values("country_of_origin")
                            .distinct()
                        )

                        # استخدام Set للتأكد من عدم تكرار بلاد المنشأ
                        unique_origins = set()

                        # تجميع بلاد المنشأ الفريدة
                        for ps in paper_services:
                            if ps["country_of_origin"]:
                                unique_origins.add(ps["country_of_origin"])

                        # تحويل المجموعة إلى قائمة من القواميس
                        origins = [
                            {"country_of_origin": country} for country in unique_origins
                        ]

                # تأكد إضافي من عدم وجود تكرار
                unique_countries = set()
                filtered_origins = []
                for origin in origins:
                    country = origin["country_of_origin"]
                    if country and country not in unique_countries:
                        unique_countries.add(country)
                        filtered_origins.append(origin)

                # إضافة بيانات تصحيح للتحقق من الاستعلام
                debug_info = {
                    "supplier_id": supplier_id,
                    "paper_type_id": paper_type_id,
                    "base_name": base_name,
                    "sheet_type": sheet_type,
                    "gsm": gsm,
                    "origins_count": len(filtered_origins),
                }

                return JsonResponse(
                    {"success": True, "origins": filtered_origins, "debug": debug_info}
                )

            except PaperType.DoesNotExist:
                return JsonResponse({"success": False, "error": "Paper type not found"})

        except Exception as e:
            import traceback

            print(f"خطأ في get_paper_origins: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "Invalid request method"})


@login_required
def get_plate_sizes(request):
    """API للحصول على مقاسات الزنكات المتاحة للمورد"""
    try:
        supplier_id = request.GET.get("supplier_id")
        
        if not supplier_id:
            return JsonResponse({"success": False, "error": "معرف المورد مطلوب"})
        
        # استيراد النموذج من supplier
        from supplier.models import PlateServiceDetails
        
        # جلب مقاسات الزنكات المتاحة للمورد
        plate_services = PlateServiceDetails.objects.filter(
            service__supplier_id=supplier_id,
            service__is_active=True
        ).select_related('service')
        
        plate_sizes_data = []
        seen_sizes = set()  # لتجنب التكرار
        
        for service in plate_services:
            if service.plate_size and service.plate_size not in seen_sizes:
                seen_sizes.add(service.plate_size)
                
                # تحسين عرض أسماء المقاسات
                size_display = service.plate_size
                if service.plate_size in ["35x50", "35.00x50.00", "quarter_sheet"]:
                    size_display = "ربع فرخ (35×50 سم)"
                elif service.plate_size in ["50x70", "50.00x70.00", "half_sheet"]:
                    size_display = "نصف فرخ (50×70 سم)"
                elif service.plate_size in ["70x100", "70.00x100.00", "full_sheet"]:
                    size_display = "فرخ كامل (70×100 سم)"
                elif service.plate_size == "custom":
                    size_display = "مقاس مخصص"
                
                plate_sizes_data.append({
                    "id": service.id,
                    "plate_size": service.plate_size,
                    "name": size_display,
                    "price": float(service.price_per_plate) if service.price_per_plate else 0,
                    "service_name": service.service.name if service.service.name else size_display
                })
        
        return JsonResponse({
            "success": True,
            "plate_sizes": plate_sizes_data
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في جلب مقاسات الزنكات: {str(e)}", exc_info=True)
        return JsonResponse({
            "success": False, 
            "error": "خطأ في جلب مقاسات الزنكات"
        })


@login_required  
def get_press_size(request):
    """API للحصول على مقاس الماكينة"""
    try:
        # الحصول على press_id من query parameters
        press_id = request.GET.get('press_id')
        if not press_id:
            return JsonResponse({
                "success": False,
                "error": "معرف الماكينة مطلوب"
            })
        
        # تحويل press_id إلى int
        press_id = int(press_id)
        
        # قيم افتراضية للمكائن الشائعة (بناءً على ID)
        default_sizes = {
            1: {"width": 35, "height": 50, "name": "ماكينة ربع فرخ"},
            2: {"width": 50, "height": 70, "name": "ماكينة نصف فرخ"}, 
            3: {"width": 70, "height": 100, "name": "ماكينة فرخ كامل"},
        }
        
        # استخدام القيم الافتراضية أولاً
        press_size = default_sizes.get(press_id, {"width": 35, "height": 50, "name": "ماكينة ربع فرخ"})
        
        return JsonResponse({
            "success": True,
            "press_size": {
                "width": press_size["width"],
                "height": press_size["height"]
            },
            "service_name": press_size["name"]
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في جلب مقاس الماكينة: {str(e)}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": "خطأ في جلب مقاس الماكينة"
        })


@login_required
def get_paper_price(request):
    """API لجلب سعر الورق بناءً على النوع والوزن والمورد ومقاس الورق وبلد المنشأ"""
    paper_type_id = request.GET.get("paper_type_id")
    gsm = request.GET.get("gsm")
    supplier_id = request.GET.get("supplier_id")
    sheet_type = request.GET.get("sheet_type")
    country_of_origin = request.GET.get("country_of_origin", "")

    # طباعة المعلومات المستلمة للتصحيح
    print(
        f"معلومات طلب سعر الورق: نوع={paper_type_id}, جرام={gsm}, مورد={supplier_id}, مقاس={sheet_type}, بلد={country_of_origin}"
    )

    # التحقق من وجود المعلومات المطلوبة
    missing_fields = []
    if not paper_type_id:
        missing_fields.append("نوع الورق")
    if not gsm:
        missing_fields.append("جرام الورق")
    if not supplier_id:
        missing_fields.append("مورد الورق")
    if not sheet_type:
        missing_fields.append("مقاس الورق")

    if missing_fields:
        error_message = f"الحقول التالية مطلوبة: {', '.join(missing_fields)}"
        print(f"خطأ: {error_message}")
        return JsonResponse({"success": False, "error": error_message})

    try:
        # الحصول على نوع الورق الأساسي
        try:
            if hasattr(PaperType, "objects") and PaperType.objects is not None:
                base_paper_type = PaperType.objects.get(id=paper_type_id)
            else:
                from .models import PaperType as RealPaperType

                base_paper_type = RealPaperType.objects.get(id=paper_type_id)
        except Exception:
            raise ValueError(f"نوع الورق غير موجود: {paper_type_id}")
        base_name = base_paper_type.name.split()[0].strip()
        supplier_name = ""

        # طباعة معلومات نوع الورق للتصحيح
        print(f"نوع الورق: {base_paper_type.name}, الاسم الأساسي: {base_name}")

        # البحث عن نوع الورق المطابق بالاسم الأساسي والوزن
        try:
            if hasattr(PaperType, "objects") and PaperType.objects is not None:
                matching_paper_type = PaperType.objects.filter(
                    name__istartswith=base_name, gsm=gsm, is_active=True
                ).first()
            else:
                from .models import PaperType as RealPaperType

                matching_paper_type = RealPaperType.objects.filter(
                    name__istartswith=base_name, gsm=gsm
                ).first()
        except Exception:
            matching_paper_type = None

        if matching_paper_type:
            # وجدنا نوع ورق مطابق بالوزن المطلوب
            price = matching_paper_type.price_per_unit
            print(
                f"تم العثور على نوع ورق مطابق: {matching_paper_type.name}, السعر: {price}"
            )

            # إذا تم تحديد المورد، نحاول الحصول على السعر منه
            if supplier_id:
                try:
                    supplier = Supplier.objects.get(id=supplier_id)
                    supplier_name = supplier.name
                    print(f"المورد: {supplier_name}")

                    # مؤقت - معطل حتى يتم حل مشكلة SupplierService
                    # استخدام السعر الافتراضي من نوع الورق
                    matching_service = None

                    if matching_service:
                        # الحصول على اسم العرض لمقاس الورق
                        sheet_type_display = dict(
                            PaperServiceDetails.SHEET_TYPE_CHOICES
                        ).get(sheet_type, sheet_type)

                        # استخدام سعر الخدمة المطابقة من المورد
                        return JsonResponse(
                            {
                                "success": True,
                                "price": float(matching_service.unit_price),
                                "supplier_name": supplier_name,
                                "gsm": gsm,
                                "paper_type_name": matching_paper_type.name,
                                "service_name": matching_service.name,
                                "service_id": matching_service.id,
                                "sheet_type": sheet_type,
                                "sheet_type_display": sheet_type_display,
                                "country_of_origin": matching_service.paper_details.country_of_origin,
                                "source": "supplier_service",
                            }
                        )
                except Exception as e:
                    # معالجة أي أخطاء متعلقة بالمورد
                    print(f"خطأ في الحصول على بيانات المورد: {str(e)}")

            # إذا وصلنا إلى هنا، نستخدم سعر نوع الورق المطابق
            return JsonResponse(
                {
                    "success": True,
                    "price": float(price),
                    "supplier_name": supplier_name,
                    "gsm": gsm,
                    "paper_type_name": matching_paper_type.name,
                    "sheet_type": sheet_type,
                    "sheet_type_display": dict(
                        PaperServiceDetails.SHEET_TYPE_CHOICES
                    ).get(sheet_type, sheet_type),
                    "country_of_origin": country_of_origin,
                    "source": "exact_match",
                }
            )
        else:
            # لم نجد نوع ورق مطابق بالوزن المطلوب
            print(f"لم يتم العثور على نوع ورق {base_name} بوزن {gsm} جم")
            return JsonResponse(
                {
                    "success": False,
                    "error": f"لم يتم العثور على نوع ورق {base_name} بوزن {gsm} جم",
                    "message": "يرجى إضافة هذا النوع من الورق أولاً",
                }
            )

    except PaperType.DoesNotExist:
        print(f"نوع الورق غير موجود: {paper_type_id}")
        return JsonResponse({"success": False, "error": "نوع الورق غير موجود"})
    except Exception as e:
        # معالجة أي أخطاء أخرى غير متوقعة
        print(f"خطأ غير متوقع في get_paper_price: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "حدث خطأ أثناء معالجة الطلب: خطأ في العملية"}
        )


def sanitize_for_json(data):
    """
    تحويل الكائنات المعقدة مثل Supplier و PaperType إلى قيم بسيطة قابلة للتحويل إلى JSON
    """
    if data is None:
        return None

    if isinstance(data, dict):
        sanitized_dict = {}
        for key, value in data.items():
            sanitized_dict[key] = sanitize_for_json(value)
        return sanitized_dict

    elif isinstance(data, list):
        return [sanitize_for_json(item) for item in data]

    # التعامل مع كائنات Django
    if hasattr(data, "id") and hasattr(data, "_meta"):
        # إذا كان كائن Django، أعد المعرف كنص
        return str(data.id)

    # تحويل الأنواع غير المتوافقة مع JSON إلى نصوص
    if isinstance(data, (datetime.date, datetime.datetime)):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return str(data)

    # إعادة القيمة كما هي إذا كانت من الأنواع الأساسية
    return data


@login_required
def get_suppliers_by_service(request):
    """API لجلب الموردين حسب نوع الخدمة"""
    if request.method == "GET":
        try:
            service_type = request.GET.get("service_type")

            if not service_type:
                return JsonResponse({"success": False, "error": "نوع الخدمة مطلوب"})

            # البحث عن الموردين الذين يقدمون هذه الخدمة
            suppliers = (
                Supplier.objects.filter(
                    supplierservice__service_type=service_type,
                    supplierservice__is_active=True,
                    is_active=True,
                )
                .distinct()
                .values("id", "name")
            )

            return JsonResponse({"success": True, "suppliers": list(suppliers)})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


@login_required
def clear_pricing_form_data(request):
    """مسح بيانات نموذج التسعير المحفوظة في الجلسة"""
    if "pricing_form_data" in request.session:
        del request.session["pricing_form_data"]

    return redirect("pricing_add")


@login_required
def coating_services_api(request):
    """API لجلب خدمات التغطية"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")

            if not supplier_id:
                return JsonResponse({"success": False, "error": "معرف المورد مطلوب"})

            # البحث عن خدمات التغطية للمورد المحدد
            # مؤقت - معطل حتى يتم حل مشكلة SupplierService
            services = []  # SupplierService.objects.filter(
            #     supplier_id=supplier_id,
            #     service_type='finishing',
            #     finishing_details__finishing_type='coating',
            #     is_active=True
            # ).values('id', 'name', 'unit_price')

            return JsonResponse({"success": True, "services": list(services)})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


@login_required
def folding_services_api(request):
    """API لجلب خدمات الريجة"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")

            if not supplier_id:
                return JsonResponse({"success": False, "error": "معرف المورد مطلوب"})

            # البحث عن خدمات الريجة للمورد المحدد
            # مؤقت - معطل حتى يتم حل مشكلة SupplierService
            services = []  # SupplierService.objects.filter(
            #     supplier_id=supplier_id,
            #     service_type='finishing',
            #     finishing_details__finishing_type='folding',
            #     is_active=True
            # ).values('id', 'name', 'unit_price')

            return JsonResponse({"success": True, "services": list(services)})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


@login_required
def die_cut_services_api(request):
    """API لجلب خدمات التكسير"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")

            if not supplier_id:
                return JsonResponse({"success": False, "error": "معرف المورد مطلوب"})

            # البحث عن خدمات التكسير للمورد المحدد
            # مؤقت - معطل حتى يتم حل مشكلة SupplierService
            services = []  # SupplierService.objects.filter(
            #     supplier_id=supplier_id,
            #     service_type='finishing',
            #     finishing_details__finishing_type='die_cut',
            #     is_active=True
            # ).values('id', 'name', 'unit_price')

            return JsonResponse({"success": True, "services": list(services)})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


@login_required
def spot_uv_services_api(request):
    """API لجلب خدمات سبوت يوفي"""
    if request.method == "GET":
        try:
            supplier_id = request.GET.get("supplier_id")

            if not supplier_id:
                return JsonResponse({"success": False, "error": "معرف المورد مطلوب"})

            # البحث عن خدمات سبوت يوفي للمورد المحدد
            # مؤقت - معطل حتى يتم حل مشكلة SupplierService
            services = []  # SupplierService.objects.filter(
            #     supplier_id=supplier_id,
            #     service_type='finishing',
            #     finishing_details__finishing_type='spot_uv',
            #     is_active=True
            # ).values('id', 'name', 'unit_price')

            return JsonResponse({"success": True, "services": list(services)})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


# تم حذف الدالة المكررة - استخدم الدالة الموجودة في نهاية الملف


@login_required
def get_press_price(request):
    """API لجلب سعر ماكينة الطباعة"""
    if request.method == "GET":
        try:
            press_id = request.GET.get("press_id")

            if not press_id:
                return JsonResponse({"success": False, "error": "معرف الماكينة مطلوب"})

            # البحث عن سعر الماكينة
            try:
                # البحث في خدمات الأوفست والديجيتال
                from supplier.models import OffsetPrintingDetails, DigitalPrintingDetails
                
                # استخراج معرف الخدمة الفعلي من press_id
                actual_service_id = press_id
                if press_id.startswith('offset_service_'):
                    actual_service_id = press_id.replace('offset_service_', '')
                elif press_id.startswith('digital_service_'):
                    actual_service_id = press_id.replace('digital_service_', '')
                elif press_id.startswith('offset_'):
                    actual_service_id = press_id.replace('offset_', '')
                elif press_id.startswith('digital_'):
                    actual_service_id = press_id.replace('digital_', '')
                
                # البحث في خدمات الأوفست
                try:
                    offset_service = OffsetPrintingDetails.objects.get(
                        id=actual_service_id,
                        service__is_active=True
                    )
                    
                    # الحصول على سعر التراج من خدمة الأوفست
                    price_per_1000 = float(offset_service.impression_cost_per_1000) if offset_service.impression_cost_per_1000 else 100.0
                    
                    return JsonResponse({
                        "success": True,
                        "price_per_1000": price_per_1000,
                        "unit_price": price_per_1000,
                        "price": price_per_1000,
                        "service_name": offset_service.service.name if offset_service.service else "خدمة أوفست",
                        "machine_type": offset_service.machine_type
                    })
                    
                except OffsetPrintingDetails.DoesNotExist:
                    # البحث في خدمات الديجيتال
                    try:
                        digital_service = DigitalPrintingDetails.objects.get(
                            id=actual_service_id,
                            service__is_active=True
                        )
                        
                        # الحصول على سعر النسخة من خدمة الديجيتال
                        price_per_copy = float(digital_service.price_per_copy) if digital_service.price_per_copy else 0.15
                        price_per_1000 = price_per_copy * 1000  # تحويل لسعر لكل 1000
                        
                        return JsonResponse({
                            "success": True,
                            "price_per_1000": price_per_1000,
                            "price_per_copy": price_per_copy,
                            "unit_price": price_per_copy,
                            "price": price_per_1000,
                            "service_name": digital_service.service.name if digital_service.service else "خدمة ديجيتال",
                            "machine_type": digital_service.machine_type
                        })
                        
                    except DigitalPrintingDetails.DoesNotExist:
                        # إرجاع سعر افتراضي إذا لم توجد الخدمة
                        return JsonResponse({
                            "success": True,
                            "price_per_1000": 100.0,
                            "unit_price": 100.0,
                            "price": 100.0,
                            "service_name": "خدمة افتراضية",
                            "note": "سعر افتراضي - لم يتم العثور على الخدمة"
                        })
            except Exception:  # SupplierService.DoesNotExist:
                print(f"الماكينة غير موجودة بالمعرف: {press_id}")
                return JsonResponse({"success": False, "error": "الماكينة غير موجودة"})

        except Exception as e:
            import traceback

            print(f"خطأ في get_press_price: {str(e)}")
            traceback.print_exc()
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


@login_required
def get_press_details(request):
    """API لجلب تفاصيل ماكينة الطباعة"""
    if request.method == "GET":
        try:
            press_id = request.GET.get("press_id")

            if not press_id:
                return JsonResponse({"success": False, "error": "معرف الماكينة مطلوب"})

            # البحث عن تفاصيل الماكينة
            try:
                # مؤقت - معطل حتى يتم حل مشكلة SupplierService
                press = None  # SupplierService.objects.get(
                #     id=press_id,
                #     service_type='offset_printing',
                #     is_active=True
                # )

                details = {
                    "name": press.name,
                    "price": float(press.unit_price),
                    "supplier": press.supplier.name,
                }

                # إضافة معلومات الحجم الافتراضية
                size_details = {
                    "width": 35,
                    "height": 50,
                    "max_width": 34,
                    "max_height": 49,
                }

                # إضافة تفاصيل الطباعة الأوفست إذا كانت متوفرة
                try:
                    offset_details = press.offset_details
                    details.update(
                        {
                            "machine_size": offset_details.get_machine_size_display(),
                            "max_width": offset_details.max_width,
                            "max_height": offset_details.max_height,
                            "colors": offset_details.colors,
                            "partial_price": float(offset_details.partial_price)
                            if offset_details.partial_price
                            else None,
                        }
                    )

                    # تحديث معلومات الحجم من تفاصيل الأوفست
                    if hasattr(offset_details, "width") and offset_details.width:
                        size_details["width"] = offset_details.width
                    if hasattr(offset_details, "height") and offset_details.height:
                        size_details["height"] = offset_details.height
                    if (
                        hasattr(offset_details, "max_width")
                        and offset_details.max_width
                    ):
                        size_details["max_width"] = offset_details.max_width
                    if (
                        hasattr(offset_details, "max_height")
                        and offset_details.max_height
                    ):
                        size_details["max_height"] = offset_details.max_height
                except Exception as e:
                    print(f"خطأ في الحصول على تفاصيل الأوفست: {str(e)}")

                return JsonResponse(
                    {"success": True, "details": details, "size_details": size_details}
                )
            except Exception:  # SupplierService.DoesNotExist:
                return JsonResponse({"success": False, "error": "الماكينة غير موجودة"})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


@login_required
def get_press_size(request):
    """API لجلب مقاس ماكينة الطباعة"""
    if request.method == "GET":
        try:
            press_id = request.GET.get("press_id")

            if not press_id:
                return JsonResponse({"success": False, "error": "معرف الماكينة مطلوب"})

            # البحث عن مقاس الماكينة
            try:
                # البحث في خدمات الأوفست والديجيتال
                from supplier.models import OffsetPrintingDetails, DigitalPrintingDetails
                
                # الأبعاد الافتراضية
                width = 70.0
                height = 100.0
                
                # استخراج معرف الخدمة الفعلي من press_id
                actual_service_id = press_id
                if press_id.startswith('offset_service_'):
                    actual_service_id = press_id.replace('offset_service_', '')
                elif press_id.startswith('digital_service_'):
                    actual_service_id = press_id.replace('digital_service_', '')
                elif press_id.startswith('offset_'):
                    actual_service_id = press_id.replace('offset_', '')
                elif press_id.startswith('digital_'):
                    actual_service_id = press_id.replace('digital_', '')
                
                # print(f"البحث عن الخدمة: press_id={press_id}, actual_service_id={actual_service_id}")
                
                # البحث في خدمات الأوفست
                try:
                    offset_service = OffsetPrintingDetails.objects.get(
                        id=actual_service_id,
                        service__is_active=True
                    )
                    
                    # الحصول على مقاس الماكينة من إعدادات الأوفست
                    if offset_service.sheet_size:
                        from pricing.models import OffsetSheetSize
                        try:
                            sheet_size = OffsetSheetSize.objects.get(code=offset_service.sheet_size)
                            width = float(sheet_size.width_cm)
                            height = float(sheet_size.height_cm)
                            # print(f"تم العثور على مقاس أوفست: {sheet_size.name}, العرض: {width}, الارتفاع: {height}")
                        except OffsetSheetSize.DoesNotExist:
                            print(f"مقاس الأوفست غير موجود: {offset_service.sheet_size}")
                    
                except OffsetPrintingDetails.DoesNotExist:
                    # البحث في خدمات الديجيتال
                    try:
                        digital_service = DigitalPrintingDetails.objects.get(
                            id=actual_service_id,
                            service__is_active=True
                        )
                        
                        # الحصول على مقاس الماكينة من إعدادات الديجيتال
                        if digital_service.sheet_size:
                            from pricing.models import DigitalSheetSize
                            try:
                                sheet_size = DigitalSheetSize.objects.get(code=digital_service.sheet_size)
                                width = float(sheet_size.width_cm)
                                height = float(sheet_size.height_cm)
                                # print(f"تم العثور على مقاس ديجيتال: {sheet_size.name}, العرض: {width}, الارتفاع: {height}")
                            except DigitalSheetSize.DoesNotExist:
                                print(f"مقاس الديجيتال غير موجود: {digital_service.sheet_size}")
                        else:
                            # قيم افتراضية للديجيتال (A4)
                            width = 21.0
                            height = 29.7
                            
                    except DigitalPrintingDetails.DoesNotExist:
                        print(f"لم يتم العثور على خدمة طباعة بالمعرف: {press_id}")

                # print(f"مقاس الماكينة النهائي - العرض: {width}, الارتفاع: {height}")
                return JsonResponse(
                    {
                        "success": True, 
                        "press_size": {"width": width, "height": height},
                        "width": width, 
                        "height": height
                    }
                )
            except Exception:  # SupplierService.DoesNotExist:
                print(f"الماكينة غير موجودة بالمعرف: {press_id}")
                return JsonResponse({"success": False, "error": "الماكينة غير موجودة"})

        except Exception as e:
            import traceback

            print(f"خطأ في get_press_size: {str(e)}")
            traceback.print_exc()
def get_paper_suppliers(request):
    """API لجلب موردي الورق"""
    if request.method == "GET":
        try:
            # البحث عن موردي الورق النشطين
            suppliers = Supplier.objects.filter(is_active=True).values(
                "id", "name"
            )  # مؤقت - جميع الموردين

            return JsonResponse({"success": True, "suppliers": list(suppliers)})

        except Exception as e:
            return JsonResponse({"success": False, "error": "خطأ في العملية"})

    return JsonResponse({"success": False, "error": "طريقة طلب غير صالحة"})


# تم حذف الدالة المكررة - استخدم الدالة الموجودة في نهاية الملف


# ==================== Views جديدة للقائمة الجانبية ====================


@login_required
def pricing_dashboard(request):
    """لوحة تحكم التسعير الرئيسية"""
    from django.db.models import Sum, Count, Avg
    from datetime import datetime, timedelta

    # إحصائيات أساسية
    total_orders = PricingOrder.objects.count()
    pending_orders = PricingOrder.objects.filter(status="pending").count()
    approved_orders = PricingOrder.objects.filter(status="approved").count()
    executed_orders = PricingOrder.objects.filter(status="executed").count()

    # إحصائيات هذا الشهر
    current_month = timezone.now().replace(day=1)
    this_month_orders = PricingOrder.objects.filter(
        created_at__gte=current_month
    ).count()

    # إحصائيات الإيرادات
    total_revenue = (
        PricingOrder.objects.filter(status__in=["approved", "executed"]).aggregate(
            Sum("sale_price")
        )["sale_price__sum"]
        or 0
    )

    this_month_revenue = (
        PricingOrder.objects.filter(
            created_at__gte=current_month, status__in=["approved", "executed"]
        ).aggregate(Sum("sale_price"))["sale_price__sum"]
        or 0
    )

    # أهم العملاء (مثال)
    try:
        from client.models import Customer

        top_clients = (
            Customer.objects.annotate(
                orders_count=Count("pricingorder"),
                total_value=Sum("pricingorder__sale_price"),
            )
            .filter(orders_count__gt=0)
            .order_by("-total_value")[:5]
        )
    except:
        top_clients = []

    # الطلبات الحديثة
    recent_orders = PricingOrder.objects.select_related(
        "client", "created_by"
    ).order_by("-created_at")[:10]

    context = {
        "active_menu": "pricing",
        "page_title": "لوحة تحكم التسعير",
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "approved_orders": approved_orders,
        "executed_orders": executed_orders,
        "this_month_orders": this_month_orders,
        "total_revenue": total_revenue,
        "this_month_revenue": this_month_revenue,
        "avg_processing_time": 3,  # مثال
        "customer_satisfaction": 95,  # مثال
        "recent_orders": recent_orders,
        "top_clients": top_clients,
        "today": timezone.now().date(),
        "now": timezone.now(),
    }
    return render(request, "pricing/dashboard.html", context)


@login_required
def quotation_list(request):
    """قائمة عروض الأسعار"""
    # في المرحلة الحالية، سنعرض طلبات التسعير المعتمدة كعروض أسعار
    quotations = (
        PricingOrder.objects.filter(status__in=["approved", "executed"])
        .select_related("client", "created_by")
        .order_by("-created_at")
    )

    # فلترة بسيطة
    search = request.GET.get("search")
    if search:
        quotations = quotations.filter(
            Q(title__icontains=search)
            | Q(order_number__icontains=search)
            | Q(description__icontains=search)
        )

    client_id = request.GET.get("client")
    if client_id:
        quotations = quotations.filter(client_id=client_id)

    date_from = request.GET.get("date_from")
    if date_from:
        quotations = quotations.filter(created_at__date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        quotations = quotations.filter(created_at__date__lte=date_to)

    # تعريف headers للجدول الموحد
    headers = [
        {
            "key": "order_number",
            "label": "رقم العرض",
            "sortable": True,
            "class": "text-center",
        },
        {
            "key": "created_at",
            "label": "تاريخ الإنشاء",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
        },
        {
            "key": "client",
            "label": "العميل",
            "template": "pricing/columns/client_column.html",
        },
        {"key": "title", "label": "العنوان", "sortable": True, "class": "text-start"},
        {
            "key": "order_type",
            "label": "نوع الطباعة",
            "template": "pricing/columns/order_type_column.html",
        },
        {
            "key": "quantity",
            "label": "الكمية",
            "sortable": True,
            "class": "text-center",
        },
        {
            "key": "sale_price",
            "label": "سعر البيع",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "decimals": 2,
        },
        {
            "key": "status",
            "label": "الحالة",
            "template": "pricing/columns/status_column.html",
        },
        {
            "key": "created_by.get_full_name",
            "label": "المنشئ",
            "sortable": True,
            "class": "text-center",
        },
    ]

    context = {
        "active_menu": "pricing",
        "page_title": "قائمة عروض الأسعار",
        "page_icon": "fas fa-file-invoice-dollar",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "عروض الأسعار",
                "url": "",
                "icon": "fas fa-file-invoice-dollar",
                "active": True,
            },
        ],
        "quotations": quotations,
        "headers": headers,
        "data": quotations,
        "table_id": "quotations-table",
        "clickable_rows": True,
        "row_click_url": "/pricing/0/",
        "primary_key": "id",
        "show_export": True,
        "export_filename": "quotations",
        "action_buttons": [
            {
                "url": "pricing:pricing_detail",
                "icon": "fa-eye",
                "label": "عرض",
                "class": "action-view",
            },
            {
                "url": "pricing:pricing_edit",
                "icon": "fa-edit",
                "label": "تعديل",
                "class": "action-edit",
                "condition": "user.is_staff or user == item.created_by",
            },
        ],
        "show_currency": True,
        "currency_symbol": "ج.م",
    }
    return render(request, "pricing/quotation_list.html", context)


@login_required
def quotation_create(request):
    """إنشاء عرض سعر جديد"""
    # في المرحلة الحالية، سنوجه لإنشاء طلب تسعير جديد
    return redirect("pricing:pricing_order_create")


@login_required
def supplier_pricing_list(request):
    """قائمة أسعار الموردين"""
    # جلب جميع الموردين (مؤقتاً حتى يتم تطوير النماذج الكاملة)
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    context = {
        "active_menu": "pricing",
        "page_title": "أسعار الموردين",
        "page_icon": "fas fa-building",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "أسعار الموردين",
                "url": "",
                "icon": "fas fa-building",
                "active": True,
            },
        ],
        "suppliers": suppliers,
        "paper_services": [],  # مؤقت
        "plate_services": [],  # مؤقت
    }
    return render(request, "pricing/supplier_pricing_list.html", context)


@login_required
def price_comparison(request):
    """مقارنة الأسعار بين الموردين"""
    from django.db.models import Count, Avg
    from datetime import datetime, timedelta

    # جلب الموردين وخدماتهم للمقارنة
    suppliers = Supplier.objects.filter(is_active=True)

    # فلترة طلبات التسعير
    orders = PricingOrder.objects.all().order_by("-created_at")

    # تطبيق الفلاتر
    product_type = request.GET.get("product_type")
    supplier_id = request.GET.get("supplier")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if product_type:
        orders = orders.filter(order_type=product_type)
    if supplier_id:
        orders = orders.filter(supplier_id=supplier_id)
    if date_from:
        orders = orders.filter(created_at__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__lte=date_to)

    # إحصائيات
    total_orders = orders.count()
    active_suppliers = suppliers.count()

    # طلبات هذا الشهر
    this_month = datetime.now().replace(day=1)
    this_month_orders = PricingOrder.objects.filter(created_at__gte=this_month).count()

    # متوسط التوفير (مثال)
    avg_savings = 15  # يمكن حسابه بناءً على البيانات الفعلية

    context = {
        "active_menu": "pricing",
        "page_title": "مقارنة الأسعار",
        "page_icon": "fas fa-chart-line",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "مقارنة الأسعار",
                "url": "",
                "icon": "fas fa-chart-line",
                "active": True,
            },
        ],
        "suppliers": suppliers,
        "comparisons": orders[:20],  # أول 20 طلب للمقارنة
        "total_orders": total_orders,
        "active_suppliers": active_suppliers,
        "this_month_orders": this_month_orders,
        "avg_savings": avg_savings,
    }
    return render(request, "pricing/price_comparison.html", context)


@login_required
def profitability_report(request):
    """تقرير الربحية"""
    # حساب الربحية لطلبات التسعير المنفذة
    executed_orders = (
        PricingOrder.objects.filter(status="executed")
        .annotate(profit=F("sale_price") - F("total_cost"))
        .order_by("-created_at")
    )

    # إحصائيات الربحية
    total_revenue = executed_orders.aggregate(Sum("sale_price"))["sale_price__sum"] or 0
    total_cost = executed_orders.aggregate(Sum("total_cost"))["total_cost__sum"] or 0
    total_profit = total_revenue - total_cost
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

    context = {
        "active_menu": "pricing",
        "page_title": "تقرير الربحية",
        "executed_orders": executed_orders,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "profit_margin": profit_margin,
    }
    return render(request, "pricing/profitability_report.html", context)


@login_required
def pricing_analytics(request):
    """تحليلات التسعير"""
    # تحليلات متقدمة للتسعير
    orders_by_status = PricingOrder.objects.values("status").annotate(count=Count("id"))
    orders_by_month = (
        PricingOrder.objects.extra(select={"month": "strftime('%%Y-%%m', created_at)"})
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    top_clients = (
        PricingOrder.objects.values("client__name")
        .annotate(total_orders=Count("id"), total_value=Sum("sale_price"))
        .order_by("-total_value")[:10]
    )

    context = {
        "active_menu": "pricing",
        "page_title": "تحليلات التسعير",
        "orders_by_status": orders_by_status,
        "orders_by_month": orders_by_month,
        "top_clients": top_clients,
    }
    return render(request, "pricing/pricing_analytics.html", context)


@login_required
def settings_home(request):
    """صفحة إعدادات التسعير - الموجودة مسبقاً"""
    return render(
        request,
        "pricing/settings/settings_home.html",
        {
            "active_menu": "pricing",
            "page_title": "إعدادات التسعير",
            "page_icon": "fas fa-cogs",
            "breadcrumb_items": [
                {
                    "title": "الرئيسية",
                    "url": reverse("core:dashboard"),
                    "icon": "fas fa-home",
                },
                {
                    "title": "التسعير",
                    "url": reverse("pricing:pricing_dashboard"),
                    "icon": "fas fa-calculator",
                },
                {
                    "title": "الإعدادات",
                    "url": "",
                    "icon": "fas fa-cogs",
                    "active": True,
                },
            ],
        },
    )


# ==================== Views الإعدادات ====================

# إعدادات أنواع الورق
# تم حذف الـ Views القديمة - استخدم الـ Views الجديدة في نهاية الملف

# تم حذف الـ Views القديمة لأحجام الورق - استخدم الـ Views الجديدة في نهاية الملف

# إعدادات اتجاهات الطباعة
@login_required
def print_direction_list(request):
    """قائمة اتجاهات الطباعة"""
    from .models import PrintDirection

    print_directions = PrintDirection.objects.all().order_by("name")

    context = {
        "print_directions": print_directions,
        "page_title": "إعدادات اتجاهات الطباعة",
        "page_icon": "fas fa-arrows-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "اتجاهات الطباعة", "active": True},
        ],
    }

    return render(request, "pricing/settings/print_directions/list.html", context)


@login_required
def print_direction_create(request):
    """إنشاء اتجاه طباعة جديد"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:print_direction_list")


@login_required
def print_direction_edit(request, pk):
    """تعديل اتجاه طباعة"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:print_direction_list")


@login_required
def print_direction_delete(request, pk):
    """حذف اتجاه طباعة"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:print_direction_list")


# إعدادات جوانب الطباعة
@login_required
def print_side_list(request):
    """قائمة جوانب الطباعة"""
    print_sides = PrintSide.objects.all() if hasattr(PrintSide, "objects") else []
    return render(
        request,
        "pricing/settings/print_side/list.html",
        {
            "print_sides": print_sides,
            "active_menu": "pricing",
            "page_title": "جوانب الطباعة",
        },
    )


@login_required
def print_side_create(request):
    """إنشاء جانب طباعة جديد"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:print_side_list")


@login_required
def print_side_edit(request, pk):
    """تعديل جانب طباعة"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:print_side_list")


@login_required
def print_side_delete(request, pk):
    """حذف جانب طباعة"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:print_side_list")


# إعدادات أنواع التغطية
@login_required
def coating_type_list(request):
    """قائمة أنواع التغطية"""
    coating_types = CoatingType.objects.all().order_by("name")

    context = {
        "coating_types": coating_types,
        "page_title": "إعدادات أنواع التغطية",
        "page_icon": "fas fa-paint-brush",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أنواع التغطية", "active": True},
        ],
    }

    return render(request, "pricing/settings/coating_type/list.html", context)


@login_required
def coating_type_create(request):
    """إنشاء نوع تغطية جديد"""
    from .forms import CoatingTypeForm

    if request.method == "POST":
        form = CoatingTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء نوع التغطية بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:coating_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/coating_type/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة نوع تغطية جديد",
                        "action_url": reverse("pricing:coating_type_create"),
                    },
                )

    form = CoatingTypeForm()
    return render(
        request,
        "pricing/settings/coating_type/form_modal.html",
        {
            "form": form,
            "title": "إضافة نوع تغطية جديد",
            "action_url": reverse("pricing:coating_type_create"),
        },
    )


@login_required
def coating_type_edit(request, pk):
    """تعديل نوع تغطية"""
    from .forms import CoatingTypeForm

    try:
        coating_type = CoatingType.objects.get(pk=pk)
    except CoatingType.DoesNotExist:
        messages.error(request, "نوع التغطية غير موجود")
        return redirect("pricing:coating_type_list")

    if request.method == "POST":
        form = CoatingTypeForm(request.POST, instance=coating_type)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث نوع التغطية بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:coating_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/coating_type/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {coating_type.name}",
                        "action_url": reverse(
                            "pricing:coating_type_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = CoatingTypeForm(instance=coating_type)
    return render(
        request,
        "pricing/settings/coating_type/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {coating_type.name}",
            "action_url": reverse("pricing:coating_type_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def coating_type_delete(request, pk):
    """حذف نوع تغطية"""
    try:
        coating_type = CoatingType.objects.get(pk=pk)
    except CoatingType.DoesNotExist:
        messages.error(request, "نوع التغطية غير موجود")
        return redirect("pricing:coating_type_list")

    if request.method == "POST":
        coating_type_name = coating_type.name
        coating_type.delete()
        messages.success(request, f'تم حذف نوع التغطية "{coating_type_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:coating_type_list")

    return render(
        request,
        "pricing/settings/coating_type/delete_modal.html",
        {
            "coating_type": coating_type,
            "action_url": reverse("pricing:coating_type_delete", kwargs={"pk": pk}),
        },
    )


# إعدادات أنواع خدمات ما بعد الطباعة
@login_required
def finishing_type_list(request):
    """قائمة أنواع خدمات ما بعد الطباعة"""
    from .models import FinishingType

    finishing_types = FinishingType.objects.all().order_by("name")

    context = {
        "finishing_types": finishing_types,
        "page_title": "إعدادات أنواع التشطيب",
        "page_icon": "fas fa-magic",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أنواع التشطيب", "active": True},
        ],
    }

    return render(request, "pricing/settings/finishing_types/list.html", context)


@login_required
def finishing_type_create(request):
    """إنشاء نوع تشطيب جديد"""
    from .models import FinishingType
    from .forms import FinishingTypeForm

    if request.method == "POST":
        form = FinishingTypeForm(request.POST)
        if form.is_valid():
            finishing_type = form.save()
            messages.success(
                request, f'تم إنشاء نوع التشطيب "{finishing_type.name}" بنجاح'
            )

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:finishing_type_list")
        else:
            # في حالة وجود أخطاء في النموذج
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = FinishingTypeForm()

    return render(
        request,
        "pricing/settings/finishing_types/form_modal.html",
        {
            "form": form,
            "title": "إضافة نوع تشطيب جديد",
            "action_url": reverse("pricing:finishing_type_create"),
        },
    )


@login_required
def finishing_type_edit(request, pk):
    """تعديل نوع تشطيب"""
    from .models import FinishingType
    from .forms import FinishingTypeForm

    try:
        finishing_type = FinishingType.objects.get(pk=pk)
    except FinishingType.DoesNotExist:
        messages.error(request, "نوع التشطيب غير موجود")
        return redirect("pricing:finishing_type_list")

    if request.method == "POST":
        form = FinishingTypeForm(request.POST, instance=finishing_type)
        if form.is_valid():
            finishing_type = form.save()
            messages.success(
                request, f'تم تحديث نوع التشطيب "{finishing_type.name}" بنجاح'
            )

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:finishing_type_list")
        else:
            # في حالة وجود أخطاء في النموذج
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = FinishingTypeForm(instance=finishing_type)

    return render(
        request,
        "pricing/settings/finishing_types/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {finishing_type.name}",
            "action_url": reverse("pricing:finishing_type_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def finishing_type_delete(request, pk):
    """حذف نوع تشطيب"""
    from .models import FinishingType

    try:
        finishing_type = FinishingType.objects.get(pk=pk)
    except FinishingType.DoesNotExist:
        messages.error(request, "نوع التشطيب غير موجود")
        return redirect("pricing:finishing_type_list")

    if request.method == "POST":
        finishing_type_name = finishing_type.name
        finishing_type.delete()
        messages.success(request, f'تم حذف نوع التشطيب "{finishing_type_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:finishing_type_list")

    return render(
        request,
        "pricing/settings/finishing_types/delete_modal.html",
        {
            "finishing_type": finishing_type,
            "action_url": reverse("pricing:finishing_type_delete", kwargs={"pk": pk}),
        },
    )


# إعدادات عامة
@login_required
def vat_settings(request):
    """إعدادات ضريبة القيمة المضافة"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:settings_home")


@login_required
def system_settings_list(request):
    """قائمة إعدادات النظام"""
    messages.info(request, "هذه الميزة تحت التطوير")
    return redirect("pricing:settings_home")


# إعدادات أنواع ماكينات الأوفست
@login_required
def offset_machine_type_list(request):
    """قائمة أنواع ماكينات الأوفست"""
    from .models import OffsetMachineType

    machine_types = OffsetMachineType.objects.all().order_by("manufacturer", "name")

    context = {
        "machine_types": machine_types,
        "page_title": "إعدادات أنواع ماكينات الأوفست",
        "page_icon": "fas fa-print",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أنواع ماكينات الأوفست", "active": True},
        ],
    }

    return render(request, "pricing/settings/offset_machine_type/list.html", context)


@login_required
def offset_machine_type_create(request):
    """إنشاء نوع ماكينة أوفست جديد"""
    from .forms import OffsetMachineTypeForm

    if request.method == "POST":
        form = OffsetMachineTypeForm(request.POST)
        if form.is_valid():
            try:
                machine_type = form.save()
                messages.success(
                    request, f'تم إنشاء نوع الماكينة "{machine_type.name}" بنجاح'
                )

                # التحقق من AJAX request
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"success": True})
                else:
                    return redirect("pricing:offset_machine_type_list")
            except Exception as e:
                # معالجة خطأ UNIQUE constraint
                if "UNIQUE constraint failed" in str(e):
                    form.add_error(
                        "code", "هذا الكود موجود بالفعل. يرجى استخدام كود مختلف."
                    )
                else:
                    form.add_error(None, f"حدث خطأ: {str(e)}")

                # التحقق من AJAX request للأخطاء
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"success": False, "errors": form.errors})
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})

    form = OffsetMachineTypeForm()
    return render(
        request,
        "pricing/settings/offset_machine_type/form_modal.html",
        {
            "form": form,
            "title": "إضافة نوع ماكينة جديد",
            "action_url": reverse("pricing:offset_machine_type_create"),
        },
    )


@login_required
def offset_machine_type_edit(request, pk):
    """تعديل نوع ماكينة أوفست"""
    from .forms import OffsetMachineTypeForm
    from .models import OffsetMachineType

    try:
        machine_type = OffsetMachineType.objects.get(pk=pk)
    except OffsetMachineType.DoesNotExist:
        messages.error(request, "نوع الماكينة غير موجود")
        return redirect("pricing:offset_machine_type_list")

    if request.method == "POST":
        form = OffsetMachineTypeForm(request.POST, instance=machine_type)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث نوع الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:offset_machine_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/offset_machine_type/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {machine_type.name}",
                        "action_url": reverse(
                            "pricing:offset_machine_type_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = OffsetMachineTypeForm(instance=machine_type)
    return render(
        request,
        "pricing/settings/offset_machine_type/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {machine_type.name}",
            "action_url": reverse(
                "pricing:offset_machine_type_edit", kwargs={"pk": pk}
            ),
        },
    )


@login_required
def offset_machine_type_delete(request, pk):
    """حذف نوع ماكينة أوفست"""
    from .models import OffsetMachineType

    try:
        machine_type = OffsetMachineType.objects.get(pk=pk)
    except OffsetMachineType.DoesNotExist:
        messages.error(request, "نوع الماكينة غير موجود")
        return redirect("pricing:offset_machine_type_list")

    if request.method == "POST":
        machine_type_name = machine_type.name
        machine_type.delete()
        messages.success(request, f'تم حذف نوع الماكينة "{machine_type_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:offset_machine_type_list")

    return render(
        request,
        "pricing/settings/offset_machine_type/delete_modal.html",
        {
            "machine_type": machine_type,
            "action_url": reverse(
                "pricing:offset_machine_type_delete", kwargs={"pk": pk}
            ),
        },
    )


# إعدادات مقاسات القطع
@login_required
def piece_size_list(request):
    """قائمة مقاسات القطع"""
    from .models import PieceSize

    piece_sizes = PieceSize.objects.all().order_by("name", "width", "height")

    context = {
        "piece_sizes": piece_sizes,
        "page_title": "إعدادات مقاسات القطع",
        "page_icon": "fas fa-cut",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "مقاسات القطع", "active": True},
        ],
    }

    return render(request, "pricing/settings/piece_size/list.html", context)


@login_required
def piece_size_create(request):
    """إنشاء مقاس قطع جديد"""
    from .forms import PieceSizeForm

    if request.method == "POST":
        form = PieceSizeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء مقاس القطع بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:piece_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/piece_size/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة مقاس قطع جديد",
                        "action_url": reverse("pricing:piece_size_create"),
                    },
                )

    form = PieceSizeForm()
    return render(
        request,
        "pricing/settings/piece_size/form_modal.html",
        {
            "form": form,
            "title": "إضافة مقاس قطع جديد",
            "action_url": reverse("pricing:piece_size_create"),
        },
    )


@login_required
def piece_size_edit(request, pk):
    """تعديل مقاس قطع"""
    from .forms import PieceSizeForm
    from .models import PieceSize

    try:
        piece_size = PieceSize.objects.get(pk=pk)
    except PieceSize.DoesNotExist:
        messages.error(request, "مقاس القطع غير موجود")
        return redirect("pricing:piece_size_list")

    if request.method == "POST":
        form = PieceSizeForm(request.POST, instance=piece_size)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث مقاس القطع بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:piece_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})

    form = PieceSizeForm(instance=piece_size)
    return render(
        request,
        "pricing/settings/piece_size/form_modal.html",
        {
            "form": form,
            "title": "تعديل مقاس القطع",
            "action_url": reverse("pricing:piece_size_edit", args=[pk]),
        },
    )


@login_required
def piece_size_delete(request, pk):
    """حذف مقاس قطع"""
    from .models import PieceSize

    try:
        piece_size = PieceSize.objects.get(pk=pk)
    except PieceSize.DoesNotExist:
        messages.error(request, "مقاس القطع غير موجود")
        return redirect("pricing:piece_size_list")

    if request.method == "POST":
        piece_size.delete()
        messages.success(request, "تم حذف مقاس القطع بنجاح")

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:piece_size_list")

    return render(
        request,
        "pricing/settings/piece_size/delete_modal.html",
        {
            "piece_size": piece_size,
            "action_url": reverse("pricing:piece_size_delete", kwargs={"pk": pk}),
        },
    )


# إعدادات مقاسات ماكينات الأوفست
@login_required
def offset_sheet_size_list(request):
    """قائمة مقاسات ماكينات الأوفست"""
    from .models import OffsetSheetSize

    sheet_sizes = OffsetSheetSize.objects.all().order_by("width_cm", "height_cm")

    context = {
        "sheet_sizes": sheet_sizes,
        "page_title": "إعدادات مقاسات ماكينات الأوفست",
        "page_icon": "fas fa-expand-arrows-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "مقاسات ماكينات الأوفست", "active": True},
        ],
    }

    return render(request, "pricing/settings/offset_sheet_size/list.html", context)


@login_required
def offset_sheet_size_create(request):
    """إنشاء مقاس ماكينة أوفست جديد"""
    from .forms import OffsetSheetSizeForm

    if request.method == "POST":
        form = OffsetSheetSizeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء مقاس الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:offset_sheet_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/offset_sheet_size/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة مقاس جديد",
                        "action_url": reverse("pricing:offset_sheet_size_create"),
                    },
                )

    form = OffsetSheetSizeForm()
    return render(
        request,
        "pricing/settings/offset_sheet_size/form_modal.html",
        {
            "form": form,
            "title": "إضافة مقاس جديد",
            "action_url": reverse("pricing:offset_sheet_size_create"),
        },
    )


@login_required
def offset_sheet_size_edit(request, pk):
    """تعديل مقاس ماكينة أوفست"""
    from .forms import OffsetSheetSizeForm
    from .models import OffsetSheetSize

    try:
        sheet_size = OffsetSheetSize.objects.get(pk=pk)
    except OffsetSheetSize.DoesNotExist:
        messages.error(request, "مقاس الماكينة غير موجود")
        return redirect("pricing:offset_sheet_size_list")

    if request.method == "POST":
        form = OffsetSheetSizeForm(request.POST, instance=sheet_size)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث مقاس الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:offset_sheet_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/offset_sheet_size/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {sheet_size.name}",
                        "action_url": reverse(
                            "pricing:offset_sheet_size_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = OffsetSheetSizeForm(instance=sheet_size)
    return render(
        request,
        "pricing/settings/offset_sheet_size/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {sheet_size.name}",
            "action_url": reverse("pricing:offset_sheet_size_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def offset_sheet_size_delete(request, pk):
    """حذف مقاس ماكينة أوفست"""
    from .models import OffsetSheetSize

    try:
        sheet_size = OffsetSheetSize.objects.get(pk=pk)
    except OffsetSheetSize.DoesNotExist:
        messages.error(request, "مقاس الماكينة غير موجود")
        return redirect("pricing:offset_sheet_size_list")

    if request.method == "POST":
        sheet_size_name = sheet_size.name
        sheet_size.delete()
        messages.success(request, f'تم حذف مقاس الماكينة "{sheet_size_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:offset_sheet_size_list")

    return render(
        request,
        "pricing/settings/offset_sheet_size/delete_modal.html",
        {
            "sheet_size": sheet_size,
            "action_url": reverse(
                "pricing:offset_sheet_size_delete", kwargs={"pk": pk}
            ),
        },
    )


# ==================== APIs حساب التكلفة ====================


@login_required
def get_paper_price(request):
    """API لحساب سعر الورق"""
    try:
        # الحصول على المعاملات
        supplier_id = request.GET.get("supplier_id")
        paper_type_id = request.GET.get("paper_type_id")
        paper_size_id = request.GET.get("paper_size_id")
        weight = request.GET.get("weight")
        quantity = int(request.GET.get("quantity", 1))
        origin = request.GET.get("origin", "local")

        if not all([supplier_id, paper_type_id, paper_size_id, weight]):
            return JsonResponse({"success": False, "error": "معاملات مفقودة"})

        # البحث عن خدمة الورق
        paper_service = PaperServiceDetails.find_paper_service(
            supplier_id=supplier_id,
            paper_type_id=paper_type_id,
            paper_size_id=paper_size_id,
            weight=int(weight),
            origin=origin,
        )

        if not paper_service:
            return JsonResponse(
                {"success": False, "error": "لم يتم العثور على سعر للورق المحدد"}
            )

        # حساب التكلفة
        total_cost = float(paper_service.price_per_sheet) * quantity

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "price_per_sheet": float(paper_service.price_per_sheet),
                    "price_per_kg": float(paper_service.price_per_kg),
                    "quantity": quantity,
                    "total_cost": total_cost,
                    "supplier_name": paper_service.supplier.name,
                    "paper_type_name": paper_service.paper_type.name,
                    "paper_size_name": paper_service.paper_size.name,
                    "weight": paper_service.weight,
                    "origin": paper_service.get_origin_display(),
                    "minimum_quantity": paper_service.minimum_quantity,
                },
            }
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في حساب سعر الورق: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "error": "خطأ في حساب سعر الورق"})


@login_required
def get_plate_price(request):
    """API لحساب سعر الزنكات"""
    try:
        # الحصول على المعاملات
        supplier_id = request.GET.get("supplier_id")
        plate_size_id = request.GET.get("plate_size_id")
        quantity = int(request.GET.get("quantity", 1))

        if not all([supplier_id, plate_size_id]):
            return JsonResponse({"success": False, "error": "معاملات مفقودة"})

        # البحث عن خدمة الزنك
        plate_service = PlateServiceDetails.find_plate_service(
            supplier_id=supplier_id, plate_size_id=plate_size_id
        )

        if not plate_service:
            return JsonResponse(
                {"success": False, "error": "لم يتم العثور على سعر للزنك المحدد"}
            )

        # حساب التكلفة
        plates_cost = float(plate_service.price_per_plate) * quantity
        total_cost = (
            plates_cost
            + float(plate_service.setup_cost)
            + float(plate_service.transportation_cost)
        )

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "price_per_plate": float(plate_service.price_per_plate),
                    "setup_cost": float(plate_service.setup_cost),
                    "transportation_cost": float(plate_service.transportation_cost),
                    "quantity": quantity,
                    "plates_cost": plates_cost,
                    "total_cost": total_cost,
                    "supplier_name": plate_service.supplier.name,
                    "plate_size_name": plate_service.plate_size.name,
                    "minimum_quantity": plate_service.minimum_quantity,
                },
            }
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في حساب سعر الزنك: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "error": "خطأ في حساب سعر الزنك"})


@login_required
def get_digital_press_price(request):
    """API لحساب سعر الطباعة الرقمية"""
    try:
        # الحصول على المعاملات
        supplier_id = request.GET.get("supplier_id")
        paper_size_id = request.GET.get("paper_size_id")
        color_type = request.GET.get("color_type", "color")
        quantity = int(request.GET.get("quantity", 1))

        if not all([supplier_id, paper_size_id]):
            return JsonResponse({"success": False, "error": "معاملات مفقودة"})

        # البحث عن خدمة الطباعة الرقمية
        try:
            digital_service = DigitalPrintingDetails.objects.get(
                supplier_id=supplier_id,
                paper_size_id=paper_size_id,
                color_type=color_type,
                is_active=True,
            )
        except DigitalPrintingDetails.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "لم يتم العثور على سعر للطباعة المحددة"}
            )

        # التحقق من الكمية
        if quantity < digital_service.minimum_quantity:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"الحد الأدنى للكمية هو {digital_service.minimum_quantity}",
                }
            )

        if (
            digital_service.maximum_quantity
            and quantity > digital_service.maximum_quantity
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": f"الحد الأقصى للكمية هو {digital_service.maximum_quantity}",
                }
            )

        # حساب التكلفة
        total_cost = float(digital_service.price_per_copy) * quantity

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "price_per_copy": float(digital_service.price_per_copy),
                    "quantity": quantity,
                    "total_cost": total_cost,
                    "supplier_name": digital_service.supplier.name,
                    "paper_size_name": digital_service.paper_size.name,
                    "color_type": digital_service.get_color_type_display(),
                    "minimum_quantity": digital_service.minimum_quantity,
                    "maximum_quantity": digital_service.maximum_quantity,
                },
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في حساب سعر الطباعة: خطأ في العملية"}
        )


@login_required
def get_paper_weights(request):
    """API للحصول على أوزان الورق المتاحة"""
    try:
        paper_type_id = request.GET.get("paper_type_id")
        paper_size_id = request.GET.get("paper_size_id")
        supplier_id = request.GET.get("supplier_id")

        query = PaperServiceDetails.objects.filter(service__is_active=True)

        if paper_type_id:
            query = query.filter(paper_type_id=paper_type_id)
        if paper_size_id:
            query = query.filter(paper_size_id=paper_size_id)
        if supplier_id:
            query = query.filter(service__supplier_id=supplier_id)

        weights = query.values_list("gsm", flat=True).distinct().order_by("gsm")

        return JsonResponse({"success": True, "data": list(weights)})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب أوزان الورق: خطأ في العملية"}
        )


@login_required
def get_paper_sheet_types(request):
    """API للحصول على أنواع الورق المتاحة"""
    try:
        sheet_types = PaperServiceDetails.SHEET_TYPE_CHOICES

        return JsonResponse(
            {
                "success": True,
                "data": [
                    {"value": choice[0], "label": choice[1]} for choice in sheet_types
                ],
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
    try:
        from supplier.models import PlateServiceDetails

        supplier_id = request.GET.get("supplier_id")

        if not supplier_id:
            # إرجاع جميع مقاسات الزنكات النشطة إذا لم يتم تحديد مورد
            from .templatetags.pricing_filters import remove_trailing_zeros

            sizes = (
                PlateSize.objects.filter(is_active=True)
                .values("id", "name", "width", "height")
                .order_by("name")
            )
            return JsonResponse(
                {
                    "success": True,
                    "plate_sizes": [
                        {
                            "id": size["id"],
                            "name": f"{size['name']} ({remove_trailing_zeros(size['width'])}×{remove_trailing_zeros(size['height'])})",
                            "service_name": f"{size['name']} ({remove_trailing_zeros(size['width'])}×{remove_trailing_zeros(size['height'])})",
                            "price": 0,  # سعر افتراضي
                        }
                        for size in sizes
                    ],
                }
            )

        # جلب المقاسات المتاحة لدى المورد المحدد مع الأسعار
        plate_services = PlateServiceDetails.objects.filter(
            service__supplier_id=supplier_id, 
            service__is_active=True
        ).select_related("service")

        from .templatetags.pricing_filters import remove_trailing_zeros

        plate_sizes_data = []
        seen_sizes = set()  # لتتبع المقاسات التي تم إضافتها
        
        for service in plate_services:
            if service.plate_size:
                # تطبيع المقاس إلى قيمة معيارية لتجنب التكرار
                normalized_size = service.plate_size
                if service.plate_size in ["35.00x50.00", "35x50", "quarter_sheet"]:
                    normalized_size = "35x50"
                    size_display = "ربع فرخ (35×50 سم)"
                elif service.plate_size in ["50.00x70.00", "50x70", "half_sheet"]:
                    normalized_size = "50x70"
                    size_display = "نصف فرخ (50×70 سم)"
                elif service.plate_size in ["70.00x100.00", "70x100", "full_sheet"]:
                    normalized_size = "70x100"
                    size_display = "فرخ كامل (70×100 سم)"
                elif service.plate_size == "custom":
                    normalized_size = "custom"
                    size_display = "مقاس مخصص"
                else:
                    normalized_size = service.plate_size
                    size_display = service.plate_size

                # إضافة فقط إذا لم يتم رؤية هذا المقاس من قبل
                if normalized_size not in seen_sizes:
                    seen_sizes.add(normalized_size)
                    plate_sizes_data.append({
                        "id": service.id,
                        "name": size_display,
                        "service_name": service.service.name if service.service.name else size_display,
                        "price": float(service.price_per_plate) if service.price_per_plate else 0,
                    })

        # إضافة معلومات التشخيص في الاستجابة
        debug_info = {
            "total_services": plate_services.count(),
            "unique_sizes_returned": len(plate_sizes_data),
            "debug_details": []
        }
        
        for service in plate_services:
            debug_info["debug_details"].append({
                "service_id": service.id,
                "service_name": service.service.name,
                "plate_size": service.plate_size,
                "price": float(service.price_per_plate) if service.price_per_plate else 0
            })

        return JsonResponse({
            "success": True, 
            "plate_sizes": plate_sizes_data,
            "debug": debug_info
        })

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب مقاسات الزنكات: خطأ في العملية"}
        )


@login_required
def get_paper_size_dimensions(request):
    """API للحصول على أبعاد مقاس الورق"""
    try:
        paper_size_id = request.GET.get("paper_size_id")

        if not paper_size_id:
            return JsonResponse({"success": False, "error": "معرف مقاس الورق مطلوب"})

        try:
            paper_size = PaperSize.objects.get(id=paper_size_id, is_active=True)
        except PaperSize.DoesNotExist:
            return JsonResponse({"success": False, "error": "مقاس الورق غير موجود"})

        return JsonResponse(
            {
                "success": True,
                "width": float(paper_size.width),
                "height": float(paper_size.height),
                "name": paper_size.name,
                "id": paper_size.id,
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب أبعاد مقاس الورق: خطأ في العملية"}
        )


@login_required
def convert_sheet_type_to_dimensions(request):
    """API لتحويل sheet_type إلى أبعاد من PaperSize"""
    try:
        sheet_type = request.GET.get("sheet_type")

        if not sheet_type:
            return JsonResponse({"success": False, "error": "نوع مقاس الورق مطلوب"})

        # خريطة تحويل من sheet_type إلى أسماء PaperSize
        sheet_type_mapping = {
            'full_70x100': 'فرخ 70×100',
            'half_50x70': 'نصف فرخ 50×70', 
            'quarter_35x50': 'ربع فرخ',
            'a3': 'A3',
            'a4': 'A4',
            'custom': None  # المقاس المخصص يحتاج معالجة خاصة
        }
        
        if sheet_type == 'custom':
            return JsonResponse({"success": False, "error": "المقاس المخصص يحتاج أبعاد محددة"})
        
        paper_size_name = sheet_type_mapping.get(sheet_type)
        if not paper_size_name:
            return JsonResponse({"success": False, "error": f"نوع مقاس الورق غير مدعوم: {sheet_type}"})

        try:
            paper_size = PaperSize.objects.get(name__icontains=paper_size_name, is_active=True)
        except PaperSize.DoesNotExist:
            return JsonResponse({"success": False, "error": f"مقاس الورق '{paper_size_name}' غير موجود في قاعدة البيانات"})

        return JsonResponse(
            {
                "success": True,
                "width": float(paper_size.width),
                "height": float(paper_size.height),
                "name": paper_size.name,
                "id": paper_size.id,
                "sheet_type": sheet_type,
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in convert_sheet_type_to_dimensions: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في تحويل نوع مقاس الورق"}
        )


@login_required
def get_paper_suppliers(request):
    """API للحصول على موردي الورق"""
    try:
        paper_type_id = request.GET.get("paper_type_id")
        paper_size_id = request.GET.get("paper_size_id")
        weight = request.GET.get("weight")

        query = PaperServiceDetails.objects.filter(service__is_active=True)

        if paper_type_id:
            # البحث في خدمات الورق حسب نوع الورق
            try:
                from pricing.models import PaperType

                paper_type = PaperType.objects.get(id=paper_type_id)
                # البحث بالاسم في PaperServiceDetails (paper_type هو CharField)
                query = query.filter(paper_type__icontains=paper_type.name.lower())
            except Exception as e:
                print(f"خطأ في البحث عن نوع الورق: {e}")
                # fallback - لا نفلتر إذا كان هناك خطأ
                pass
        if paper_size_id:
            query = query.filter(paper_size_id=paper_size_id)
        if weight:
            query = query.filter(gsm=int(weight))

        suppliers = (
            query.select_related("service__supplier")
            .values("service__supplier__id", "service__supplier__name")
            .distinct()
            .order_by("service__supplier__name")
        )

        return JsonResponse(
            {
                "success": True,
                "suppliers": [
                    {
                        "id": supplier["service__supplier__id"],
                        "name": supplier["service__supplier__name"],
                    }
                    for supplier in suppliers
                ],
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب موردي الورق: خطأ في العملية"}
        )


@login_required
def get_suppliers_by_service(request):
    """API للحصول على الموردين حسب نوع الخدمة"""
    try:
        service_type = request.GET.get("service_type")

        if not service_type:
            return JsonResponse({"success": False, "error": "نوع الخدمة مطلوب"})

        # استخدام النماذج من supplier بدلاً من النماذج المحذوفة
        from supplier.models import SpecializedService

        suppliers = (
            SpecializedService.objects.filter(
                category__code=service_type, is_active=True
            )
            .select_related("supplier")
            .values("supplier__id", "supplier__name")
            .distinct()
            .order_by("supplier__name")
        )

        return JsonResponse(
            {
                "success": True,
                "data": [
                    {"id": supplier["supplier__id"], "name": supplier["supplier__name"]}
                    for supplier in suppliers
                ],
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب الموردين: خطأ في العملية"}
        )


@login_required
def calculate_cost(request):
    """API حساب التكلفة الإجمالية للطلب"""
    try:
        if request.method != "POST":
            return JsonResponse({"success": False, "error": "يجب استخدام POST method"})

        data = json.loads(request.body)

        # بيانات الطلب الأساسية
        quantity = int(data.get("quantity", 1))
        order_type = data.get("order_type", "offset")

        # تكاليف المواد
        material_cost = Decimal("0.00")
        printing_cost = Decimal("0.00")
        finishing_cost = Decimal("0.00")
        extra_cost = Decimal("0.00")

        # حساب تكلفة الورق
        paper_data = data.get("paper", {})
        if paper_data:
            paper_response = get_paper_price_internal(paper_data, quantity)
            if paper_response.get("success"):
                material_cost += Decimal(str(paper_response["data"]["total_cost"]))

        # حساب تكلفة الطباعة
        printing_data = data.get("printing", {})
        if printing_data:
            if order_type == "digital":
                press_response = get_press_price_internal(printing_data, quantity)
                if press_response.get("success"):
                    printing_cost += Decimal(str(press_response["data"]["total_cost"]))
            else:
                # حساب تكلفة الزنكات للأوفست
                plate_data = printing_data.get("plates", {})
                if plate_data:
                    plate_response = get_plate_price_internal(plate_data)
                    if plate_response.get("success"):
                        printing_cost += Decimal(
                            str(plate_response["data"]["total_cost"])
                        )

        # حساب تكلفة خدمات التشطيب
        finishing_services = data.get("finishing_services", [])
        for service in finishing_services:
            service_cost = Decimal(str(service.get("unit_price", 0))) * int(
                service.get("quantity", 1)
            )
            finishing_cost += service_cost

        # حساب المصاريف الإضافية
        extra_expenses = data.get("extra_expenses", [])
        for expense in extra_expenses:
            extra_cost += Decimal(str(expense.get("amount", 0)))

        # حساب إجمالي التكلفة
        total_cost = material_cost + printing_cost + finishing_cost + extra_cost

        # حساب هامش الربح
        profit_margin = Decimal(str(data.get("profit_margin", 20)))
        sale_price = total_cost * (1 + (profit_margin / 100))

        # حساب ضريبة القيمة المضافة
        vat_setting = VATSetting.get_current_vat()
        vat_amount = Decimal("0.00")
        final_price = sale_price

        if vat_setting and vat_setting.is_enabled:
            vat_amount = sale_price * (vat_setting.percentage / 100)
            final_price = sale_price + vat_amount

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "costs": {
                        "material_cost": float(material_cost),
                        "printing_cost": float(printing_cost),
                        "finishing_cost": float(finishing_cost),
                        "extra_cost": float(extra_cost),
                        "total_cost": float(total_cost),
                    },
                    "pricing": {
                        "profit_margin": float(profit_margin),
                        "sale_price": float(sale_price),
                        "vat_amount": float(vat_amount),
                        "final_price": float(final_price),
                    },
                    "breakdown": {
                        "cost_per_unit": float(total_cost / quantity)
                        if quantity > 0
                        else 0,
                        "price_per_unit": float(final_price / quantity)
                        if quantity > 0
                        else 0,
                        "profit_amount": float(sale_price - total_cost),
                        "profit_percentage": float(
                            (sale_price - total_cost) / total_cost * 100
                        )
                        if total_cost > 0
                        else 0,
                    },
                },
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في حساب التكلفة: خطأ في العملية"}
        )


# دوال مساعدة داخلية
def get_paper_price_internal(paper_data, quantity):
    """دالة داخلية لحساب سعر الورق"""
    try:
        paper_service = PaperServiceDetails.find_paper_service(
            supplier_id=paper_data.get("supplier_id"),
            paper_type_id=paper_data.get("paper_type_id"),
            paper_size_id=paper_data.get("paper_size_id"),
            weight=int(paper_data.get("weight", 0)),
            origin=paper_data.get("origin", "local"),
        )

        if not paper_service:
            return {"success": False, "error": "خدمة الورق غير موجودة"}

        total_cost = float(paper_service.price_per_sheet) * quantity

        return {
            "success": True,
            "data": {
                "total_cost": total_cost,
                "price_per_sheet": float(paper_service.price_per_sheet),
            },
        }
    except Exception as e:
        return {"success": False, "error": "خطأ في العملية"}


def get_press_price_internal(printing_data, quantity):
    """دالة داخلية لحساب سعر الطباعة"""
    try:
        digital_service = DigitalPrintingDetails.objects.get(
            supplier_id=printing_data.get("supplier_id"),
            paper_size_id=printing_data.get("paper_size_id"),
            color_type=printing_data.get("color_type", "color"),
            is_active=True,
        )

        total_cost = float(digital_service.price_per_copy) * quantity

        return {
            "success": True,
            "data": {
                "total_cost": total_cost,
                "price_per_copy": float(digital_service.price_per_copy),
            },
        }
    except Exception as e:
        return {"success": False, "error": "خطأ في العملية"}


def get_plate_price_internal(plate_data):
    """دالة داخلية لحساب سعر الزنكات"""
    try:
        plate_service = PlateServiceDetails.find_plate_service(
            supplier_id=plate_data.get("supplier_id"),
            plate_size_id=plate_data.get("plate_size_id"),
        )

        if not plate_service:
            return {"success": False, "error": "خدمة الزنك غير موجودة"}

        quantity = int(plate_data.get("quantity", 1))
        plates_cost = float(plate_service.price_per_plate) * quantity
        total_cost = (
            plates_cost
            + float(plate_service.setup_cost)
            + float(plate_service.transportation_cost)
        )

        return {
            "success": True,
            "data": {"total_cost": total_cost, "plates_cost": plates_cost},
        }
    except Exception as e:
        return {"success": False, "error": "خطأ في العملية"}


# ==================== APIs خدمات التشطيب ====================


@login_required
def coating_services_api(request):
    """API للحصول على خدمات التغطية"""
    try:
        supplier_id = request.GET.get("supplier_id")

        from supplier.models import SpecializedService

        query = SpecializedService.objects.filter(
            category__code="finishing", is_active=True
        ).select_related("supplier")

        if supplier_id:
            query = query.filter(supplier_id=supplier_id)

        services = query.values(
            "id",
            "name",
            "description",
            "unit_price",
            "minimum_quantity",
            "supplier__id",
            "supplier__name",
        ).order_by("supplier__name", "name")

        return JsonResponse({"success": True, "data": list(services)})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب خدمات التغطية: خطأ في العملية"}
        )


@login_required
def folding_services_api(request):
    """API للحصول على خدمات الطي"""
    try:
        supplier_id = request.GET.get("supplier_id")

        from supplier.models import SpecializedService

        query = SpecializedService.objects.filter(
            category__code="finishing", is_active=True
        ).select_related("supplier")

        if supplier_id:
            query = query.filter(supplier_id=supplier_id)

        services = query.values(
            "id",
            "name",
            "description",
            "unit_price",
            "minimum_quantity",
            "supplier__id",
            "supplier__name",
        ).order_by("supplier__name", "name")

        return JsonResponse({"success": True, "data": list(services)})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب خدمات الطي: خطأ في العملية"}
        )


@login_required
def die_cut_services_api(request):
    """API للحصول على خدمات القص"""
    try:
        supplier_id = request.GET.get("supplier_id")

        from supplier.models import SpecializedService

        query = SpecializedService.objects.filter(
            category__code="finishing", is_active=True
        ).select_related("supplier")

        if supplier_id:
            query = query.filter(supplier_id=supplier_id)

        services = query.values(
            "id",
            "name",
            "description",
            "unit_price",
            "minimum_quantity",
            "supplier__id",
            "supplier__name",
        ).order_by("supplier__name", "name")

        return JsonResponse({"success": True, "data": list(services)})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب خدمات القص: خطأ في العملية"}
        )


@login_required
def spot_uv_services_api(request):
    """API للحصول على خدمات الورنيش الموضعي"""
    try:
        supplier_id = request.GET.get("supplier_id")

        from supplier.models import SpecializedService

        query = SpecializedService.objects.filter(
            category__code="finishing", is_active=True
        ).select_related("supplier")

        if supplier_id:
            query = query.filter(supplier_id=supplier_id)

        services = query.values(
            "id",
            "name",
            "description",
            "unit_price",
            "minimum_quantity",
            "supplier__id",
            "supplier__name",
        ).order_by("supplier__name", "name")

        return JsonResponse({"success": True, "data": list(services)})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {
                "success": False,
                "error": "خطأ في جلب خدمات الورنيش الموضعي: خطأ في العملية",
            }
        )


@login_required
def get_presses(request):
    """API للحصول على المطابع المتاحة"""
    try:
        supplier_id = request.GET.get("supplier_id")
        order_type = request.GET.get("order_type")  # أوفست أو ديجيتال

        if not supplier_id:
            # إرجاع جميع المكابس المتاحة إذا لم يتم تحديد مورد
            from .models import OffsetMachineType, DigitalMachineType

            presses = []

            # إضافة مكابس الأوفست
            offset_machines = OffsetMachineType.objects.filter(is_active=True)
            for machine in offset_machines:
                presses.append(
                    {
                        "id": f"offset_{machine.id}",
                        "name": f"{machine.manufacturer} {machine.name}"
                        if machine.manufacturer
                        else machine.name,
                        "type": "offset",
                        "price_per_1000": 100.0,  # سعر افتراضي
                    }
                )

            # إضافة مكابس الديجيتال
            digital_machines = DigitalMachineType.objects.filter(is_active=True)
            for machine in digital_machines:
                presses.append(
                    {
                        "id": f"digital_{machine.id}",
                        "name": f"{machine.manufacturer} {machine.name}"
                        if machine.manufacturer
                        else machine.name,
                        "type": "digital",
                        "price_per_1000": 150.0,  # سعر افتراضي
                    }
                )

            return JsonResponse({"success": True, "presses": presses})

        # جلب المكابس المتاحة لدى المورد المحدد
        from supplier.models import OffsetPrintingDetails, DigitalPrintingDetails

        presses = []

        # فلترة بناءً على نوع الطلب
        if not order_type or order_type == "offset":
            # البحث في خدمات الأوفست
            offset_services = OffsetPrintingDetails.objects.filter(
                service__supplier_id=supplier_id, service__is_active=True
            ).select_related("service")

            for service in offset_services:
                if service.machine_type:
                    # استخدام اسم الخدمة بدلاً من نوع الماكينة
                    machine_name = (
                        service.service.name
                        if service.service.name
                        else dict(OffsetPrintingDetails.MACHINE_TYPE_CHOICES).get(
                            service.machine_type, service.machine_type
                        )
                    )

                    presses.append(
                        {
                            "id": f"offset_service_{service.id}",
                            "name": machine_name,
                            "type": "offset",
                            "price_per_1000": float(service.impression_cost_per_1000)
                            if service.impression_cost_per_1000
                            else 100.0,
                        }
                    )

        if not order_type or order_type == "digital":
            # البحث في خدمات الديجيتال
            digital_services = DigitalPrintingDetails.objects.filter(
                service__supplier_id=supplier_id, service__is_active=True
            ).select_related("service")

            for service in digital_services:
                if service.machine_type:
                    # استخدام اسم الخدمة بدلاً من نوع الماكينة
                    machine_name = (
                        service.service.name
                        if service.service.name
                        else dict(DigitalPrintingDetails.MACHINE_TYPE_CHOICES).get(
                            service.machine_type, service.machine_type
                        )
                    )

                    presses.append(
                        {
                            "id": f"digital_service_{service.id}",
                            "name": machine_name,
                            "type": "digital",
                            "price_per_1000": float(service.price_per_copy) * 1000
                            if service.price_per_copy
                            else 150.0,
                        }
                    )

        return JsonResponse({"success": True, "presses": presses})

    except Exception as e:
        import traceback
        return JsonResponse(
            {
                "success": False,
                "error": f"خطأ في جلب المطابع: {str(e)}",
                "details": traceback.format_exc(),
                "presses": [],
            }
        )


@login_required
def get_press_details(request):
    """API للحصول على تفاصيل المطبعة"""
    try:
        press_id = request.GET.get("press_id")

        if not press_id:
            return JsonResponse({"success": False, "error": "معرف المطبعة مطلوب"})

        # بيانات مؤقتة - يمكن ربطها بنظام المطابع لاحقاً
        press_details = {
            "1": {
                "name": "مطبعة أوفست كبيرة",
                "type": "offset",
                "colors": 4,
                "speed": 10000,
            },
            "2": {
                "name": "مطبعة أوفست متوسطة",
                "type": "offset",
                "colors": 2,
                "speed": 8000,
            },
            "3": {
                "name": "مطبعة رقمية ملونة",
                "type": "digital",
                "colors": 4,
                "speed": 2000,
            },
            "4": {
                "name": "مطبعة رقمية أبيض وأسود",
                "type": "digital",
                "colors": 1,
                "speed": 3000,
            },
        }

        press = press_details.get(press_id)
        if not press:
            return JsonResponse({"success": False, "error": "المطبعة غير موجودة"})

        return JsonResponse({"success": True, "data": press})

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب تفاصيل المطبعة: خطأ في العملية"}
        )


@require_http_methods(["GET"])
def get_paper_types(request):
    """API لجلب أنواع الورق"""
    try:
        paper_types = PaperType.objects.filter(is_active=True).values(
            "id", "name", "description"
        )
        return JsonResponse(list(paper_types), safe=False)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب أنواع الورق: خطأ في العملية"}
        )


@require_http_methods(["POST"])
def calculate_cost_api(request):
    """API لحساب التكلفة الإجمالية"""
    try:
        data = json.loads(request.body)

        # حساب تكلفة الورق
        paper_cost = 0
        if (
            data.get("paper_type")
            and data.get("paper_size")
            and data.get("weight")
            and data.get("quantity")
        ):
            paper_response = get_paper_price(request)
            if paper_response.status_code == 200:
                paper_data = json.loads(paper_response.content)
                if paper_data.get("success"):
                    paper_cost = paper_data.get("total_cost", 0)

        # حساب تكلفة الطباعة
        press_cost = 0
        if data.get("press_type") and data.get("colors") and data.get("quantity"):
            press_response = get_press_price(request)
            if press_response.status_code == 200:
                press_data = json.loads(press_response.content)
                if press_data.get("success"):
                    press_cost = press_data.get("total_cost", 0)

        # حساب تكلفة الزنكات
        plate_cost = 0
        if data.get("plate_size") and data.get("plate_quantity"):
            plate_response = get_plate_price(request)
            if plate_response.status_code == 200:
                plate_data = json.loads(plate_response.content)
                if plate_data.get("success"):
                    plate_cost = plate_data.get("total_cost", 0)

        # حساب التكلفة الإجمالية
        subtotal = paper_cost + press_cost + plate_cost

        # حساب الضريبة
        vat_rate = 0.15  # 15% افتراضي
        try:
            vat_setting = VATSetting.objects.filter(is_active=True).first()
            if vat_setting:
                vat_rate = float(vat_setting.rate) / 100
        except:
            pass

        vat_amount = subtotal * vat_rate
        total_cost = subtotal + vat_amount

        return JsonResponse(
            {
                "success": True,
                "paper_cost": paper_cost,
                "press_cost": press_cost,
                "plate_cost": plate_cost,
                "subtotal": subtotal,
                "vat_rate": vat_rate * 100,
                "vat_amount": vat_amount,
                "total_cost": total_cost,
            }
        )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في حساب التكلفة: خطأ في العملية"}
        )


# ===== Views للنماذج الجديدة =====

# استيراد النماذج الجديدة
from .models import (
    OrderSupplier,
    PricingQuotation,
    PricingApprovalWorkflow,
    PricingApproval,
    PricingReport,
    PricingKPI,
)
from .forms import QuotationSearchForm


class OrderSupplierListView(LoginRequiredMixin, ListView):
    """عرض قائمة موردي الطلب"""

    model = OrderSupplier
    template_name = "pricing/order_suppliers_list.html"
    context_object_name = "order_suppliers"
    paginate_by = 20

    def get_queryset(self):
        order_id = self.kwargs.get("order_id")
        if order_id:
            return OrderSupplier.objects.filter(order_id=order_id).select_related(
                "order", "supplier"
            )
        return OrderSupplier.objects.select_related("order", "supplier").order_by(
            "-created_at"
        )


class OrderSupplierCreateView(LoginRequiredMixin, CreateView):
    """إضافة مورد جديد للطلب"""

    model = OrderSupplier
    template_name = "pricing/order_supplier_form.html"
    fields = [
        "supplier",
        "role",
        "service_type",
        "description",
        "estimated_cost",
        "quoted_price",
        "contact_person",
        "phone",
        "email",
        "notes",
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_id = self.kwargs.get("order_id")
        context["order"] = get_object_or_404(PricingOrder, id=order_id)
        context["order_suppliers"] = OrderSupplier.objects.filter(
            order_id=order_id
        ).select_related("supplier")
        context["suppliers"] = Supplier.objects.filter(is_active=True)

        # حساب إحصائيات التكاليف
        order_suppliers = context["order_suppliers"]
        context["total_estimated_cost"] = sum(
            os.estimated_cost for os in order_suppliers
        )
        context["total_quoted_price"] = sum(os.quoted_price for os in order_suppliers)
        context["price_difference"] = (
            context["total_quoted_price"] - context["total_estimated_cost"]
        )

        return context

    def form_valid(self, form):
        order_id = self.kwargs.get("order_id")
        form.instance.order_id = order_id
        messages.success(self.request, _("تم إضافة المورد بنجاح"))
        return super().form_valid(form)

    def get_success_url(self):
        order_id = self.kwargs.get("order_id")
        return reverse("pricing:order_suppliers_list", kwargs={"order_id": order_id})


class PricingQuotationListView(LoginRequiredMixin, ListView):
    """عرض قائمة عروض الأسعار"""

    model = PricingQuotation
    template_name = "pricing/quotations_list.html"
    context_object_name = "quotations"
    paginate_by = 15

    def get_queryset(self):
        queryset = PricingQuotation.objects.select_related(
            "pricing_order", "created_by"
        ).order_by("-created_at")

        # فلترة حسب الحالة
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # فلترة حسب التاريخ
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        # البحث
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(quotation_number__icontains=search)
                | Q(pricing_order__client__name__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_form"] = QuotationSearchForm(self.request.GET)
        return context


class PricingQuotationDetailView(LoginRequiredMixin, DetailView):
    """تفاصيل عرض السعر"""

    model = PricingQuotation
    template_name = "pricing/quotation_detail.html"
    context_object_name = "quotation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = self.object.status in ["draft", "under_review"]
        return context


class PricingQuotationCreateView(LoginRequiredMixin, CreateView):
    """إنشاء عرض سعر جديد"""

    model = PricingQuotation
    template_name = "pricing/quotation_form.html"
    fields = [
        "pricing_order",
        "valid_until",
        "follow_up_date",
        "payment_terms",
        "delivery_terms",
        "warranty_terms",
        "special_conditions",
        "sent_to_person",
        "sent_via",
        "discount_percentage",
    ]

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        # إنشاء رقم العرض تلقائياً
        form.instance.quotation_number = self.generate_quotation_number()
        messages.success(self.request, _("تم إنشاء عرض السعر بنجاح"))
        return super().form_valid(form)

    def generate_quotation_number(self):
        """إنشاء رقم عرض فريد"""
        today = timezone.now().date()
        prefix = f"QUO{today.strftime('%Y%m%d')}"

        # البحث عن آخر رقم في نفس اليوم
        last_quotation = (
            PricingQuotation.objects.filter(quotation_number__startswith=prefix)
            .order_by("-quotation_number")
            .first()
        )

        if last_quotation:
            last_number = int(last_quotation.quotation_number[-3:])
            new_number = last_number + 1
        else:
            new_number = 1

        return f"{prefix}{new_number:03d}"

    def get_success_url(self):
        return reverse("pricing:quotation_detail", kwargs={"pk": self.object.pk})


class PricingQuotationUpdateView(LoginRequiredMixin, UpdateView):
    """تحديث عرض السعر"""

    model = PricingQuotation
    template_name = "pricing/quotation_form.html"
    fields = [
        "valid_until",
        "follow_up_date",
        "status",
        "payment_terms",
        "delivery_terms",
        "warranty_terms",
        "special_conditions",
        "sent_to_person",
        "sent_via",
        "discount_percentage",
        "client_feedback",
        "internal_notes",
    ]

    def form_valid(self, form):
        messages.success(self.request, _("تم تحديث عرض السعر بنجاح"))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("pricing:quotation_detail", kwargs={"pk": self.object.pk})


class PricingApprovalWorkflowListView(LoginRequiredMixin, ListView):
    """عرض قائمة تدفقات الموافقة"""

    model = PricingApprovalWorkflow
    template_name = "pricing/approval_workflows_list.html"
    context_object_name = "workflows"
    paginate_by = 10

    def get_queryset(self):
        return PricingApprovalWorkflow.objects.select_related(
            "created_by", "primary_approver", "secondary_approver"
        ).order_by("-created_at")


class PricingApprovalWorkflowCreateView(LoginRequiredMixin, CreateView):
    """إنشاء تدفق موافقة جديد"""

    model = PricingApprovalWorkflow
    template_name = "pricing/approval_workflow_form.html"
    fields = [
        "name",
        "description",
        "min_amount",
        "max_amount",
        "primary_approver",
        "secondary_approver",
        "email_notifications",
        "whatsapp_notifications",
        "auto_approve_below_limit",
        "require_both_approvers",
    ]

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تم إنشاء تدفق الموافقة بنجاح"))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("pricing:approval_workflows_list")


class PricingApprovalListView(LoginRequiredMixin, ListView):
    """عرض قائمة الموافقات"""

    model = PricingApproval
    template_name = "pricing/approvals_list.html"
    context_object_name = "approvals"
    paginate_by = 15

    def get_queryset(self):
        queryset = PricingApproval.objects.select_related(
            "pricing_order", "workflow", "requested_by", "approver"
        ).order_by("-created_at")

        # فلترة للمعتمد الحالي
        if self.request.GET.get("my_approvals"):
            queryset = queryset.filter(approver=self.request.user)

        # فلترة حسب الحالة
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_count"] = PricingApproval.objects.filter(
            approver=self.request.user, status="pending"
        ).count()
        return context


class PricingApprovalDetailView(LoginRequiredMixin, DetailView):
    """تفاصيل الموافقة"""

    model = PricingApproval
    template_name = "pricing/approval_detail.html"
    context_object_name = "approval"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_approve"] = (
            self.object.approver == self.request.user
            and self.object.status == "pending"
        )
        return context


@login_required
def enhanced_pricing_form(request):
    """صفحة التسعير المحسنة"""
    context = {
        "title": "نظام التسعير المحسن",
    }
    return render(request, "pricing/enhanced_pricing_form.html", context)


@login_required
@require_http_methods(["POST"])
def approve_pricing_request(request, approval_id):
    """الموافقة على طلب التسعير"""
    approval = get_object_or_404(PricingApproval, id=approval_id)

    # التحقق من الصلاحيات
    if approval.approver != request.user:
        raise PermissionDenied(_("ليس لديك صلاحية للموافقة على هذا الطلب"))

    if approval.status != "pending":
        messages.error(request, _("هذا الطلب تم التعامل معه مسبقاً"))
        return redirect("pricing:approval_detail", pk=approval_id)

    action = request.POST.get("action")
    comments = request.POST.get("comments", "")

    if action == "approve":
        approval.status = "approved"
        approval.approved_at = timezone.now()
        approval.comments = comments
        approval.save()

        messages.success(request, _("تم الموافقة على الطلب بنجاح"))

    elif action == "reject":
        approval.status = "rejected"
        approval.comments = comments
        approval.save()

        messages.success(request, _("تم رفض الطلب"))

    return redirect("pricing:approval_detail", pk=approval_id)


class PricingReportListView(LoginRequiredMixin, ListView):
    """عرض قائمة التقارير"""

    model = PricingReport
    template_name = "pricing/reports_list.html"
    context_object_name = "reports"
    paginate_by = 10

    def get_queryset(self):
        return PricingReport.objects.select_related("generated_by").order_by(
            "-created_at"
        )


class PricingKPIListView(LoginRequiredMixin, ListView):
    """عرض قائمة مؤشرات الأداء"""

    model = PricingKPI
    template_name = "pricing/kpis_list.html"
    context_object_name = "kpis"
    paginate_by = 20

    def get_queryset(self):
        return PricingKPI.objects.order_by("-period_start", "kpi_type")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # إحصائيات سريعة
        context["total_orders"] = PricingOrder.objects.count()
        context["total_quotations"] = PricingQuotation.objects.count()
        context["pending_approvals"] = PricingApproval.objects.filter(
            status="pending"
        ).count()

        return context


@login_required
def pricing_dashboard(request):
    """لوحة تحكم التسعير"""
    context = {
        "total_orders": PricingOrder.objects.count(),
        "total_quotations": PricingQuotation.objects.count(),
        "pending_approvals": PricingApproval.objects.filter(status="pending").count(),
        "active_workflows": PricingApprovalWorkflow.objects.filter(
            is_active=True
        ).count(),
        # الطلبات الحديثة
        "recent_orders": PricingOrder.objects.select_related("client", "created_by")[
            :5
        ],
        # العروض الحديثة
        "recent_quotations": PricingQuotation.objects.select_related(
            "pricing_order", "created_by"
        )[:5],
        # الموافقات المعلقة للمستخدم الحالي
        "my_pending_approvals": PricingApproval.objects.filter(
            approver=request.user, status="pending"
        ).select_related("pricing_order", "workflow")[:5],
        # بيانات الصفحة والبريدكرمب
        "page_title": "لوحة تحكم التسعير",
        "page_icon": "fas fa-tachometer-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "لوحة التحكم",
                "url": "",
                "icon": "fas fa-tachometer-alt",
                "active": True,
            },
        ],
    }

    return render(request, "pricing/dashboard.html", context)


# ==================== إعدادات ماكينات الديجيتال ====================

# إعدادات أنواع ماكينات الديجيتال
@login_required
def digital_machine_type_list(request):
    """قائمة أنواع ماكينات الديجيتال"""
    from .models import DigitalMachineType

    machine_types = DigitalMachineType.objects.all().order_by("manufacturer", "name")

    context = {
        "machine_types": machine_types,
        "page_title": "إعدادات أنواع ماكينات الديجيتال",
        "page_icon": "fas fa-desktop",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أنواع ماكينات الديجيتال", "active": True},
        ],
    }

    return render(request, "pricing/settings/digital_machine_type/list.html", context)


@login_required
def digital_machine_type_create(request):
    """إنشاء نوع ماكينة ديجيتال جديد"""
    from .forms import DigitalMachineTypeForm

    if request.method == "POST":
        form = DigitalMachineTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء نوع الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:digital_machine_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/digital_machine_type/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة نوع ماكينة جديد",
                        "action_url": reverse("pricing:digital_machine_type_create"),
                    },
                )

    form = DigitalMachineTypeForm()
    return render(
        request,
        "pricing/settings/digital_machine_type/form_modal.html",
        {
            "form": form,
            "title": "إضافة نوع ماكينة جديد",
            "action_url": reverse("pricing:digital_machine_type_create"),
        },
    )


@login_required
def digital_machine_type_edit(request, pk):
    """تعديل نوع ماكينة ديجيتال"""
    from .forms import DigitalMachineTypeForm
    from .models import DigitalMachineType

    try:
        machine_type = DigitalMachineType.objects.get(pk=pk)
    except DigitalMachineType.DoesNotExist:
        messages.error(request, "نوع الماكينة غير موجود")
        return redirect("pricing:digital_machine_type_list")

    if request.method == "POST":
        form = DigitalMachineTypeForm(request.POST, instance=machine_type)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث نوع الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:digital_machine_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/digital_machine_type/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {machine_type.name}",
                        "action_url": reverse(
                            "pricing:digital_machine_type_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = DigitalMachineTypeForm(instance=machine_type)
    return render(
        request,
        "pricing/settings/digital_machine_type/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {machine_type.name}",
            "action_url": reverse(
                "pricing:digital_machine_type_edit", kwargs={"pk": pk}
            ),
        },
    )


@login_required
def digital_machine_type_delete(request, pk):
    """حذف نوع ماكينة ديجيتال"""
    from .models import DigitalMachineType

    try:
        machine_type = DigitalMachineType.objects.get(pk=pk)
    except DigitalMachineType.DoesNotExist:
        messages.error(request, "نوع الماكينة غير موجود")
        return redirect("pricing:digital_machine_type_list")

    if request.method == "POST":
        machine_type_name = machine_type.name
        machine_type.delete()
        messages.success(request, f'تم حذف نوع الماكينة "{machine_type_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:digital_machine_type_list")

    return render(
        request,
        "pricing/settings/digital_machine_type/delete_modal.html",
        {
            "machine_type": machine_type,
            "action_url": reverse(
                "pricing:digital_machine_type_delete", kwargs={"pk": pk}
            ),
        },
    )


# إعدادات مقاسات ماكينات الديجيتال
@login_required
def digital_sheet_size_list(request):
    """قائمة مقاسات ماكينات الديجيتال"""
    from .models import DigitalSheetSize

    sheet_sizes = DigitalSheetSize.objects.all().order_by("width_cm", "height_cm")

    context = {
        "sheet_sizes": sheet_sizes,
        "page_title": "إعدادات مقاسات ماكينات الديجيتال",
        "page_icon": "fas fa-expand-arrows-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "مقاسات ماكينات الديجيتال", "active": True},
        ],
    }

    return render(request, "pricing/settings/digital_sheet_size/list.html", context)


@login_required
def digital_sheet_size_create(request):
    """إنشاء مقاس ماكينة ديجيتال جديد"""
    from .forms import DigitalSheetSizeForm

    if request.method == "POST":
        form = DigitalSheetSizeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء مقاس الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:digital_sheet_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/digital_sheet_size/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة مقاس جديد",
                        "action_url": reverse("pricing:digital_sheet_size_create"),
                    },
                )

    form = DigitalSheetSizeForm()
    return render(
        request,
        "pricing/settings/digital_sheet_size/form_modal.html",
        {
            "form": form,
            "title": "إضافة مقاس جديد",
            "action_url": reverse("pricing:digital_sheet_size_create"),
        },
    )


@login_required
def digital_sheet_size_edit(request, pk):
    """تعديل مقاس ماكينة ديجيتال"""
    from .forms import DigitalSheetSizeForm
    from .models import DigitalSheetSize

    try:
        sheet_size = DigitalSheetSize.objects.get(pk=pk)
    except DigitalSheetSize.DoesNotExist:
        messages.error(request, "مقاس الماكينة غير موجود")
        return redirect("pricing:digital_sheet_size_list")

    if request.method == "POST":
        form = DigitalSheetSizeForm(request.POST, instance=sheet_size)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث مقاس الماكينة بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:digital_sheet_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/digital_sheet_size/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {sheet_size.name}",
                        "action_url": reverse(
                            "pricing:digital_sheet_size_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = DigitalSheetSizeForm(instance=sheet_size)
    return render(
        request,
        "pricing/settings/digital_sheet_size/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {sheet_size.name}",
            "action_url": reverse("pricing:digital_sheet_size_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def digital_sheet_size_delete(request, pk):
    """حذف مقاس ماكينة ديجيتال"""
    from .models import DigitalSheetSize

    try:
        sheet_size = DigitalSheetSize.objects.get(pk=pk)
    except DigitalSheetSize.DoesNotExist:
        messages.error(request, "مقاس الماكينة غير موجود")
        return redirect("pricing:digital_sheet_size_list")

    if request.method == "POST":
        sheet_size_name = sheet_size.name
        sheet_size.delete()
        messages.success(request, f'تم حذف مقاس الماكينة "{sheet_size_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:digital_sheet_size_list")

    return render(
        request,
        "pricing/settings/digital_sheet_size/delete_modal.html",
        {
            "sheet_size": sheet_size,
            "action_url": reverse(
                "pricing:digital_sheet_size_delete", kwargs={"pk": pk}
            ),
        },
    )


# ===== إعدادات أوزان الورق =====


@login_required
def paper_weight_list(request):
    """قائمة أوزان الورق"""
    from .models import PaperWeight

    weights = PaperWeight.objects.all().order_by("gsm")

    context = {
        "paper_weights": weights,
        "page_title": "إعدادات أوزان الورق",
        "page_icon": "fas fa-weight-hanging",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أوزان الورق", "active": True},
        ],
    }

    return render(request, "pricing/settings/paper_weights/list.html", context)


@login_required
def paper_weight_create(request):
    """إنشاء وزن ورق جديد"""
    from .models import PaperWeight
    from .forms import PaperWeightForm

    if request.method == "POST":
        form = PaperWeightForm(request.POST)
        if form.is_valid():
            weight = form.save()
            messages.success(request, f'تم إنشاء وزن الورق "{weight.name}" بنجاح')

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_weight_list")
        else:
            # في حالة وجود أخطاء في النموذج
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperWeightForm()

    return render(
        request,
        "pricing/settings/paper_weights/form_modal.html",
        {
            "form": form,
            "title": "إضافة وزن ورق جديد",
            "action_url": reverse("pricing:paper_weight_create"),
        },
    )


@login_required
def paper_weight_edit(request, pk):
    """تعديل وزن ورق"""
    from .models import PaperWeight
    from .forms import PaperWeightForm

    try:
        weight = PaperWeight.objects.get(pk=pk)
    except PaperWeight.DoesNotExist:
        messages.error(request, "وزن الورق غير موجود")
        return redirect("pricing:paper_weight_list")

    if request.method == "POST":
        form = PaperWeightForm(request.POST, instance=weight)
        if form.is_valid():
            weight = form.save()
            messages.success(request, f'تم تحديث وزن الورق "{weight.name}" بنجاح')

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_weight_list")
        else:
            # في حالة وجود أخطاء في النموذج
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperWeightForm(instance=weight)

    return render(
        request,
        "pricing/settings/paper_weights/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {weight.name}",
            "action_url": reverse("pricing:paper_weight_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def paper_weight_delete(request, pk):
    """حذف وزن ورق"""
    from .models import PaperWeight

    try:
        weight = PaperWeight.objects.get(pk=pk)
    except PaperWeight.DoesNotExist:
        messages.error(request, "وزن الورق غير موجود")
        return redirect("pricing:paper_weight_list")

    if request.method == "POST":
        weight_name = weight.name
        weight.delete()
        messages.success(request, f'تم حذف وزن الورق "{weight_name}" بنجاح')

        # التحقق من AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:paper_weight_list")

    return render(
        request,
        "pricing/settings/paper_weights/delete_modal.html",
        {
            "weight": weight,
            "action_url": reverse("pricing:paper_weight_delete", kwargs={"pk": pk}),
        },
    )


# ===== إعدادات أنواع الورق =====


@login_required
def paper_type_list(request):
    """قائمة أنواع الورق"""
    from .models import PaperType

    paper_types = PaperType.objects.all().order_by("name")

    context = {
        "paper_types": paper_types,
        "page_title": "إعدادات أنواع الورق",
        "page_icon": "fas fa-layer-group",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أنواع الورق", "active": True},
        ],
    }

    return render(request, "pricing/settings/paper_types/list.html", context)


@login_required
def paper_type_create(request):
    """إنشاء نوع ورق جديد"""
    from .models import PaperType
    from .forms import PaperTypeForm

    if request.method == "POST":
        form = PaperTypeForm(request.POST)
        if form.is_valid():
            paper_type = form.save()
            messages.success(request, f'تم إنشاء نوع الورق "{paper_type.name}" بنجاح')

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_type_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperTypeForm()

    return render(
        request,
        "pricing/settings/paper_types/form_modal.html",
        {
            "form": form,
            "title": "إضافة نوع ورق جديد",
            "action_url": reverse("pricing:paper_type_create"),
        },
    )


@login_required
def paper_type_edit(request, pk):
    """تعديل نوع ورق"""
    from .models import PaperType
    from .forms import PaperTypeForm

    try:
        paper_type = PaperType.objects.get(pk=pk)
    except PaperType.DoesNotExist:
        messages.error(request, "نوع الورق غير موجود")
        return redirect("pricing:paper_type_list")

    if request.method == "POST":
        form = PaperTypeForm(request.POST, instance=paper_type)
        if form.is_valid():
            paper_type = form.save()
            messages.success(request, f'تم تحديث نوع الورق "{paper_type.name}" بنجاح')

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_type_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperTypeForm(instance=paper_type)

    return render(
        request,
        "pricing/settings/paper_types/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {paper_type.name}",
            "action_url": reverse("pricing:paper_type_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def paper_type_delete(request, pk):
    """حذف نوع ورق"""
    from .models import PaperType

    try:
        paper_type = PaperType.objects.get(pk=pk)
    except PaperType.DoesNotExist:
        messages.error(request, "نوع الورق غير موجود")
        return redirect("pricing:paper_type_list")

    if request.method == "POST":
        paper_type_name = paper_type.name
        paper_type.delete()
        messages.success(request, f'تم حذف نوع الورق "{paper_type_name}" بنجاح')

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:paper_type_list")

    return render(
        request,
        "pricing/settings/paper_types/delete_modal.html",
        {
            "paper_type": paper_type,
            "action_url": reverse("pricing:paper_type_delete", kwargs={"pk": pk}),
        },
    )


# ===== إعدادات أحجام الورق =====


@login_required
def paper_size_list(request):
    """قائمة أحجام الورق"""
    from .models import PaperSize

    paper_sizes = PaperSize.objects.all().order_by("name")

    context = {
        "paper_sizes": paper_sizes,
        "page_title": "إعدادات أحجام الورق",
        "page_icon": "fas fa-ruler-combined",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أحجام الورق", "active": True},
        ],
    }

    return render(request, "pricing/settings/paper_sizes/list.html", context)


@login_required
def paper_size_create(request):
    """إنشاء حجم ورق جديد"""
    from .models import PaperSize
    from .forms import PaperSizeForm

    if request.method == "POST":
        form = PaperSizeForm(request.POST)
        if form.is_valid():
            paper_size = form.save()
            messages.success(request, f'تم إنشاء حجم الورق "{paper_size.name}" بنجاح')

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_size_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperSizeForm()

    return render(
        request,
        "pricing/settings/paper_sizes/form_modal.html",
        {
            "form": form,
            "title": "إضافة حجم ورق جديد",
            "action_url": reverse("pricing:paper_size_create"),
        },
    )


@login_required
def paper_size_edit(request, pk):
    """تعديل حجم ورق"""
    from .models import PaperSize
    from .forms import PaperSizeForm

    try:
        paper_size = PaperSize.objects.get(pk=pk)
    except PaperSize.DoesNotExist:
        messages.error(request, "حجم الورق غير موجود")
        return redirect("pricing:paper_size_list")

    if request.method == "POST":
        form = PaperSizeForm(request.POST, instance=paper_size)
        if form.is_valid():
            paper_size = form.save()
            messages.success(request, f'تم تحديث حجم الورق "{paper_size.name}" بنجاح')

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_size_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperSizeForm(instance=paper_size)

    return render(
        request,
        "pricing/settings/paper_sizes/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {paper_size.name}",
            "action_url": reverse("pricing:paper_size_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def paper_size_delete(request, pk):
    """حذف حجم ورق"""
    from .models import PaperSize

    try:
        paper_size = PaperSize.objects.get(pk=pk)
    except PaperSize.DoesNotExist:
        messages.error(request, "حجم الورق غير موجود")
        return redirect("pricing:paper_size_list")

    if request.method == "POST":
        paper_size_name = paper_size.name
        paper_size.delete()
        messages.success(request, f'تم حذف حجم الورق "{paper_size_name}" بنجاح')

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:paper_size_list")

    return render(
        request,
        "pricing/settings/paper_sizes/delete_modal.html",
        {
            "paper_size": paper_size,
            "action_url": reverse("pricing:paper_size_delete", kwargs={"pk": pk}),
        },
    )


# ===== إعدادات منشأ الورق =====


@login_required
def paper_origin_list(request):
    """قائمة منشأ الورق"""
    from .models import PaperOrigin

    paper_origins = PaperOrigin.objects.all().order_by("name")

    context = {
        "paper_origins": paper_origins,
        "page_title": "إعدادات منشأ الورق",
        "page_icon": "fas fa-globe",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "منشأ الورق", "active": True},
        ],
    }

    return render(request, "pricing/settings/paper_origins/list.html", context)


@login_required
def paper_origin_create(request):
    """إنشاء منشأ ورق جديد"""
    from .models import PaperOrigin
    from .forms import PaperOriginForm

    if request.method == "POST":
        form = PaperOriginForm(request.POST)
        if form.is_valid():
            paper_origin = form.save()
            messages.success(
                request, f'تم إنشاء منشأ الورق "{paper_origin.name}" بنجاح'
            )

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_origin_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperOriginForm()

    return render(
        request,
        "pricing/settings/paper_origins/form_modal.html",
        {
            "form": form,
            "title": "إضافة منشأ ورق جديد",
            "action_url": reverse("pricing:paper_origin_create"),
        },
    )


@login_required
def paper_origin_edit(request, pk):
    """تعديل منشأ ورق"""
    from .models import PaperOrigin
    from .forms import PaperOriginForm

    try:
        paper_origin = PaperOrigin.objects.get(pk=pk)
    except PaperOrigin.DoesNotExist:
        messages.error(request, "منشأ الورق غير موجود")
        return redirect("pricing:paper_origin_list")

    if request.method == "POST":
        form = PaperOriginForm(request.POST, instance=paper_origin)
        if form.is_valid():
            paper_origin = form.save()
            messages.success(
                request, f'تم تحديث منشأ الورق "{paper_origin.name}" بنجاح'
            )

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:paper_origin_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PaperOriginForm(instance=paper_origin)

    return render(
        request,
        "pricing/settings/paper_origins/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {paper_origin.name}",
            "action_url": reverse("pricing:paper_origin_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def paper_origin_delete(request, pk):
    """حذف منشأ ورق"""
    from .models import PaperOrigin

    try:
        paper_origin = PaperOrigin.objects.get(pk=pk)
    except PaperOrigin.DoesNotExist:
        messages.error(request, "منشأ الورق غير موجود")
        return redirect("pricing:paper_origin_list")

    if request.method == "POST":
        paper_origin_name = paper_origin.name
        paper_origin.delete()
        messages.success(request, f'تم حذف منشأ الورق "{paper_origin_name}" بنجاح')

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:paper_origin_list")

    return render(
        request,
        "pricing/settings/paper_origins/delete_modal.html",
        {
            "paper_origin": paper_origin,
            "action_url": reverse("pricing:paper_origin_delete", kwargs={"pk": pk}),
        },
    )


# ==================== إعدادات أنواع المنتجات ====================


@login_required
def product_type_list(request):
    """قائمة أنواع المنتجات"""
    from .models import ProductType

    product_types = ProductType.objects.all().order_by("name")

    context = {
        "product_types": product_types,
        "page_title": "إعدادات أنواع المنتجات",
        "page_icon": "fas fa-box",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "أنواع المنتجات", "active": True},
        ],
    }

    return render(request, "pricing/settings/product_types/list.html", context)


@login_required
def product_type_create(request):
    """إنشاء نوع منتج جديد"""
    from .forms import ProductTypeForm

    if request.method == "POST":
        form = ProductTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء نوع المنتج بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:product_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/product_types/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة نوع منتج جديد",
                        "action_url": reverse("pricing:product_type_create"),
                    },
                )

    form = ProductTypeForm()
    return render(
        request,
        "pricing/settings/product_types/form_modal.html",
        {
            "form": form,
            "title": "إضافة نوع منتج جديد",
            "action_url": reverse("pricing:product_type_create"),
        },
    )


@login_required
def product_type_edit(request, pk):
    """تعديل نوع منتج"""
    from .forms import ProductTypeForm
    from .models import ProductType

    try:
        product_type = ProductType.objects.get(pk=pk)
    except ProductType.DoesNotExist:
        messages.error(request, "نوع المنتج غير موجود")
        return redirect("pricing:product_type_list")

    if request.method == "POST":
        form = ProductTypeForm(request.POST, instance=product_type)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث نوع المنتج بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:product_type_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/product_types/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {product_type.name}",
                        "action_url": reverse(
                            "pricing:product_type_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = ProductTypeForm(instance=product_type)
    return render(
        request,
        "pricing/settings/product_types/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {product_type.name}",
            "action_url": reverse("pricing:product_type_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def product_type_delete(request, pk):
    """حذف نوع منتج"""
    from .models import ProductType

    try:
        product_type = ProductType.objects.get(pk=pk)
    except ProductType.DoesNotExist:
        messages.error(request, "نوع المنتج غير موجود")
        return redirect("pricing:product_type_list")

    if request.method == "POST":
        product_type_name = product_type.name
        product_type.delete()
        messages.success(request, f'تم حذف نوع المنتج "{product_type_name}" بنجاح')

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:product_type_list")

    return render(
        request,
        "pricing/settings/product_types/delete_modal.html",
        {
            "product_type": product_type,
            "action_url": reverse("pricing:product_type_delete", kwargs={"pk": pk}),
        },
    )


# ==================== إعدادات مقاسات المنتجات ====================


@login_required
def product_size_list(request):
    """قائمة مقاسات المنتجات"""
    from .models import ProductSize

    product_sizes = ProductSize.objects.all().order_by("name")

    context = {
        "product_sizes": product_sizes,
        "page_title": "إعدادات مقاسات المنتجات",
        "page_icon": "fas fa-ruler-combined",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "مقاسات المنتجات", "active": True},
        ],
    }

    return render(request, "pricing/settings/product_sizes/list.html", context)


@login_required
def product_size_create(request):
    """إنشاء مقاس منتج جديد"""
    from .forms import ProductSizeForm

    if request.method == "POST":
        form = ProductSizeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إنشاء مقاس المنتج بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:product_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/product_sizes/form_modal.html",
                    {
                        "form": form,
                        "title": "إضافة مقاس منتج جديد",
                        "action_url": reverse("pricing:product_size_create"),
                    },
                )

    form = ProductSizeForm()
    return render(
        request,
        "pricing/settings/product_sizes/form_modal.html",
        {
            "form": form,
            "title": "إضافة مقاس منتج جديد",
            "action_url": reverse("pricing:product_size_create"),
        },
    )


@login_required
def product_size_edit(request, pk):
    """تعديل مقاس منتج"""
    from .forms import ProductSizeForm
    from .models import ProductSize

    try:
        product_size = ProductSize.objects.get(pk=pk)
    except ProductSize.DoesNotExist:
        messages.error(request, "مقاس المنتج غير موجود")
        return redirect("pricing:product_size_list")

    if request.method == "POST":
        form = ProductSizeForm(request.POST, instance=product_size)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث مقاس المنتج بنجاح")

            # التحقق من AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:product_size_list")
        else:
            # التحقق من AJAX request للأخطاء
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
            else:
                # في حالة عدم وجود AJAX، أعد عرض النموذج مع الأخطاء
                return render(
                    request,
                    "pricing/settings/product_sizes/form_modal.html",
                    {
                        "form": form,
                        "title": f"تعديل {product_size.name}",
                        "action_url": reverse(
                            "pricing:product_size_edit", kwargs={"pk": pk}
                        ),
                    },
                )

    form = ProductSizeForm(instance=product_size)
    return render(
        request,
        "pricing/settings/product_sizes/form_modal.html",
        {
            "form": form,
            "title": f"تعديل {product_size.name}",
            "action_url": reverse("pricing:product_size_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def product_size_delete(request, pk):
    """حذف مقاس منتج"""
    from .models import ProductSize

    try:
        product_size = ProductSize.objects.get(pk=pk)
    except ProductSize.DoesNotExist:
        messages.error(request, "مقاس المنتج غير موجود")
        return redirect("pricing:product_size_list")

    if request.method == "POST":
        product_size_name = product_size.name
        product_size.delete()
        messages.success(request, f'تم حذف مقاس المنتج "{product_size_name}" بنجاح')

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:product_size_list")

    return render(
        request,
        "pricing/settings/product_sizes/delete_modal.html",
        {
            "product_size": product_size,
            "action_url": reverse("pricing:product_size_delete", kwargs={"pk": pk}),
        },
    )


# ===== إعدادات مقاسات الزنكات =====


@login_required
def plate_size_list(request):
    """قائمة مقاسات الزنكات"""
    from .models import PlateSize

    plate_sizes = PlateSize.objects.all().order_by("name")

    context = {
        "plate_sizes": plate_sizes,
        "page_title": "إعدادات مقاسات الزنكات",
        "page_icon": "fas fa-th-large",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "التسعير",
                "url": reverse("pricing:pricing_dashboard"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "الإعدادات",
                "url": reverse("pricing:settings_home"),
                "icon": "fas fa-cog",
            },
            {"title": "مقاسات الزنكات", "active": True},
        ],
    }

    return render(request, "pricing/settings/plate_sizes/list.html", context)


@login_required
def plate_size_create(request):
    """إنشاء مقاس زنك جديد"""
    from .models import PlateSize
    from .forms_plates import PlateSizeForm

    if request.method == "POST":
        form = PlateSizeForm(request.POST)
        if form.is_valid():
            plate_size = form.save()
            messages.success(request, f'تم إنشاء مقاس الزنك "{plate_size.name}" بنجاح')

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:plate_size_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PlateSizeForm()

    return render(
        request,
        "pricing/settings/plate_sizes/form_modal.html",
        {
            "form": form,
            "title": "إضافة مقاس زنك جديد",
            "action_url": reverse("pricing:plate_size_create"),
        },
    )


@login_required
def plate_size_edit(request, pk):
    """تعديل مقاس زنك"""
    from .models import PlateSize
    from .forms_plates import PlateSizeForm

    try:
        plate_size = PlateSize.objects.get(pk=pk)
    except PlateSize.DoesNotExist:
        messages.error(request, "مقاس الزنك غير موجود")
        return redirect("pricing:plate_size_list")

    if request.method == "POST":
        form = PlateSizeForm(request.POST, instance=plate_size)
        if form.is_valid():
            plate_size = form.save()
            messages.success(request, f'تم تحديث مقاس الزنك "{plate_size.name}" بنجاح')

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            else:
                return redirect("pricing:plate_size_list")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})
    else:
        form = PlateSizeForm(instance=plate_size)

    return render(
        request,
        "pricing/settings/plate_sizes/form_modal.html",
        {
            "form": form,
            "title": f'تعديل مقاس الزنك "{plate_size.name}"',
            "action_url": reverse("pricing:plate_size_edit", kwargs={"pk": pk}),
        },
    )


@login_required
def plate_size_delete(request, pk):
    """حذف مقاس زنك"""
    from .models import PlateSize

    try:
        plate_size = PlateSize.objects.get(pk=pk)
    except PlateSize.DoesNotExist:
        messages.error(request, "مقاس الزنك غير موجود")
        return redirect("pricing:plate_size_list")

    if request.method == "POST":
        plate_size_name = plate_size.name
        plate_size.delete()
        messages.success(request, f'تم حذف مقاس الزنك "{plate_size_name}" بنجاح')

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            return redirect("pricing:plate_size_list")

    return render(
        request,
        "pricing/settings/plate_sizes/delete_modal.html",
        {
            "plate_size": plate_size,
            "action_url": reverse("pricing:plate_size_delete", kwargs={"pk": pk}),
        },
    )


# API endpoint لجلب أنواع التغطية
@login_required
def coating_types_api(request):
    """API لجلب أنواع التغطية للاستخدام في النماذج"""
    from django.http import JsonResponse
    from .models import CoatingType
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # جلب جميع أنواع التغطية (بدون فلترة is_active في البداية للتشخيص)
        all_coating_types = CoatingType.objects.all().order_by('name')
        active_coating_types = CoatingType.objects.filter(is_active=True).order_by('name')
        
        logger.info(f"إجمالي أنواع التغطية: {all_coating_types.count()}")
        logger.info(f"أنواع التغطية النشطة: {active_coating_types.count()}")
        
        data = []
        
        # استخدام جميع الأنواع إذا لم توجد أنواع نشطة
        coating_types_to_use = active_coating_types if active_coating_types.exists() else all_coating_types
        
        for coating_type in coating_types_to_use:
            item = {
                'id': coating_type.id,
                'code': coating_type.id,
                'name': coating_type.name,
                'title': coating_type.name,
                'description': getattr(coating_type, 'description', ''),
                'is_active': getattr(coating_type, 'is_active', True),
                'is_default': getattr(coating_type, 'is_default', False)
            }
            data.append(item)
            logger.info(f"تمت إضافة نوع التغطية: {coating_type.name} (ID: {coating_type.id})")
        
        # إذا لم توجد بيانات، أضف بيانات افتراضية
        if not data:
            logger.warning("لا توجد أنواع تغطية في قاعدة البيانات، استخدام البيانات الافتراضية")
            default_types = [
                {'id': 1, 'name': 'ورنيش', 'code': 1, 'title': 'ورنيش'},
                {'id': 2, 'name': 'طلاء UV', 'code': 2, 'title': 'طلاء UV'},
                {'id': 3, 'name': 'طلاء مائي', 'code': 3, 'title': 'طلاء مائي'},
                {'id': 4, 'name': 'UV نقطي', 'code': 4, 'title': 'UV نقطي'},
                {'id': 5, 'name': 'طلاء مطفي', 'code': 5, 'title': 'طلاء مطفي'}
            ]
            data = default_types
        
        logger.info(f"إرسال {len(data)} نوع تغطية")
        return JsonResponse(data, safe=False)
        
    except Exception as e:
        logger.error(f"خطأ في API أنواع التغطية: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_coating_services_by_supplier(request):
    """API لجلب خدمات التغطية حسب المورد"""
    try:
        supplier_id = request.GET.get("supplier_id")
        
        if not supplier_id:
            return JsonResponse({"success": False, "error": "معرف المورد مطلوب"})

        from supplier.models import FinishingServiceDetails, SpecializedService
        
        # جلب جميع خدمات التشطيب للمورد المحدد
        # (سنعتبر جميع خدمات التشطيب كخدمات تغطية محتملة)
        coating_services = FinishingServiceDetails.objects.filter(
            service__supplier_id=supplier_id,
            service__is_active=True
        ).select_related('service')
        
        services_data = []
        for service in coating_services:
            # إنشاء اسم أفضل للخدمة
            service_name = service.get_finishing_type_display()
            if service_name == str(service.finishing_type):
                # إذا كان الاسم مجرد رقم، استخدم اسم الخدمة المتخصصة
                service_name = service.service.name if service.service.name else f"خدمة تشطيب {service.finishing_type}"
            
            services_data.append({
                'id': service.id,
                'name': service_name,
                'finishing_type': service.finishing_type,
                'price_per_unit': float(service.price_per_unit),
                'calculation_method': service.calculation_method,
                'calculation_method_display': service.get_calculation_method_display(),
                'setup_time_minutes': service.setup_time_minutes,
                'min_size_cm': float(service.min_size_cm) if service.min_size_cm else None,
                'max_size_cm': float(service.max_size_cm) if service.max_size_cm else None,
            })
        
        return JsonResponse({
            "success": True, 
            "services": services_data
        })

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_coating_services_by_supplier: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في جلب خدمات التغطية"}
        )


@login_required 
def get_coating_service_price(request):
    """API لجلب سعر خدمة التغطية"""
    try:
        service_id = request.GET.get("service_id")
        quantity = request.GET.get("quantity", 1)
        
        if not service_id:
            return JsonResponse({"success": False, "error": "معرف الخدمة مطلوب"})
            
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            quantity = 1
            
        from supplier.models import FinishingServiceDetails
        
        service = FinishingServiceDetails.objects.get(
            id=service_id,
            service__is_active=True
        )
        
        # حساب السعر حسب طريقة الحساب
        base_price = float(service.price_per_unit)
        
        if service.calculation_method == 'per_piece':
            total_price = base_price * quantity
        elif service.calculation_method == 'per_thousand':
            total_price = base_price * (quantity / 1000)
        elif service.calculation_method == 'per_hour':
            # افتراض ساعة واحدة للكمية الصغيرة
            hours = max(1, quantity / 1000)  # كل 1000 قطعة = ساعة
            total_price = base_price * hours
        elif service.calculation_method == 'per_meter':
            # افتراض متر مربع واحد للكمية الصغيرة
            meters = max(1, quantity / 100)  # كل 100 قطعة = متر مربع
            total_price = base_price * meters
        else:
            total_price = base_price * quantity
            
        return JsonResponse({
            "success": True,
            "price_per_unit": base_price,
            "total_price": round(total_price, 2),
            "calculation_method": service.calculation_method,
            "calculation_method_display": service.get_calculation_method_display(),
            "setup_time_minutes": service.setup_time_minutes
        })

    except FinishingServiceDetails.DoesNotExist:
        return JsonResponse({"success": False, "error": "الخدمة غير موجودة"})
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_coating_service_price: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "error": "خطأ في حساب سعر الخدمة"}
        )
