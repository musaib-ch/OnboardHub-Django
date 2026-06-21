# OnboardHub Quick Reference & Commands

## Development Commands

```bash
# Virtual environment
python -m venv venv              # Create venv
source venv/bin/activate         # Activate (Mac/Linux)
venv\Scripts\activate            # Activate (Windows)
deactivate                       # Deactivate

# Dependencies
pip install -r requirements.txt  # Install all
pip freeze > requirements.txt    # Update list
pip install django celery redis  # Install specific

# Database
python manage.py migrate         # Run migrations
python manage.py makemigrations  # Create migration
python manage.py migrate --fake  # Skip migration
python manage.py sqlmigrate core 0001  # See SQL

# Server
python manage.py runserver               # Dev server
python manage.py runserver 0.0.0.0:8000  # Public IP
python manage.py check                   # Health check

# Admin
python manage.py createsuperuser  # Create admin
python manage.py changepassword    # Change password

# Testing
python manage.py test                    # Run all
python manage.py test core.tests         # Specific app
python manage.py test core.tests.test_models  # Specific test

# Shell
python manage.py shell            # Django shell
python manage.py dbshell          # Database shell

# Static files
python manage.py collectstatic    # Collect CSS/JS
python manage.py findstatic       # Find files

# Sample data
python manage.py loaddata sample_data  # Load fixtures
python manage.py dumpdata core > backup.json  # Export

# Celery
celery -A onboardhub worker -l info  # Worker
celery -A onboardhub beat -l info    # Beat scheduler
celery -A onboardhub inspect active  # Check tasks
celery -A onboardhub purge           # Clear queue
```

---

## Production Commands

```bash
# Nginx
sudo systemctl start nginx        # Start
sudo systemctl stop nginx         # Stop
sudo systemctl restart nginx      # Restart
sudo systemctl status nginx       # Status
sudo nginx -t                     # Test config

# Gunicorn
sudo systemctl start gunicorn     # Start
sudo systemctl restart gunicorn   # Restart
sudo systemctl status gunicorn    # Status
sudo journalctl -u gunicorn       # View logs

# Celery
sudo systemctl start celery-worker      # Start worker
sudo systemctl start celery-beat        # Start beat
sudo systemctl status celery-worker     # Status

# PostgreSQL
psql -h hostname -U user -d database        # Connect
\l                                          # List DBs
\d                                          # List tables
\q                                          # Quit

# Backups
pg_dump -h host -U user -d db > backup.sql  # Backup DB
psql -h host -U user -d db < backup.sql     # Restore

# SSH
ssh -i key.pem ubuntu@ip-address    # Connect
ssh-keygen -t rsa -N ""             # Generate key
```

---

## Environment Variables

```bash
# Core Django
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
DATABASE_URL=postgresql://user:pass@host:5432/onboardhub

# Cache & Tasks
CELERY_BROKER_URL=redis://localhost:6379/0
CACHE_URL=redis://localhost:6379/1

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# Zoom
ZOOM_CLIENT_ID=your_client_id
ZOOM_CLIENT_SECRET=your_client_secret
ZOOM_ACCOUNT_ID=your_account_id

# AWS S3 (optional)
USE_S3=True
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_STORAGE_BUCKET_NAME=your-bucket
```

---

## Django Admin URLs

```
/admin/                           # Admin home
/admin/auth/user/                 # Users
/admin/core/user/                 # Custom users
/admin/core/orgunit/              # Departments
/admin/core/form/                 # Forms
/admin/core/engagement/           # Engagements
/admin/core/appsetting/           # Settings
/admin/core/medicalrecord/        # Medical records
```

---

## Application URLs

```
Authentication:
/login/                           # Login
/logout/                          # Logout
/forgot-password/                 # Forgot password
/reset-password/<token>/          # Reset password
/change-password/                 # Change password
/profile/                         # User profile

Employee Paths:
/employee/home/                   # Employee dashboard
/employee/medical/                # Medical upload
/employee/pre-onboarding/         # Pre-onboarding forms
/employee/onboarding/             # Onboarding forms
/employee/post-onboarding/        # Post-onboarding
/employee/onboarding-plan/        # 30/60/90 plan

Admin Paths:
/admin/dashboard/                 # Admin dashboard
/admin/employees/                 # Employee list
/admin/employees/<id>/            # Employee detail
/admin/onboarding-plans/          # Plans list
/admin/analytics/                 # Analytics
/admin/settings/email/            # Email settings
/admin/settings/portal/           # Portal settings

Chat:
/messages/                        # Chat inbox
/messages/<user_id>/              # Chat with user

API:
/api/employees/                   # API: Employees
/api/onboarding-plans/            # API: Plans
/api/messages/                    # API: Chat
/api/analytics/                   # API: Analytics
```

---

## Database Models

