# OnboardHub — Django Rebuild

A from-scratch Django rebuild of the OnboardHub employee onboarding portal,
consolidating the original Flask app's **52 tables into 14 domain tables**
while preserving the same UI/UX.

## Tech stack
- Python 3.11+, Django 5.0
- SQLite (dev) — swap `DATABASES` for PostgreSQL in production
- Bootstrap 5 + the original glass design system (CSS ported verbatim)

## Quick start (Windows PowerShell)

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # creates tenant, admin, employee, sample form
python manage.py runserver
```

Open http://127.0.0.1:8000

Seeded logins (from `seed_demo`):

| Role     | Email                       | Password       |
|----------|-----------------------------|----------------|
| Admin    | admin@onboardhub.local      | Admin@12345    |
| Employee | employee@onboardhub.local   | Employee@123   |

Create your own super admin instead with:
```powershell
python manage.py createsuperuser
```

## The 14-table consolidated schema (`core/models.py`)

| Table | Replaces (original Flask tables) |
|---|---|
| `Tenant` | tenant, tenant_feature, feature_module |
| `User` | user, role, user_permission (overrides now a JSON column) |
| `OrgUnit` | department, organization_unit, organization_option, hrbp_department |
| `AppSetting` | app_setting, integration_config, oracle_ebs_config |
| `Form` | form, form_template, form_section, form_field, quiz, survey, assessment (fields → JSON schema) |
| `FormResponse` | form_response, response, public_form_response, public_form_answer (answers → JSON) |
| `OnboardingDocument` | onboarding_document, onboarding_document_signature (signatures → JSON) |
| `MedicalRecord` | medical_requirement, medical_document, employee_medical_requirement |
| `Notification` | notification, notification_email_log, local_mailbox_message, management_message |
| `AuditLog` | audit_log, activity_log, sync_log |
| `Content` | knowledge, training, orientation, presentation, portal_slider/gallery/video/resource |
| `Enrollment` | program, enrollment, training progress, timeline |
| `Goal` | goals, goal plans, goal reviews |
| `Mentorship` | mentorship, mentor sessions |

Variable-shape data that used to live in satellite tables (form fields,
responses, signatures, feature flags, per-user permission overrides) is now
stored in JSON columns. This is the deliberate trade-off that hits the
"≤15 tables" target.

## What's implemented (Phase 1 — core)
- **Auth**: email login, logout, forgot/reset password, forced password change,
  profile, activation links — case-insensitive email backend, idle session timeout.
- **Multi-tenancy + theming**: `site_settings` context processor drives the
  branded glass UI exactly like the original.
- **Employee onboarding**: dashboard with progress, stage flow
  (pre-onboarding → onboarding → post-onboarding), dynamic form fill (save/draft),
  document signing, submit-for-review, medical view, set-joining-date, on-hold.
- **Admin console**: dashboard, employee list/detail, user CRUD (with temp
  passwords), JSON-schema **form builder**, onboarding documents, medical
  requirement catalog + review.
- **Public forms**: shareable anonymous form links + thank-you/closed pages.
- **Notifications** + **audit logging**.

## What's built beyond Phase 1
- **Content modules** (knowledge hub, training, orientation, presentations) —
  admin manage + employee browse/read/complete, driven by `Content` + `Engagement`
  (`core/views/content_views.py`).
- **Training & Learning Paths** (`core/views/training_views.py`) — admins build
  ordered learning paths from training modules, auto-assign by role/department/
  grade (rules in `AppSetting`) or manually; employees get a **My Learning**
  page with sequential unlock, progress tracking, and a completion certificate.
  Deadline nudges, manager escalation, and recurrence/recertification run via
  `python manage.py training_reminders` (cron / Task Scheduler). No new tables —
  learning paths are `Content(kind="learning_path")`, enrollments are
  `Engagement(kind="enrollment")`.

## What's stubbed for later phases (expansion)
The `Engagement` table also backs **goals** and **mentorship**, whose
views/templates are not yet built, along with surveys/quiz result UIs,
analytics, the automation/workflow builder, and Oracle EBS sync. The schema is
locked so adding them won't change the table count.

## Production deployment (Cloudflare Tunnel)
See [`deploy/README.md`](deploy/README.md). In short: set `APP_ENV=production`
and the host/CSRF env vars in `.env`, run `deploy/serve.ps1` (waitress +
WhiteNoise on `:8000`), then `cloudflared tunnel run` to expose it on HTTPS.

## Project layout
```
core/
  models.py            # 14 consolidated models
  permissions.py       # role permission matrix
  auth_backends.py     # case-insensitive email login
  middleware.py        # idle-session timeout + last_activity
  context_processors.py# site_settings (theming)
  services.py          # progress %, feature flags, logging, notify
  decorators.py        # login/role/permission guards
  views/               # auth, employee, admin, public, common
  templatetags/        # dict_get, humanize_status, ...
  management/commands/seed_demo.py
templates/             # base.html (ported CSS), all pages
onboardhub/settings.py
```
