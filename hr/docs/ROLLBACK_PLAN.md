# HR Module - Rollback Plan

**Version:** 1.0  
**Date:** February 19, 2026  
**Estimated Rollback Time:** 30 minutes  
**Risk Level:** LOW

## Overview

This document provides a comprehensive rollback plan in case the HR governance integration deployment encounters critical issues. The plan is designed to restore the system to a stable state quickly and safely.

## When to Rollback

### Immediate Rollback Required

Rollback **immediately** if any of these conditions occur:

- ❌ **Critical functionality broken**
  - Payroll creation completely fails
  - Users cannot access HR module
  - System crashes or becomes unresponsive

- ❌ **Data integrity issues**
  - Incorrect salary calculations
  - Missing or corrupted payroll records
  - Journal entries not balanced
  - Data loss detected

- ❌ **Performance degradation > 50%**
  - Payroll creation takes > 5 seconds (was ~1s)
  - Page load times > 10 seconds (was ~2s)
  - Database queries timeout
  - System becomes unusable

- ❌ **Multiple user complaints**
  - 3+ users report same critical issue
  - Widespread inability to perform tasks
  - Business operations blocked

- ❌ **Security vulnerability discovered**
  - Unauthorized access possible
  - Data exposure risk
  - Critical security flaw

- ❌ **Database corruption detected**
  - Foreign key violations
  - Orphaned records
  - Inconsistent data state

### Consider Rollback

Consider rollback if:

- ⚠️ **Minor functionality issues** affecting < 10% of users
- ⚠️ **Performance degradation 20-50%** but system still usable
- ⚠️ **Non-critical bugs** that can be fixed quickly
- ⚠️ **User confusion** about new interface (training issue)

**Note:** For "Consider Rollback" scenarios, evaluate if a hotfix is faster than rollback.

## Pre-Rollback Checklist

Before initiating rollback:

- [ ] **Confirm the issue is critical** (use criteria above)
- [ ] **Document the problem**
  - What is broken?
  - How many users affected?
  - Error messages/logs
  - Steps to reproduce
- [ ] **Notify stakeholders**
  - HR Manager
  - Finance Manager
  - Development team
  - System users
- [ ] **Verify backup availability**
  - Database backup exists
  - Backup is recent (< 24 hours)
  - Backup is accessible
- [ ] **Get approval** (if time permits)
  - Manager approval
  - Technical lead approval

## Rollback Procedure

### Step 1: Enable Maintenance Mode (2 minutes)

**Purpose:** Prevent users from making changes during rollback

```bash
# Option 1: Django maintenance mode
python manage.py maintenance_mode on

# Option 2: Nginx maintenance page
sudo ln -s /etc/nginx/sites-available/maintenance /etc/nginx/sites-enabled/
sudo systemctl reload nginx

# Option 3: Environment variable
export MAINTENANCE_MODE=true

# Verify maintenance mode active
curl -I http://localhost:8000/
# Should return 503 Service Unavailable
```

**Verification:**
- [ ] Maintenance page displays
- [ ] Users cannot access application
- [ ] No new requests being processed

---

### Step 2: Stop Application Services (3 minutes)

**Purpose:** Ensure no processes are writing to database

```bash
# Stop application server
sudo systemctl stop gunicorn
# Or for uWSGI:
sudo systemctl stop uwsgi

# Stop background workers (if any)
sudo systemctl stop celery
sudo systemctl stop celery-beat

# Verify services stopped
sudo systemctl status gunicorn
sudo systemctl status celery
# Should show "inactive (dead)"
```

**Verification:**
- [ ] Gunicorn/uWSGI stopped
- [ ] Celery workers stopped
- [ ] No Python processes running
- [ ] No database connections from app

---

### Step 3: Backup Current State (5 minutes)

**Purpose:** Preserve current state for post-mortem analysis

```bash
# Create rollback backup directory
mkdir -p /backups/rollback_$(date +%Y%m%d_%H%M%S)
cd /backups/rollback_$(date +%Y%m%d_%H%M%S)

# Backup current database
python manage.py dumpdata > current_state.json
# Or database-specific:
mysqldump -u user -p database > current_state.sql

# Backup current code
git log -1 > current_commit.txt
git diff > current_changes.diff

# Backup logs
cp /var/log/django/django.log django_log_backup.log
cp /var/log/nginx/error.log nginx_error_backup.log

# Verify backups created
ls -lh
```

**Verification:**
- [ ] Database backup created
- [ ] Code state documented
- [ ] Logs backed up
- [ ] All files readable

---

### Step 4: Restore Database (10 minutes)

**Purpose:** Restore database to pre-deployment state

