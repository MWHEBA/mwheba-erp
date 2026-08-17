from django.test import TestCase, Client
from django.contrib.auth import authenticate, get_user_model
from django.urls import reverse

User = get_user_model()


class EmailOrUsernameAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password=self.password,
            first_name="Test",
            last_name="User",
            is_active=True,
        )

    def test_authenticate_with_username(self):
        """تسجيل الدخول باستخدام اسم المستخدم"""
        user = authenticate(username="testuser", password=self.password)
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user.pk)

    def test_authenticate_with_username_case_insensitive(self):
        """تسجيل الدخول باسم مستخدم بحروف كبيرة/صغيرة"""
        user = authenticate(username="TestUser", password=self.password)
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user.pk)

    def test_authenticate_with_email(self):
        """تسجيل الدخول باستخدام البريد الإلكتروني"""
        user = authenticate(username="testuser@example.com", password=self.password)
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user.pk)

    def test_authenticate_with_email_case_insensitive_and_whitespace(self):
        """تسجيل الدخول ببريد إلكتروني بحروف كبيرة ومسافات"""
        user = authenticate(username="  TestUser@Example.COM  ", password=self.password)
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user.pk)

    def test_authenticate_wrong_password(self):
        """فشل تسجيل الدخول عند إدخال كلمة مرور خاطئة"""
        user_by_uname = authenticate(username="testuser", password="WrongPassword!")
        self.assertIsNone(user_by_uname)

        user_by_email = authenticate(username="testuser@example.com", password="WrongPassword!")
        self.assertIsNone(user_by_email)

    def test_authenticate_inactive_user(self):
        """فشل تسجيل الدخول للمستخدم غير النشط"""
        self.user.is_active = False
        self.user.save()

        user_by_uname = authenticate(username="testuser", password=self.password)
        self.assertIsNone(user_by_uname)

        user_by_email = authenticate(username="testuser@example.com", password=self.password)
        self.assertIsNone(user_by_email)

    def test_login_view_with_username(self):
        """تسجيل الدخول عبر صفحة /login/ باليوزرنيم"""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": self.password},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_view_with_email(self):
        """تسجيل الدخول عبر صفحة /login/ بالإيميل"""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser@example.com", "password": self.password},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
