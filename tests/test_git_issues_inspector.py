import os
import pytest
from scripts.check_git_issues import (
    load_env_var,
    get_current_git_repo,
    check_local_git_status,
    inspect_git_issues,
)


def test_load_env_var():
    """اختبار قراءة التوكن من ملف .env"""
    token = load_env_var("GITGUARDIAN_API_KEY")
    assert token is not None
    assert token.startswith("gg_pat_")


def test_get_current_git_repo():
    """اختبار تحديد اسم المستودع الحالي"""
    repo = get_current_git_repo()
    assert "mwheba" in repo.lower()


def test_check_local_git_status():
    """اختبار فحص حالة Git المحلية"""
    status = check_local_git_status()
    assert "branch" in status
    assert "uncommitted_files" in status
    assert "risky_untracked" in status
    assert isinstance(status["risky_untracked"], list)


def test_inspect_git_issues_structure():
    """اختبار جلب الحوادث وهيكل التقرير الخاص بالمستودع"""
    report = inspect_git_issues(fetch_details=False)
    assert report["source_found"] is True
    assert "MWHEBA/mwheba-erp" in report["active_source"]["name"]
    assert report["open_incidents_count"] >= 0
    assert isinstance(report["incidents"], list)