```bash
# Locate pre-deployment backup
ls -lh /backups/backup_deployment_*.json
# Or:
ls -lh /backups/backup_*.sql

# Option 1: Django loaddata (if using JSON)
python manage.py flush --noinput
python manage.py loaddata /backups/backup_deployment_YYYYMMDD_HHMMSS.json

# Option 2: MySQL restore
mysql -u user -p database < /backups/backup_deployment_YYYYMMDD_HHMMSS.sql

# Option 3: PostgreSQL restore
psql -U user -d database < /backups/backup_deployment_YYYYMMDD_HHMMSS.sql

# Verify database restored
python manage.py shell
>>> from hr.models import Payroll
>>> Payroll.objects.count()
# Should match pre-deployment count
```

**Verification:**
- [ ] Database restore completed without errors
- [ ] Record counts match pre-deployment
- [ ] No foreign key violations
- [ ] Data integrity intact

---

### Step 5: Revert Code Changes (5 minutes)

**Purpose:** Restore code to pre-deployment version

```bash
# Get pre-deployment commit hash
cat /backups/pre_deployment_commit.txt
# Or check git log:
git log --oneline -10

# Option 1: Revert commit (safe, creates new commit)
git revert <deployment-commit-hash>

# Option 2: Hard reset (destructive, use with caution)
git reset --hard <pre-deployment-commit-hash>

# Verify correct version
git log -1
git status

# Reinstall dependencies (in case they changed)
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Verify code reverted
grep -r "HRPayrollGatewayService" hr/
# Should return ZERO results if fully reverted
```

**Verification:**
- [ ] Code reverted to previous version
- [ ] Dependencies installed
- [ ] Static files collected
- [ ] No uncommitted changes

---

### Step 6: Run Migrations (if needed) (3 minutes)

**Purpose:** Ensure database schema matches code

```bash
# Check migration status
python manage.py showmigrations hr

# If migrations need to be reversed:
python manage.py migrate hr <previous-migration-number>

# Verify migrations
python manage.py showmigrations hr
# All should be applied correctly
```

**Verification:**
- [ ] Migrations match code version
- [ ] No unapplied migrations
- [ ] No migration errors

---

### Step 7: Restart Services (5 minutes)

**Purpose:** Bring application back online

```bash
# Start application server
sudo systemctl start gunicorn
# Or:
sudo systemctl start uwsgi

# Start background workers
sudo systemctl start celery
sudo systemctl start celery-beat

# Verify services running
sudo systemctl status gunicorn
sudo systemctl status celery
# Should show "active (running)"

# Check for errors
journalctl -u gunicorn -n 50
journalctl -u celery -n 50
```

**Verification:**
- [ ] Gunicorn/uWSGI running
- [ ] Celery workers running
- [ ] No errors in service logs
- [ ] Application responding

---

### Step 8: Verify System Stable (5 minutes)

**Purpose:** Ensure system is working correctly

```bash
# Test application responds
curl -I http://localhost:8000/
# Should return 200 OK (or 503 if still in maintenance)

# Test database connection
python manage.py shell
>>> from django.db import connection
>>> connection.ensure_connection()
>>> # Should not raise error

# Test critical functionality
# - Login works
# - Can view payroll list
# - Can view employee list
# - No 500 errors

# Check error logs
tail -f /var/log/django/django.log
# Should show no errors
```

**Verification:**
- [ ] Application accessible
- [ ] Database connection working
- [ ] Critical pages load
- [ ] No errors in logs

---

### Step 9: Exit Maintenance Mode (2 minutes)

**Purpose:** Allow users back into system

```bash
# Option 1: Django maintenance mode
python manage.py maintenance_mode off

# Option 2: Nginx
sudo rm /etc/nginx/sites-enabled/maintenance
sudo systemctl reload nginx

# Option 3: Environment variable
unset MAINTENANCE_MODE

# Verify maintenance mode off
curl -I http://localhost:8000/
# Should return 200 OK
```

**Verification:**
- [ ] Maintenance mode disabled
- [ ] Users can access application
- [ ] Login works
- [ ] Basic functionality works

---

### Step 10: Monitor System (30 minutes)

**Purpose:** Ensure system remains stable

```bash
# Monitor error logs
tail -f /var/log/django/django.log

# Monitor application logs
tail -f /var/log/application.log

# Monitor web server logs
tail -f /var/log/nginx/error.log

# Monitor system resources
htop

# Check for user reports
# - No error complaints
# - Functionality working
# - Performance acceptable
```

**Verification:**
- [ ] No error spikes
- [ ] Performance normal
- [ ] Users can work normally
- [ ] No new issues reported

---

## Post-Rollback Tasks

### Immediate (Within 1 hour)

- [ ] **Notify stakeholders**
  - Rollback completed
  - System stable
  - Users can resume work

