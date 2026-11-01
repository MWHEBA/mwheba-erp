import pytest
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth import get_user_model
from django.core.cache import cache
from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware

User = get_user_model()


@pytest.fixture(autouse=True)
def clean_module_cache():
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')
    yield
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')


@pytest.mark.django_db
class TestModuleAccessMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        self.dummy_response_content = b"OK"
        self.middleware = ModuleAccessMiddleware(lambda req: self._mock_response(req))

    def _mock_response(self, request):
        from django.http import HttpResponse
        return HttpResponse(self.dummy_response_content)

    def _prepare_request(self, request):
        setattr(request, 'session', {})
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def test_core_module_routes_always_pass(self):
        request = self.factory.get('/users/login/')
        request = self._prepare_request(request)
        response = self.middleware(request)
        assert response.status_code == 200
        assert response.content == self.dummy_response_content

    def test_enabled_modules_accessible_via_namespace_map(self):
        # customers_sales is enabled
        SystemModule.objects.filter(code='customers_sales').update(is_enabled=True)
        cache.delete('enabled_modules_set')
        
        request = self.factory.get('/sales/invoices/')
        request = self._prepare_request(request)
        response = self.middleware(request)
        assert response.status_code == 200
        assert response.content == self.dummy_response_content

    def test_disabled_module_web_route_redirects_to_dashboard(self):
        # printing_pricing is disabled in DB
        SystemModule.objects.filter(code='printing_pricing').update(is_enabled=False)
        cache.delete('enabled_modules_set')
        
        request = self.factory.get('/printing-pricing/')
        request = self._prepare_request(request)
        response = self.middleware(request)
        assert response.status_code == 302
        assert response.url == '/dashboard/' or response.url == '/'

    def test_disabled_module_api_returns_json_403(self):
        # warehouses disabled
        SystemModule.objects.filter(code='warehouses').update(is_enabled=False)
        cache.delete('enabled_modules_set')
        
        request = self.factory.get('/api/products/')
        request = self._prepare_request(request)
        response = self.middleware(request)
        import json
        assert response.status_code == 403
        data = json.loads(response.content)
        assert data['error'] == 'MODULE_DISABLED'
        assert data['module'] == 'warehouses'
