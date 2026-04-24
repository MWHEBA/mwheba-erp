# HR Module Deployment Guide

**Version:** 1.0  
**Date:** February 19, 2026  
**Environment:** Development → Production  
**Risk Level:** LOW (Development environment, no production data)

## Pre-Deployment Checklist

### 1 Day Before Deployment

- [ ] **All tests passing**
  ```bash
  pytest hr/tests/ -v --cov=hr --cov-report=html
  # Expected: 85/85 tests passing, >80% coverage
  ```

- [ ] **Code review complete**
  - [ ] All PRs reviewed and approved
  - [ ] No critical issues in code review
  - [ ] Security review completed

- [ ] **Documentation updated**
  - [ ] GOVERNANCE_INTEGRATION_GUIDE.md complete
  - [ ] DEPLOYMENT_GUIDE.md complete
  - [ ] BREAKING_CHANGES.md complete
  - [ ] Code docstrings updated

- [ ] **Database backup**
  ```bash
  python manage.py dumpdata > backup_pre_deployment.json
  # Or use database-specific backup
  mysqldump -u user -p database > backup.sql
  ```

- [ ] **Test migrations on staging**
  ```bash
  # On staging environment
  python manage.py migrate --plan
  python manage.py migrate
  python manage.py check --deploy
  ```

- [ ] **Verify no breaking changes**
  - [ ] All deprecated methods have warnings
  - [ ] No direct breaking changes to public APIs
  - [ ] Backward compatibility maintained where possible

- [ ] **Notify team**
  - [ ] Send deployment notification email
  - [ ] Schedule deployment window
  - [ ] Ensure team availability for support

## Deployment Day

### Step 1: Pre-Deployment Verification (15 minutes)

```bash
# 1. Pull latest code
git pull origin main

# 2. Verify branch
git branch
# Should be on main/master

# 3. Check for uncommitted changes
git status
# Should be clean

# 4. Verify tests pass
pytest hr/tests/ -v
# All tests should pass

# 5. Check for security issues
python manage.py check --deploy
# Should report no issues
```

### Step 2: Backup (10 minutes)

```bash
# 1. Backup database
python manage.py dumpdata > backup_deployment_$(date +%Y%m%d_%H%M%S).json

# 2. Backup media files (if any)
tar -czf media_backup_$(date +%Y%m%d_%H%M%S).tar.gz media/

# 3. Verify backups
ls -lh backup_*.json
ls -lh media_backup_*.tar.gz
```

### Step 3: Maintenance Mode (2 minutes)

```bash
# Option 1: Using Django maintenance mode
python manage.py maintenance_mode on

# Option 2: Using web server
# Nginx: Enable maintenance page
sudo ln -s /etc/nginx/sites-available/maintenance /etc/nginx/sites-enabled/
sudo systemctl reload nginx

# Option 3: Using environment variable
export MAINTENANCE_MODE=true
```

### Step 4: Deploy Code (10 minutes)

```bash
# 1. Install/update dependencies
pip install -r requirements.txt

# 2. Collect static files
python manage.py collectstatic --noinput

# 3. Run migrations
python manage.py migrate

# 4. Clear cache
python manage.py clear_cache
# Or manually:
# redis-cli FLUSHDB
```

### Step 5: Restart Services (5 minutes)

```bash
# 1. Restart application server
# Gunicorn:
sudo systemctl restart gunicorn

# uWSGI:
sudo systemctl restart uwsgi

# 2. Restart celery (if used)
sudo systemctl restart celery

# 3. Restart redis (if needed)
sudo systemctl restart redis

# 4. Verify services running
sudo systemctl status gunicorn
sudo systemctl status celery
sudo systemctl status redis
```

### Step 6: Verify Critical Workflows (15 minutes)

