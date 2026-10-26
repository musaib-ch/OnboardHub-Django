"""
<<<<<<< HEAD
Django settings for onboardhub project (OnboardHub — Django rebuild).
=======
Django settings for OnboardHub — production-ready configuration.
All secrets/environment values are read from environment variables.
>>>>>>> origin/main
"""

import os
from pathlib import Path
<<<<<<< HEAD

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-1rz@my@8nxw!9u9sk%&r%2%$6p*s7gxg)6py)cdp#fhiqb43cb",
)
=======
from django.contrib.messages import constants as messages  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Core ─────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Generate one with: python -c \"from django.core.management.utils import get_random_secret_key as g; print(g())\""
    )
>>>>>>> origin/main

DEBUG = os.environ.get("APP_ENV", "development") != "production"


def _csv_env(name, default=""):
    """Read a comma-separated env var into a clean list."""
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


<<<<<<< HEAD
# In dev, accept any host. In production, set ALLOWED_HOSTS to your Cloudflare
# hostname(s), e.g. ALLOWED_HOSTS="onboard.example.com".
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS") or (["*"] if DEBUG else [])

# Django >= 4 requires the HTTPS origin(s) here for POST/CSRF to work behind a
# proxy. Cloudflare Tunnel terminates TLS, so list your public https origin,
# e.g. CSRF_TRUSTED_ORIGINS="https://onboard.example.com".
CSRF_TRUSTED_ORIGINS = _csv_env("CSRF_TRUSTED_ORIGINS")

=======
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS") or (["*"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = _csv_env("CSRF_TRUSTED_ORIGINS")

# ── Apps ──────────────────────────────────────────────────────────────────────
>>>>>>> origin/main
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

<<<<<<< HEAD
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serve static files directly from the WSGI app (no separate web server
    # needed behind the Cloudflare tunnel).
=======
# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
>>>>>>> origin/main
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.LastActivityMiddleware",
]

ROOT_URLCONF = "onboardhub.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "onboardhub.wsgi.application"

<<<<<<< HEAD
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

=======
# ── Database ─────────────────────────────────────────────────────────────────
if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME"),
            "USER": os.environ.get("DB_USER"),
            "PASSWORD": os.environ.get("DB_PASSWORD"),
            "HOST": os.environ.get("DB_HOST"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ── Auth ─────────────────────────────────────────────────────────────────────
>>>>>>> origin/main
AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = ["core.auth_backends.EmailBackend"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "index"
LOGOUT_REDIRECT_URL = "login"

<<<<<<< HEAD
# Map Django message tags to Bootstrap alert classes (matches Flask flash categories).
from django.contrib.messages import constants as messages  # noqa: E402

=======
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Messages ──────────────────────────────────────────────────────────────────
>>>>>>> origin/main
MESSAGE_TAGS = {
    messages.DEBUG: "secondary",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

<<<<<<< HEAD
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
]

=======
# ── Internationalisation ──────────────────────────────────────────────────────
>>>>>>> origin/main
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("APP_TIMEZONE", "Asia/Karachi")
USE_I18N = True
USE_TZ = True

<<<<<<< HEAD
=======
# ── Static & Media ────────────────────────────────────────────────────────────
>>>>>>> origin/main
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

<<<<<<< HEAD
# Compressed + hashed static files served by WhiteNoise.
=======
>>>>>>> origin/main
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

<<<<<<< HEAD
# Idle session timeout (minutes) — mirrors Flask SESSION_TIMEOUT_MINUTES.
# Send email in a background thread so requests don't block on SMTP.
# Set to False (e.g. in tests) to send synchronously.
EMAIL_ASYNC = os.environ.get("EMAIL_ASYNC", "true").lower() == "true"

SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# ── Reverse-proxy / HTTPS (Cloudflare Tunnel) ────────────────────────────────
# Cloudflare terminates TLS and forwards plain HTTP to the local app, setting
# X-Forwarded-Proto. Trust it so Django knows the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    # Only mark cookies secure in production; lets local HTTP dev still work.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS — opt in via env once you're confident the domain is HTTPS-only.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
    SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)

# ── Celery Configuration (background tasks, scheduled reminders) ──────────────
=======
# ── Session / Email ───────────────────────────────────────────────────────────
# SMTP is intentionally database-driven. The admin SMTP Settings page is the
# single source of truth, and this backend makes django.core.mail.send_mail()
# use the same saved host/port/user/password/TLS settings.
EMAIL_BACKEND = "core.db_email_backend.AppSettingEmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@onboardhub.local")
EMAIL_ASYNC = os.environ.get("EMAIL_ASYNC", "true").lower() == "true"
SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True  # Prevent JS access to session cookie
SESSION_COOKIE_SAMESITE = "Lax"  # CSRF protection

# ── HTTPS / Proxy ──────────────────────────────────────────────────────────────
# Cloudflare Tunnel terminates TLS; trust the forwarded proto header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
    SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)
    # Prevent browsers from detecting MIME types (clickjacking)
    X_FRAME_OPTIONS = "DENY"

# ── Celery ─────────────────────────────────────────────────────────────────────
>>>>>>> origin/main
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
<<<<<<< HEAD
=======

# ── File upload limits ─────────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB form data
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB file uploads
>>>>>>> origin/main