- [ ] **Document incident**
  - What went wrong
  - Why rollback was needed
  - What was done
  - Current system state

- [ ] **Preserve evidence**
  - Error logs
  - Database state
  - User reports
  - Screenshots

### Short-term (Within 24 hours)

- [ ] **Root cause analysis**
  - What caused the issue?
  - Why wasn't it caught in testing?
  - What can prevent it in future?

- [ ] **Create incident report**
  - Timeline of events
  - Impact assessment
  - Lessons learned
  - Action items

- [ ] **Plan fix**
  - How to fix the issue
  - Additional testing needed
  - Timeline for re-deployment

### Long-term (Within 1 week)

- [ ] **Implement fixes**
  - Fix root cause
  - Add tests to prevent regression
  - Update documentation

- [ ] **Improve process**
  - Better testing procedures
  - Better deployment process
  - Better rollback procedures

- [ ] **Plan re-deployment**
  - When to try again
  - Additional safeguards
  - Communication plan

## Rollback Incident Report Template

```markdown
# Rollback Incident Report

## Incident Details

**Date:** YYYY-MM-DD HH:MM  
**Duration:** X hours  
**Severity:** Critical/High/Medium  
**Affected Users:** X users / All users  

## What Happened

[Describe what went wrong]

## Why Rollback Was Necessary

[Explain why rollback was the best option]

## Rollback Timeline

- HH:MM - Issue detected
- HH:MM - Decision to rollback made
- HH:MM - Maintenance mode enabled
- HH:MM - Services stopped
- HH:MM - Database restored
- HH:MM - Code reverted
- HH:MM - Services restarted
- HH:MM - System verified stable
- HH:MM - Maintenance mode disabled
- HH:MM - Users notified

## Impact Assessment

**Business Impact:**
- Payroll processing delayed by X hours
- X users unable to work
- No data loss

**Technical Impact:**
- Database restored to previous state
- Code reverted to previous version
- X hours of work lost

**Financial Impact:**
- Estimated cost: $X
- Lost productivity: X hours

## Root Cause

[What caused the issue]

## Lessons Learned

**What Went Well:**
- Rollback completed quickly
- No data loss
- Good communication

**What Could Be Improved:**
- Better testing before deployment
- Earlier detection of issue
- Faster decision making

## Action Items

- [ ] Fix root cause issue
- [ ] Add regression tests
- [ ] Update deployment process
- [ ] Improve monitoring
- [ ] Schedule re-deployment

## Sign-off

**Prepared by:** [Name]  
**Reviewed by:** [Name]  
**Approved by:** [Name]  
**Date:** YYYY-MM-DD
```

## Emergency Contacts

### Technical Team

- **Backend Developer:** [Name] - [Phone] - [Email]
- **DevOps Engineer:** [Name] - [Phone] - [Email]
- **Database Admin:** [Name] - [Phone] - [Email]
- **System Admin:** [Name] - [Phone] - [Email]

### Business Team

- **HR Manager:** [Name] - [Phone] - [Email]
- **Finance Manager:** [Name] - [Phone] - [Email]
- **IT Manager:** [Name] - [Phone] - [Email]

### Escalation Path

1. **Level 1:** Backend Developer (immediate)
2. **Level 2:** Technical Lead (if issue persists > 15 min)
3. **Level 3:** IT Manager (if issue persists > 30 min)
4. **Level 4:** CTO (if critical business impact)

## Testing the Rollback Plan

### Quarterly Rollback Drill

Perform a rollback drill every quarter to ensure:

- [ ] Team knows the procedure
- [ ] Backups are working
- [ ] Rollback time is acceptable
- [ ] Documentation is up-to-date

### Drill Procedure

1. Schedule drill during low-usage time
2. Notify team (but not users)
3. Perform full rollback procedure
4. Time each step
5. Document any issues
6. Update plan as needed

## Appendix

### Useful Commands

```bash
# Check service status
sudo systemctl status gunicorn celery nginx

# View recent logs
journalctl -u gunicorn -n 100
journalctl -u celery -n 100

# Check database connections
sudo netstat -tulpn | grep :3306  # MySQL
sudo netstat -tulpn | grep :5432  # PostgreSQL

# Check disk space
df -h

# Check memory usage
free -h

# Check running processes
ps aux | grep python
ps aux | grep gunicorn
```

### Backup Locations

```bash
# Pre-deployment backups
/backups/backup_deployment_*.json
/backups/backup_deployment_*.sql

# Rollback backups
/backups/rollback_*/

# Automatic backups
/backups/daily/
/backups/weekly/
```

## Changelog

### Version 1.0 (February 19, 2026)

- Initial rollback plan
- Comprehensive step-by-step procedure
- Incident report template
- Emergency contacts
