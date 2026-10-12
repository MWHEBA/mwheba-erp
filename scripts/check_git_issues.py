#!/usr/bin/env python
"""
Git & GitGuardian Issue Inspector for MWHEBA ERP.
فحص أخطاء ومشاكل وأسرار Git الخاصة بمشروع MWHEBA ERP حصرياً عبر GitGuardian و Git المحلي.
"""

import os
import sys
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

# Base project path
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """قراءة متغير من البيئة أو من ملف .env مباشرة"""
    val = os.environ.get(key)
    if val:
        return val

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k == key:
                        return v
        except Exception:
            pass
    return default


def get_current_git_repo() -> str:
    """استخراج اسم المستودع الحالي من Git remote"""
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        url = res.stdout.strip()
        # Extract owner/repo from URL (https or ssh)
        # e.g., https://github.com/MWHEBA/mwheba-erp.git or git@github.com:MWHEBA/mwheba-erp.git
        m = re.search(r"[:/]([^/]+/[^/\.]+)(?:\.git)?$", url)
        if m:
            return m.group(1)
        return url
    except Exception:
        return "MWHEBA/mwheba-erp"


def run_git_command(args: List[str]) -> str:
    """تشغيل أمر git والحصول على المخرجات"""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return res.stdout.strip()
    except Exception as e:
        return f"Error running git {' '.join(args)}: {e}"


def check_local_git_status() -> Dict[str, Any]:
    """فحص حالة Git المحلية للمشروع الحالي بحثاً عن تسريبات أو ملفات حرجة"""
    branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    status_raw = run_git_command(["status", "--porcelain"])
    
    # Sensitive file patterns to flag
    sensitive_patterns = [
        r"\.env($|\..*)",
        r".*\.key$",
        r".*\.pem$",
        r".*\.sql$",
        r".*id_rsa.*",
        r".*secret.*",
        r".*password.*"
    ]
    
    uncommitted_files = []
    risky_untracked = []
    
    if status_raw:
        for line in status_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            status_code = line[:2].strip()
            filepath = line[3:].strip()
            uncommitted_files.append({"status": status_code, "path": filepath})
            
            # Check if risky untracked file
            for pat in sensitive_patterns:
                if re.search(pat, filepath, re.IGNORECASE):
                    risky_untracked.append({"file": filepath, "status": status_code})
                    break

    # Check unpushed commits
    unpushed_raw = run_git_command(["log", "@{u}..HEAD", "--oneline"])
    unpushed_commits = [c for c in unpushed_raw.splitlines() if c.strip()] if "fatal:" not in unpushed_raw else []

    return {
        "branch": branch,
        "uncommitted_count": len(uncommitted_files),
        "uncommitted_files": uncommitted_files,
        "risky_untracked": risky_untracked,
        "unpushed_commits": unpushed_commits
    }


