# -*- coding: utf-8 -*-
"""
Tests for Wave 1 - Phase 0:
ModuleAccessMiddleware Hardened Fail-Closed Guard, Real Estate API Blocking,
and Dynamic SystemModule Toggle Synchronization.
"""
import json
import pytest
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware

User = get_user_model()


@pytest.fixture(autouse=True)
def clean_cache():
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')
    yield
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')


@pytest.mark.django_db
class TestPhase0ModuleToggleAndMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        self.dummy_response = b"OK_REAL_ESTATE"
        self.middleware = ModuleAccessMiddleware(lambda req: self._mock_response(req))

    def _mock_response(self, request):
        from django.http import HttpResponse
        return HttpResponse(self.dummy_response)

    def _prepare_request(self, request):
        setattr(request, 'session', {})
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def test_real_estate_web_route_blocked_when_module_disabled(self):
        """
        عند تعطيل تطبيق العقارات في SystemModule، يتم حظر مسار الويب وإعادة التوجيه للوحة التحكم
        """
        SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={'name_ar': 'التطوير العقاري', 'is_enabled': False}
        )
        ModuleAccessMiddleware.invalidate_cache()

        request = self.factory.get('/real-estate/projects/1/matrix/')
        request = self._prepare_request(request)
        response = self.middleware(request)

        assert response.status_code == 302
        assert response.url in ['/dashboard/', '/']

    def test_real_estate_web_route_allowed_when_module_enabled(self):
        """
        عند تفعيل تطبيق العقارات، يسمح الـ Middleware بمرور الطلب طبيعياً
        """
        SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
        )
        ModuleAccessMiddleware.invalidate_cache()

        request = self.factory.get('/real-estate/projects/1/matrix/')
        request = self._prepare_request(request)
        response = self.middleware(request)

        assert response.status_code == 200
        assert response.content == self.dummy_response

    def test_real_estate_api_prefix_returns_json_403_when_disabled(self):
        """
        فحص حظر الـ API المباشر ببادئة /real-estate/api/ و /api/real-estate/ بـ JSON 403
        """
        SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={'name_ar': 'التطوير العقاري', 'is_enabled': False}
        )
        ModuleAccessMiddleware.invalidate_cache()

        # اختبار البادئة الأولى
        req1 = self.factory.get('/real-estate/api/units/1/')
        req1 = self._prepare_request(req1)
        res1 = self.middleware(req1)

        assert res1.status_code == 403
        data1 = json.loads(res1.content)
        assert data1['error'] == 'MODULE_DISABLED'
        assert data1['module'] == 'real_estate'

        # اختبار البادئة الثانية
        req2 = self.factory.get('/api/real-estate/units/1/')
        req2 = self._prepare_request(req2)
        res2 = self.middleware(req2)

        assert res2.status_code == 403
        data2 = json.loads(res2.content)
        assert data2['error'] == 'MODULE_DISABLED'
        assert data2['module'] == 'real_estate'

    def test_fail_closed_policy_on_cache_or_database_error(self, monkeypatch):
        """
        اختبار سياسة الفشل المغلق Fail-Closed:
        عند حدوث خطأ أو استثناء أثناء جلب الموديولات، يُحظر الوصول لـ real_estate ويُسمح فقط بـ CORE_MODULES
        """
        # تفريغ الكاش
        cache.delete(ModuleAccessMiddleware.CACHE_KEY_MODULES)

        # محاكاة تعطل استعلام SystemModule
        def mock_error(*args, **kwargs):
            raise RuntimeError("Database connection failure")

        monkeypatch.setattr(SystemModule.objects, "filter", mock_error)

        enabled = ModuleAccessMiddleware._get_enabled_modules()
        # يجب أن يحتوي فقط على تطبيقات core الأساسية
        assert 'real_estate' not in enabled
        assert 'core' in enabled
        assert 'users' in enabled

        # فحص رفض مسار العقارات في وضع الـ Fail-Closed
        request = self.factory.get('/real-estate/api/units/1/')
        request = self._prepare_request(request)
        response = self.middleware(request)
        assert response.status_code == 403

    def test_cache_invalidation_instant_effect(self):
        """
        اختبار إبطال الكاش الفوري: التبديل في قاعدة البيانات يظهر فوراً بمجرد استدعاء invalidate_cache
        """
        mod, _ = SystemModule.objects.update_or_create(
            code='real_estate',
            defaults={'name_ar': 'التطوير العقاري', 'is_enabled': True}
        )
        ModuleAccessMiddleware.invalidate_cache()
        assert ModuleAccessMiddleware._is_module_enabled('real_estate') is True

        # تعطيل
        mod.is_enabled = False
        mod.save()
        ModuleAccessMiddleware.invalidate_cache()
        assert ModuleAccessMiddleware._is_module_enabled('real_estate') is False