```bash
# 1. Check application is running
curl -I http://localhost:8000/
# Should return 200 OK

# 2. Test login
# Open browser and login

# 3. Test payroll creation
# Navigate to HR → Payroll → Create
# Create a test payroll
# Verify it appears in list

# 4. Test journal entry creation
# Verify journal entry was created
# Check in Financial → Journal Entries

# 5. Verify audit trail
# Check governance → Audit Trail
# Verify operations are logged

# 6. Check error logs
tail -f logs/django.log
# Should show no errors
```

### Step 7: Exit Maintenance Mode (2 minutes)

```bash
# Option 1: Django maintenance mode
python manage.py maintenance_mode off

# Option 2: Web server
sudo rm /etc/nginx/sites-enabled/maintenance
sudo systemctl reload nginx

# Option 3: Environment variable
unset MAINTENANCE_MODE
```

### Step 8: Monitor (1 hour)

```bash
# 1. Monitor error logs
tail -f logs/django.log

# 2. Monitor application logs
tail -f logs/application.log

# 3. Monitor web server logs
tail -f /var/log/nginx/error.log

# 4. Monitor system resources
htop
# Check CPU, memory usage

# 5. Monitor database
# Check for slow queries
# Check for connection issues
```

## Post-Deployment Verification

### Immediate Checks (First 15 minutes)

- [ ] **Application accessible**
  - [ ] Homepage loads
  - [ ] Login works
  - [ ] No 500 errors

- [ ] **Payroll creation works**
  - [ ] Can create single payroll
  - [ ] Can process batch payrolls
  - [ ] Calculations are correct

- [ ] **Journal entries created**
  - [ ] Journal entry created for payroll
  - [ ] Entry is balanced
  - [ ] Source linkage correct

- [ ] **Audit trail working**
  - [ ] Operations logged
  - [ ] User tracking correct
  - [ ] Timestamps accurate

- [ ] **Performance acceptable**
  - [ ] Page load < 2 seconds
  - [ ] Payroll creation < 1 second
  - [ ] No timeout errors

### Extended Monitoring (First Hour)

- [ ] **No error spikes**
  - Check error logs
  - Check Sentry/error tracking
  - Check user reports

- [ ] **Performance stable**
  - Monitor response times
  - Check database queries
  - Monitor server resources

- [ ] **User feedback positive**
  - No critical complaints
  - Functionality working as expected
  - No data issues reported

### First Day Monitoring

- [ ] **System stable**
  - No crashes
  - No data corruption
  - No performance degradation

- [ ] **All features working**
  - Payroll processing
  - Journal entry creation
  - Reports generation
  - Data export

- [ ] **Team comfortable**
  - No confusion about new system
  - Documentation helpful
  - Support requests minimal

## Rollback Plan

### When to Rollback

Rollback **immediately** if:

- ❌ Critical functionality broken (payroll creation fails)
- ❌ Data integrity issues (incorrect calculations)
- ❌ Performance degradation > 50% (unacceptable slowness)
- ❌ Multiple user complaints (widespread issues)
- ❌ Security vulnerability discovered
- ❌ Database corruption detected

### Rollback Steps (30 minutes)

#### Step 1: Enable Maintenance Mode (2 minutes)

```bash
python manage.py maintenance_mode on
```

#### Step 2: Stop Services (3 minutes)

```bash
sudo systemctl stop gunicorn
sudo systemctl stop celery
```

#### Step 3: Restore Database (10 minutes)

```bash
# Option 1: Django loaddata
python manage.py flush --noinput
python manage.py loaddata backup_deployment_YYYYMMDD_HHMMSS.json

# Option 2: Database restore
mysql -u user -p database < backup.sql
```

#### Step 4: Revert Code (5 minutes)

```bash
# Get commit hash before deployment
git log --oneline -5

# Revert to previous commit
git revert <commit-hash>
# Or hard reset (if safe)
git reset --hard <previous-commit-hash>

# Reinstall dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput
```

#### Step 5: Restart Services (5 minutes)