class GitGuardianClient:
    """عميل GitGuardian API للتعامل مع أسرار ومشاكل مستودع محدد"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.gitguardian.com/v1"
        self.headers = {
            "Authorization": f"Token {self.api_key}",
            "User-Agent": "MWHEBA-GitGuardian-Inspector/1.0"
        }

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        import urllib.request
        import urllib.parse

        url = f"{self.base_url}{endpoint}"
        if params:
            qs = urllib.parse.urlencode(params)
            url = f"{url}?{qs}"

        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))

    def get_sources_for_repo(self, repo_full_name: str) -> List[Dict[str, Any]]:
        """العثور على معرّفات المستودع في GitGuardian المطابقة لهذا المشروع فقط"""
        all_sources = self._get("/sources", {"per_page": 100})
        matching = []
        target_clean = repo_full_name.lower().replace("-", "").replace("_", "")
        
        for s in all_sources:
            s_name = s.get("full_name", "").lower().replace("-", "").replace("_", "")
            if s_name == target_clean or repo_full_name.lower() in s.get("full_name", "").lower():
                matching.append(s)
                
        # فرز المصادر لتقديم النشط حالياً أولاً
        matching.sort(key=lambda x: (x.get("monitoring_status") == "active", x.get("id")), reverse=True)
        return matching

    def get_incidents_for_source(self, source_id: int) -> List[Dict[str, Any]]:
        """جلب جميع حوادث الأسرار للمصدر المحدد"""
        return self._get(f"/sources/{source_id}/incidents/secrets", {"per_page": 100})

    def get_incident_details(self, incident_id: int) -> Dict[str, Any]:
        """جلب تفاصيل حادث محدد مع أماكن التواجد والملفات المتأثرة"""
        return self._get(f"/incidents/secrets/{incident_id}")


def inspect_git_issues(api_key: Optional[str] = None, show_all: bool = False, fetch_details: bool = True) -> Dict[str, Any]:
    """الفحص الشامل لمشاكل Git الخاصة بهذا المشروع"""
    repo_name = get_current_git_repo()
    token = api_key or load_env_var("GITGUARDIAN_API_KEY")

    report = {
        "repository": repo_name,
        "local_git": check_local_git_status(),
        "gitguardian_connected": bool(token),
        "source_found": False,
        "active_source": None,
        "all_sources": [],
        "open_incidents_count": 0,
        "ignored_incidents_count": 0,
        "resolved_incidents_count": 0,
        "incidents": [],
        "error": None
    }

    if not token:
        report["error"] = "مفتاح GITGUARDIAN_API_KEY غير موجود في متغيرات البيئة أو ملف .env"
        return report

    try:
        client = GitGuardianClient(token)
        sources = client.get_sources_for_repo(repo_name)
        
        if not sources:
            report["error"] = f"لم يتم العثور على مستودع في GitGuardian يطابق: {repo_name}"
            return report

        report["source_found"] = True
        report["all_sources"] = [{"id": s["id"], "name": s["full_name"], "status": s.get("monitoring_status")} for s in sources]
        
        active_source = sources[0]
        report["active_source"] = {
            "id": active_source["id"],
            "name": active_source.get("full_name"),
            "status": active_source.get("monitoring_status"),
            "health": active_source.get("health")
        }

        # جلب الحوادث الخاصة بالمستودع النشط
        raw_incidents = client.get_incidents_for_source(active_source["id"])
        
        for inc in raw_incidents:
            status = inc.get("status", "")
            if status == "TRIGGERED":
                report["open_incidents_count"] += 1
            elif status == "IGNORED":
                report["ignored_incidents_count"] += 1
            elif status == "RESOLVED":
                report["resolved_incidents_count"] += 1

            # هل نضيف الحادث للتقرير؟
            # إذا كان مفتوح (TRIGGERED) يضاف دائماً، أو إذا تم طلب show_all
            if status == "TRIGGERED" or show_all:
                inc_info = {
                    "id": inc.get("id"),
                    "name": inc.get("incident_name"),
                    "severity": inc.get("severity", "unknown").upper(),
                    "status": status,
                    "date": inc.get("date"),
                    "url": inc.get("gitguardian_url"),
                    "files": []
                }

                if fetch_details:
                    try:
                        det = client.get_incident_details(inc["id"])
                        occs = det.get("occurrences", [])
                        files = list(set(o.get("filepath") for o in occs if o.get("filepath")))
                        inc_info["files"] = files
                        inc_info["occurrences_count"] = len(occs)
                        inc_info["tags"] = det.get("tags", [])
                    except Exception:
                        pass

                report["incidents"].append(inc_info)

    except Exception as e:
        report["error"] = f"خطأ أثناء الاتصال بـ GitGuardian API: {str(e)}"

    return report


def print_formatted_report(report: Dict[str, Any], show_all: bool = False):
    """طباعة تقرير منسق وواضح جداً في الطرفية باللغتين العربية والإنجليزية"""
    print("\n" + "=" * 70)
    print(" 🛡️  MWHEBA ERP - GIT & GITGUARDIAN SECURITY INSPECTOR")
    print(" تقرير أخطاء ومشاكل وسجلات Git الخاصة بمشروع MWHEBA ERP")
    print("=" * 70)

    repo = report["repository"]
    print(f"\n📂 المستودع المستهدف (Current Target): {repo}")

    # Local Git section
    local = report.get("local_git", {})
    print("\n" + "-" * 70)
    print(" 💻 الحالة المحلية للمستودع (Local Git Health):")
    print("-" * 70)
    print(f"  • الفرع الحالي (Branch): {local.get('branch', 'unknown')}")
    print(f"  • ملفات بها تعديلات غير محفوظة: {local.get('uncommitted_count', 0)}")
    
    if local.get("risky_untracked"):
        print("  ⚠️ تحذير: تم اكتشاف ملفات حساسة غير متجاهلة محلياً:")
        for r in local["risky_untracked"]:
            print(f"     - [{r['status']}] {r['file']}")
    else:
        print("  ✓ لا توجد ملفات حساسة أو مفاتيح غير مؤمنة في التعديلات المحلية")

    if local.get("unpushed_commits"):
        print(f"  • تنبيه: هناك {len(local['unpushed_commits'])} كوميت لم يتم رفعها لـ remote:")
        for c in local["unpushed_commits"][:5]:
            print(f"     * {c}")

    # GitGuardian Section
    print("\n" + "-" * 70)
    print(" ☁️  فحص أسرار وحوادث GitGuardian (Cloud Repository Incidents):")
    print("-" * 70)

    if report.get("error"):
        print(f"  ❌ خطأ: {report['error']}")
        print("=" * 70 + "\n")
        return

    active_src = report.get("active_source", {})
    print(f"  • المصدر في GitGuardian: {active_src.get('name')} (ID: {active_src.get('id')})")
    print(f"  • حالة المراقبة (Monitoring): {active_src.get('status')} | صحة المستودع: {active_src.get('health')}")
    print(f"  • ملخص الحوادث:")
    print(f"     🚨 مصايب مفتوحة تتطلب تدخل (TRIGGERED/OPEN): {report['open_incidents_count']}")
    print(f"     ⏸️  حوادث تم تجاهلها (IGNORED): {report['ignored_incidents_count']}")
    print(f"     ✅ حوادث تم حلها (RESOLVED): {report['resolved_incidents_count']}")

    incidents = report.get("incidents", [])
    if not incidents:
        if report['open_incidents_count'] == 0:
            print("\n  🎉 مبروك! لا توجد أي تسريبات أو أسرار مفتوحة لهذا المشروع على GitGuardian.")
        else:
            print("\n  لا توجد عناصر لعرضها وفق الفلتر المحدد.")
    else:
        print(f"\n 🚨 قائمة الأسرار والمشاكل المفتوحة ({len(incidents)} حادثة):")
        print(" " + "-" * 68)
        for idx, inc in enumerate(incidents, 1):
            sev_badge = f"[{inc['severity']}]"
            print(f"  {idx}. {sev_badge} {inc['name']} (Incident #{inc['id']})")
            print(f"     الحالة: {inc['status']} | التاريخ: {inc.get('date', 'N/A')[:10]}")
            if inc.get("files"):
                print(f"     الملفات المتأثرة: {', '.join(inc['files'])}")
            print(f"     رابط المعالجة: {inc['url']}")
            print()

    print("=" * 70)
    print("💡 نصيحة: لحل أو تجاهل أي حادثة، افتح الرابط المباشر في GitGuardian أو استخدم أداة المعالجة.")
    print("=" * 70 + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MWHEBA ERP Git & Secrets Inspector")
    parser.add_argument("--all", action="store_true", help="عرض جميع الحوادث بما فيها المتجاهلة والمحلولة")
    parser.add_argument("--json", action="store_true", help="إخراج النتيجة بصيغة JSON")
    parser.add_argument("--no-details", action="store_true", help="تخطي جلب تفاصيل الملفات لتسريع الفحص")
    args = parser.parse_args()

    report = inspect_git_issues(show_all=args.all, fetch_details=not args.no_details)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_formatted_report(report, show_all=args.all)


if __name__ == "__main__":
    main()