```
User
├── Full Name
├── Email (unique)
├── Role (super_admin, admin, hrbp, manager, employee)
├── Status (pending, medical, pre_onboarding, onboarding, post_onboarding, completed)
├── Department
└── 40+ fields (position, phone, address, etc.)

Engagement (flexible container)
├── User
├── Kind (training, session, chat_dm, onboarding_plan)
├── Content (optional FK)
└── Data (JSON - flexible per kind)

Content
├── Title
├── Description
├── Kind (course, lesson, knowledge, presentation)
└── Data (JSON - course structure, lessons, quiz, etc.)

Form & FormResponse
├── Form: title, stage, fields
└── FormResponse: user, form, responses (JSON)

OrgUnit (departments, locations, divisions)
├── Name
├── Kind
├── Parent (optional)
└── Meta (JSON)

AppSetting
├── Key
└── Value (JSON)

MedicalRecord
├── User
├── File
├── Status (pending, approved, rejected)
└── Notes

OnboardingDocument
├── Title
├── Kind
├── Required
└── Meta (JSON)

ReviewMessage
├── Employee
├── Stage
├── Message
└── Timestamp
```

---

## API Response Format

```json
{
  "id": 1,
  "name": "John Doe",
  "email": "john@company.com",
  "status": "onboarding",
  "progress": 45,
  "stages": [
    {
      "name": "medical",
      "status": "completed",
      "progress": 100
    }
  ]
}
```

---

## Useful Curl Commands

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","password":"pass"}'

# Get employees
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/employees/

# Get analytics
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/analytics/summary/

# Export CSV
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/analytics/export/?format=csv > analytics.csv
```

---

## Email Template Variables

```
Core Variables:
{{employee_name}}        - John Doe
{{employee_email}}       - john@company.com
{{portal_link}}          - https://app.company.com
{{sender_name}}          - OnboardHub Team

Session Variables:
{{session_title}}        - Compliance Training
{{scheduled_date}}       - 2026-06-20
{{session_time}}         - 2:00 PM
{{zoom_join_url}}        - https://zoom.us/j/123456789

Training Variables:
{{course_title}}         - New Hire Onboarding
{{lesson_count}}         - 10
{{estimated_duration}}   - 20 hours
{{course_link}}          - https://app.com/courses/1

Plan Variables:
{{phase}}                - Day 30
{{manager_name}}         - Jane Smith
{{plan_link}}            - https://app.com/plans/1
{{milestone_title}}      - Complete orientation
```

---

## Troubleshooting Checklist

```
Page Issues:
[ ] Check browser console (F12) for JS errors
[ ] Check Django logs
[ ] Verify URL is correct
[ ] Clear browser cache
[ ] Test in incognito mode

Database Issues:
[ ] Check database connection string
[ ] Verify database is running
[ ] Check user has correct permissions
[ ] Run migrations
[ ] Check for locking tables

Email Issues:
[ ] Check SMTP config
[ ] Verify credentials
[ ] Check firewalls/security groups
[ ] Review email logs
[ ] Test with test email button

Performance Issues:
[ ] Check server CPU/memory
[ ] Review slow query log
[ ] Check Celery workers
[ ] Verify Redis connection
[ ] Monitor database connections

Zoom Integration:
[ ] Verify OAuth credentials
[ ] Click "Test Connection"
[ ] Check Zoom API status
[ ] Review integration logs
[ ] Check OAuth scopes
```

---

## Important Files

```
Configuration:
settings.py              - Django settings
urls.py                  - URL routing
requirements.txt         - Python dependencies
.env                     - Environment variables

Database:
models.py                - Data models
migrations/              - Schema changes
db.sqlite3               - Development database

Services:
services/email_service.py          - Email system
services/chat_service.py           - Chat system
services/onboarding_plan_service.py - 30/60/90 plans
services/unified_stages_service.py  - Unified stages

Views:
views/admin_views.py     - Admin interface
views/employee_views.py   - Employee interface
views/chat_views.py      - Chat system
views/analytics_views.py  - Analytics

Templates:
templates/base.html      - Base template
templates/admin/         - Admin templates
templates/employee/      - Employee templates
```

---

## Key Permissions

```
view_employees           - Can see employee list
manage_users            - Can create/edit users
manage_onboarding_plans - Can create 30/60/90 plans
manage_training         - Can manage training
approve_medical         - Can approve medical docs
bypass_stages           - Can complete on behalf
manage_forms            - Can create forms
export_data             - Can export to CSV
```

---

## Useful Links

- Admin: http://localhost:8000/admin/
- Employee: http://localhost:8000/employee/home/
- API: http://localhost:8000/api/
- Analytics: http://localhost:8000/admin/analytics/
- Email Settings: http://localhost:8000/admin/settings/email/
- Chat: http://localhost:8000/messages/

---

## Emergency Procedures

```bash
# Database locked
sudo lsof | grep db.sqlite3
kill -9 <pid>

# Clear cache
redis-cli FLUSHALL

# Restart all services
sudo systemctl restart gunicorn nginx celery-worker celery-beat

# Emergency maintenance mode
# Set DEBUG=True, add maintenance.html, redirect all traffic

# Database recovery
pg_dump -h host -U user db > backup.sql
DROP DATABASE db;
CREATE DATABASE db;
psql -h host -U user db < backup.sql

# Reset admin password
python manage.py changepassword admin

# Purge Celery queue
celery -A onboardhub purge

# Clear Django cache
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
```

---

## Performance Tips

- Use `select_related()` for FK queries
- Use `prefetch_related()` for M2M queries
- Index frequently searched fields
- Cache API responses
- Optimize database queries
- Use Redis for sessions
- Enable gzip compression
- Use CDN for static files
- Monitor slow queries
- Batch process large operations

---

**Last Updated**: 2026-06-20
**Version**: 1.0
