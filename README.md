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
