# GitHub Actions Workflows

## 🔧 Active Workflows

### 1. **Security Scan** (`security-scan.yml`)
- **Bandit** - Python security linting
- **Safety** - Dependency vulnerability scanning  
- **Semgrep** - Advanced security analysis
- **pip-audit** - Package vulnerability audit
- **TruffleHog** - Secret detection (push events only)

### 2. **Django Tests** (`django-tests.yml`)
- Multi-version testing (Python 3.8-3.11, Django 4.1-4.2)
- Redis service integration
- Database migrations testing
- Comprehensive test suite

### 3. **Code Quality** (`code-quality.yml`)
- **Black** - Code formatting
- **isort** - Import sorting
- **flake8** - Linting
- **mypy** - Type checking
- **radon** - Complexity analysis
- **pylint** - Code quality scoring

## 🔍 CodeQL Analysis

**CodeQL is handled by GitHub's default setup** to avoid SARIF file conflicts.

The default setup provides:
- ✅ Automatic language detection
- ✅ Security-focused queries
- ✅ Regular scanning schedule
- ✅ Integration with GitHub Security tab

## 📝 Notes

- **TruffleHog** only runs on push events to avoid BASE/HEAD conflicts
- **Cache keys** are unique per workflow to prevent conflicts
- **All workflows** use continue-on-error for non-critical steps
- **Security reports** are uploaded as artifacts for review
