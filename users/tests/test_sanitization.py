# -*- coding: utf-8 -*-
import pytest
from utils.validators import sanitize_email, sanitize_username
from users.forms import UserCreationForm, UserProfileForm


def test_sanitize_email_removes_spaces_and_invisible_chars():
    # Regular space
    assert sanitize_email(" ahmadalhussun@gmail.com ") == "ahmadalhussun@gmail.com"
    # Space after @
    assert sanitize_email("ahmadalhussun@ gmail.com") == "ahmadalhussun@gmail.com"
    # Unicode zero-width space and LTR / RTL marks
    assert sanitize_email("ahmadalhussun\u200e@\u200fgmail.com") == "ahmadalhussun@gmail.com"
    assert sanitize_email("ahmadalhussun@\u200Bgmail.com") == "ahmadalhussun@gmail.com"
    assert sanitize_email("ahmadalhussun@\u00A0gmail.com") == "ahmadalhussun@gmail.com"
    assert sanitize_email("ahmadalhussun@\uFEFFgmail.com") == "ahmadalhussun@gmail.com"
    # Uppercase to lowercase
    assert sanitize_email("AhmadAlhussun@Gmail.COM") == "ahmadalhussun@gmail.com"


def test_sanitize_username_removes_spaces_and_invisible_chars():
    assert sanitize_username("  ahmad_user  ") == "ahmad_user"
    assert sanitize_username("ahmad\u200e_user\u200f") == "ahmad_user"
    assert sanitize_username("ahmad\u00A0user") == "ahmaduser"
