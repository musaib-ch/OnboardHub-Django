<<<<<<< HEAD
﻿# OnboardHub — Django

OnboardHub is a Django-based employee onboarding portal focused on configurable, workflow-driven onboarding, content, training, and offer management.

This repository contains a rebuilt and consolidated Django implementation used for development and internal deployment.

## Highlights

- Django 5.x, Python 3.11+; server-rendered pages with targeted JSON/AJAX endpoints for UI interactivity
- Multi-tenant-ready design, configurable onboarding stages and templates, content and learning modules
- Offer management (templates, email templates, WYSIWYG scaffolding, tokens, approvals) implemented in `core/models_offers.py`
- Admin UI for content, templates, training, analytics and CSV exports

## Quick start (development - Windows PowerShell)

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies and prepare the DB:

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo    # optional: creates sample tenant, users, demo data
python manage.py runserver
```

3. Open the site in your browser:

http://127.0.0.1:8000

## Recommended developer flow

- Use a feature branch per task (e.g. `feature/offers-wysiwyg`) and open PRs against `main`/`master`.
- Run targeted tests when changing core logic:

```powershell
python manage.py test core.tests.OfferTests
```

- Use a separate Postgres database for production; update `DATABASES` in settings or use environment variables.

## Offer management (where to look)

- Data models and business logic: `core/models_offers.py`
- API endpoints and admin wiring: `core/views/offer_api_views.py`, `core/views/public_offer_views.py`, `core/views/admin_views.py`
- Admin templates (editor scaffolding): `templates/admin/offer_templates.html`, `templates/admin/offer_email_templates.html`

If you need a high-fidelity export (PDF/DOCX) or e-signature provider integration, see the project plan notes in `C:/Users/H&M/.copilot/session-state/.../plan.md` (session-only — not checked into the repo).

## Excluding local and large artifacts

This repository prefers to keep the Git history focused on source and essential configuration. A `.gitignore` update has been appended to reduce accidental commits of local/session artifacts and bulk documentation files.

If you previously pushed many documentation `.md` files and want them removed from the remote, run these commands locally (they will remove them from the repo history going forward but will not delete local files):

```powershell
# remove tracked markdown files (keep README.md)
git rm --cached "*.md"
git add README.md
git commit -m "chore: stop tracking bulk markdown files (kept README)"
git push
```

Be careful: `git rm --cached "*.md"` will untrack all markdown files that are currently tracked. Run `git status` first to review which files will be affected.

## Security & production notes

- Keep `.env` and secrets out of source control (already in `.gitignore`).
- Sanitize any HTML entered into templates (the app uses server-side bleach sanitization for template content).
- Token-based public endpoints (offer accept/reject) are intentionally CSRF-exempt — audit logging and rate-limiting are in place but consider additional production hardening.

## Contributing

Create issues describing the feature or bug, then open a branch and a PR. Maintainers will review and merge following the project guidelines.

## License

Specify your project license here (e.g. MIT) or update the LICENSE file as needed.

---

(README generated/updated by project assistant.)
=======
# OnboardHub

Enterprise HR onboarding portal built with Django 5. Supports multi-stage employee onboarding, offer management, document signing, medical clearance, assessments, and live sessions.

## Quick Start

### 1. Environment setup

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
```

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

### 2. Install & run

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py init_stages      # Seed default stage definitions
python manage.py createsuperuser
python manage.py collectstatic --no-input
python manage.py runserver        # dev
# OR
waitress-serve --port=8000 onboardhub.wsgi:application  # production
```

### 3. Seed demo data (optional)

```bash
python manage.py seed_demo
```

## Production Deployment (Cloudflare Tunnel)

See `.env.example` for all required variables. Key checklist:

- `APP_ENV=production`
- `SECRET_KEY` — long random string, never committed
- `ALLOWED_HOSTS` — your public domain
- `CSRF_TRUSTED_ORIGINS` — `https://your-domain.com`
- SMTP settings configured via Admin → Email Settings
- Run `python manage.py collectstatic` after any code update

## Architecture

```
onboardhub/          Django project settings, urls, wsgi/asgi
core/
  models.py          All ORM models (User, Form, Content, etc.)
  models_offers.py   Offer / e-signature models
  views/             Feature-split view modules
  services/          Business logic (email, notifications, analytics…)
  templates/         Jinja-compatible Django templates
static/              Project-level static assets
templates/           HTML templates
```

## Security

- All secrets via environment variables — no hardcoded credentials
- CSRF protection on all state-changing views
- Session idle timeout (configurable via `SESSION_TIMEOUT_MINUTES`)
- Role-based access: `super_admin`, `admin`, `hrbp`, `manager`, `employee`
- File upload validation (type + size) on all upload endpoints
- HTML sanitization on public form submissions (bleach)
- Open redirect protection on all `next` URL parameters

## Background Tasks (optional)

```bash
# Start Redis first, then:
celery -A onboardhub worker -l info
celery -A onboardhub beat -l info   # scheduled reminders
```
>>>>>>> origin/main
