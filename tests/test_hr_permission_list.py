import pytest
from django.urls import reverse
from django.test import Client
from hr.models import PermissionType
from users.models import User

@pytest.mark.django_db
def test_permission_list_view():
    user = User.objects.create_superuser(
        username="admin_perm",
        email="admin_perm@example.com",
        password="password123"
    )
    PermissionType.objects.create(name_ar="إذن شخصي", code="PERSONAL")

    client = Client()
    client.force_login(user)

    url = reverse("hr:permission_list")
    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert "إذن شخصي" in response.content.decode("utf-8")