```bash
sudo systemctl start gunicorn
sudo systemctl start celery
sudo systemctl status gunicorn
sudo systemctl status celery
```

#### Step 6: Verify System Stable (5 minutes)

```bash
# Test application
curl -I http://localhost:8000/

# Check logs
tail -f logs/django.log

# Test critical workflows
# - Login
# - View payroll list
# - Basic operations
```

#### Step 7: Exit Maintenance Mode (2 minutes)

```bash
python manage.py maintenance_mode off
```

#### Step 8: Document Incident (After rollback)

```markdown
# Rollback Incident Report

**Date:** YYYY-MM-DD HH:MM
**Reason:** [Why rollback was necessary]
**Impact:** [What was affected]
**Root Cause:** [What caused the issue]
**Resolution:** [How it was fixed]
**Prevention:** [How to prevent in future]
```

## Migration Scripts

### No Data Migration Needed

Since we're in a development environment with no production data, no data migration is required.

```python
# hr/management/commands/migrate_to_gateways.py
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Migrate existing data to use gateway structure'
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(
                '✅ No data migration needed (development environment)'
            )
        )
        self.stdout.write(
            'All new payrolls will automatically use gateway services.'
        )
```

## Environment-Specific Notes

### Development Environment

- No maintenance mode needed
- Can deploy anytime
- Rollback is easy
- No user impact

### Staging Environment

- Test deployment process
- Verify migrations work
- Test rollback procedure
- Gather performance metrics

### Production Environment

- **NOT APPLICABLE** - We're in development
- When moving to production:
  - Schedule deployment window
  - Notify all users
  - Have full team available
  - Monitor closely for 24 hours

## Success Criteria

### Technical Success

- ✅ All tests passing (85/85)
- ✅ No errors in logs
- ✅ Performance acceptable (< 1s per operation)
- ✅ Audit trail complete
- ✅ Idempotency working

### Business Success

- ✅ Payroll processing works
- ✅ Journal entries created correctly
- ✅ Reports accurate
- ✅ Users can perform their tasks
- ✅ No data loss or corruption

### Team Success

- ✅ Team trained on new system
- ✅ Documentation helpful
- ✅ Support requests minimal
- ✅ Confidence in new system

## Post-Deployment Tasks

### Week 1

- [ ] Monitor error logs daily
- [ ] Gather user feedback
- [ ] Address any issues quickly
- [ ] Update documentation if needed
- [ ] Conduct team retrospective

### Week 2-4

- [ ] Monitor performance trends
- [ ] Optimize slow queries
- [ ] Refine documentation
- [ ] Plan next improvements
- [ ] Celebrate success! 🎉

## Support Contacts

### Technical Issues

- **Backend Developer:** [Name/Email]
- **DevOps:** [Name/Email]
- **Database Admin:** [Name/Email]

### Business Issues

- **HR Manager:** [Name/Email]
- **Finance Manager:** [Name/Email]
- **System Admin:** [Name/Email]

## Appendix

### Useful Commands

```bash
# Check Django version
python manage.py --version

# Check installed packages
pip list

# Check database migrations
python manage.py showmigrations

# Check for missing migrations
python manage.py makemigrations --dry-run

# Run specific test
pytest hr/tests/test_services.py::TestPayrollGateway -v

# Check code quality
flake8 hr/
black hr/ --check
isort hr/ --check-only

# Generate coverage report
pytest --cov=hr --cov-report=html
# Open htmlcov/index.html
```

### Log Locations

```bash
# Application logs
/var/log/django/django.log
/var/log/django/application.log

# Web server logs
/var/log/nginx/access.log
/var/log/nginx/error.log

# Database logs
/var/log/mysql/error.log
/var/log/postgresql/postgresql.log

# System logs
/var/log/syslog
journalctl -u gunicorn
journalctl -u celery
```

## Changelog

### Version 1.0 (February 19, 2026)

- Initial deployment guide
- Development environment focus
- Complete rollback procedures
- Comprehensive checklists
