# OnboardHub - Complete Platform Documentation

## Overview
OnboardHub is a comprehensive employee onboarding platform built with Django that streamlines the entire onboarding process from day one to day 90+ with integrated medical reviews, training assignments, real-time collaboration, and detailed analytics.

---

## 📚 Documentation Files

### For Getting Started
- **[SETUP_DEVELOPMENT.md](SETUP_DEVELOPMENT.md)** - Local development with SQLite
- **[SETUP_PRODUCTION.md](SETUP_PRODUCTION.md)** - Production deployment on AWS/GCP with PostgreSQL
- **[USER_TRAINING_GUIDE.md](USER_TRAINING_GUIDE.md)** - Training materials for all user roles
- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** - Complete API reference

### For Implementation
- **[INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md)** - Feature summary and architecture overview
- **[PROJECT-STATUS-2026-06.md](PROJECT-STATUS-2026-06.md)** - Detailed completion status

---

## 🚀 Quick Start

### Development (5 minutes)
```bash
# 1. Clone and setup
git clone <repo>
cd OnboardHub-Django
python -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser

# 4. Run
python manage.py runserver
# Visit http://localhost:8000
```

### Production (AWS)
See [SETUP_PRODUCTION.md](SETUP_PRODUCTION.md) for detailed AWS/GCP deployment

---

## 📋 System Features

### Core Onboarding Stages
1. **Medical** - Document upload & approval with medical review panel
2. **Pre-Onboarding** - Initial forms & requirements
3. **Orientation** - Sessions with Zoom integration
4. **Training & Learning** - Learning paths, courses, quizzes
5. **30/60/90 Plan** - Milestone tracking with feedback
6. **Onboarding** - Onboarding documents & forms
7. **Post-Onboarding** - Review & feedback completion

### Communication & Collaboration
- Real-time chat with @mentions
- Email notifications (10+ templates)
- Feedback threads on milestones
- Activity logs for all events

### Administration
- Employee management & analytics
- Medical document review & approval
- 30/60/90 plan creation & tracking
- Training & learning path assignment
- Email template customization
- Role-based access control
- Integration settings (Zoom, email, portal)

### Analytics & Reporting
- Employee completion rates by stage
- Medical approval rates
- Training completion statistics
- 30/60/90 plan progress
- Exportable to CSV
- Department breakdown

---

## 👥 User Roles & Permissions

| Role | Access | Can Do |
|------|--------|--------|
| **Super Admin** | Everything | All features, all settings, all employees |
| **Admin** | Global | Manage users, forms, documents, settings (except integrations) |
| **HRBP** | Department | Manage department employees, create plans, assign training |
| **Manager** | Team | View team, create plans, post feedback |
| **Medical Approver** | Medical only | Review and approve medical documents |
| **Employee** | Own profile | View own progress, complete forms, attend training |

---

## 🗄️ Database Schema

### 15 Tables (JSON Consolidation)
```
Core Tables:
- User (employees, staff, admins)
- OrgUnit (departments, locations, divisions)
- Form, FormResponse
- Content (courses, learning paths, knowledge items)
- Engagement (sessions, training, chat, 30/60/90)
- MedicalRecord, OnboardingDocument
- AppSetting (configuration, settings, templates)
- ReviewMessage (stage conversations)
```

All complex data (emails, templates, plans, chats) stored as JSON in existing tables.

---

## 🔌 Integrations

### Zoom
```
Zoom OAuth Setup (Admin > Settings > Integrations > Zoom):
- Client ID & Secret
- Account ID
- Test Connection
- Auto-creates meeting links for sessions
```

### Email
```
SMTP Configuration (Admin > Settings > Portal):
- Sender name & email address
- Portal URL (used in all emails)
- Custom footer
- 10+ email templates customizable
```

### External Services
- SendGrid / AWS SES for SMTP
- Redis for caching & Celery
- S3 for media (optional)

---

## 🔐 Security

- Role-based access control (RBAC)
- Permission matrix (21 permissions)
- SSL/TLS encryption in production
- Database encryption at rest
- CSRF protection
- XSS prevention
- SQL injection protection
- Secure password hashing (PBKDF2)
- Session security (secure cookies, HTTPS-only)

---

## 📊 API Endpoints

Base URL: `/api/`

### Main Endpoints
- `POST /auth/login/` - User login
- `GET /employees/` - List employees
- `GET /employees/{id}/` - Employee details
- `GET /onboarding-plans/` - 30/60/90 plans
- `GET /messages/` - Chat conversations
- `GET /analytics/summary/` - Analytics metrics
- `GET /analytics/export/?format=csv` - Export data
- `POST /settings/zoom/` - Zoom configuration
- `POST /settings/portal/` - Portal configuration

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for full reference.

---

## 📈 Metrics & Analytics

### Available Reports
- Employee onboarding progress by stage
- Completion rates (medical, training, documents)
- Time in each stage
- 30/60/90 plan completion
- Department completion breakdown
- Training completion rates
- Medical approval rates

### Export Formats
- CSV (all analytics)
- JSON (API responses)
- PDF (certificates, reports)

---

## 🛠️ Technology Stack

### Backend
- **Framework**: Django 5.0
- **Language**: Python 3.11+
- **Database**: PostgreSQL (production), SQLite (development)
- **Task Queue**: Celery with Redis
- **API**: Django REST Framework (planned)

### Frontend
- **Template**: Django Templates
- **CSS**: Bootstrap 5
- **JS**: Vanilla JS (no framework)
- **Icons**: Bootstrap Icons

### Infrastructure
- **Development**: SQLite, Django dev server
- **Production**: PostgreSQL, Gunicorn, Nginx
- **Deployment**: AWS EC2/RDS, Google App Engine/Cloud SQL, or self-hosted

---

## 📝 File Structure

```
OnboardHub-Django/
├── onboardhub/
│   ├── settings.py          # Django config
│   ├── urls.py              # URL routing
│   ├── wsgi.py              # WSGI app
│   └── celery.py            # Celery config
├── core/
│   ├── models.py            # 13 core models
│   ├── views/
│   │   ├── admin_views.py
│   │   ├── employee_views.py
│   │   ├── chat_views.py
│   │   └── ...
│   ├── services/
│   │   ├── email_service.py
│   │   ├── chat_service.py
│   │   ├── onboarding_plan_service.py
│   │   ├── unified_stages_service.py
│   │   └── ...
│   ├── migrations/          # Database migrations
│   ├── permissions.py       # Role permissions
│   ├── decorators.py        # Auth decorators
│   └── urls.py              # App URLs
├── templates/               # HTML templates
├── static/
│   ├── css/
│   ├── js/
│   └── images/
├── fixtures/                # Sample data
├── tests/                   # Test suite
├── manage.py                # Management script
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
└── README.md                # This file
```

---

## 🧪 Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test core

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html
```

---

## 📋 Deployment Checklist

### Pre-Deployment
- [ ] All tests passing
- [ ] No DEBUG mode in production
- [ ] Environment variables configured
- [ ] Database backups enabled
- [ ] SSL certificate ready
- [ ] SMTP credentials configured
- [ ] Zoom OAuth credentials ready
- [ ] Redis instance running
- [ ] S3 bucket created (if using S3)

### Deployment
- [ ] Database migrations run
- [ ] Static files collected
- [ ] Gunicorn service started
- [ ] Nginx configured
- [ ] SSL certificate installed
- [ ] Celery workers running
- [ ] Celery beat scheduler running
- [ ] Monitoring enabled
- [ ] Alerts configured

### Post-Deployment
- [ ] Test login & basic flows
- [ ] Verify email sending
- [ ] Test Zoom integration
- [ ] Check analytics dashboard
- [ ] Monitor error logs
- [ ] Performance check
- [ ] Security scan
- [ ] Backup verification

---

## 🐛 Troubleshooting

### Common Issues

**Issue**: Page not opening
- Solution: Check Django logs, verify URL routing, clear cache

**Issue**: Email not sending
- Solution: Check SMTP config, verify credentials, check email logs

**Issue**: Zoom integration failing
- Solution: Verify OAuth credentials, test connection button, check secrets

**Issue**: 30/60/90 plan not showing
- Solution: Ensure plan is created, check permissions, verify employee has active plan

**Issue**: Chat not loading
- Solution: Check Redis connection, verify user authentication, check database

**Issue**: Celery tasks not running
- Solution: Check Redis broker, verify celery worker status, check beat scheduler

---

## 📞 Support & Maintenance

### Regular Maintenance
- Daily: Monitor error logs
- Weekly: Review database size, test backups
- Monthly: Security updates, dependency updates
- Quarterly: Performance optimization, capacity planning

### Contacts
- **Technical Issues**: devops@company.com
- **Feature Requests**: product@company.com
- **Security Issues**: security@company.com

---

## 📄 License

Copyright 2026 - All Rights Reserved

---

## 🚀 What's Next?

After deployment:
1. Create admin user
2. Configure Zoom integration
3. Set up email sender details
4. Create departments/locations
5. Import/create employees
6. Set up forms and documents
7. Configure learning paths
8. Create 30/60/90 plan templates
9. Enable email notifications
10. Monitor analytics dashboard

---

## 📚 Additional Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [Bootstrap Documentation](https://getbootstrap.com/docs/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Gunicorn Documentation](https://gunicorn.org/)

---

## Version History

- **v1.0** (2026-06-20) - Initial release
  - Core onboarding stages
  - Medical review system
  - Training & learning paths
  - 30/60/90 day plans
  - Real-time chat
  - Email notifications
  - Analytics & reporting
  - Zoom integration
  - Role-based access control
