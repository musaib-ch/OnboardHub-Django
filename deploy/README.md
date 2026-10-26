<<<<<<< HEAD
# Deploying OnboardHub via Cloudflare Tunnel

Cloudflare Tunnel (`cloudflared`) exposes the locally-running Django app on a
public HTTPS hostname without opening any inbound ports — Cloudflare terminates
TLS and forwards plain HTTP to `127.0.0.1:8000`.

```
Browser ──HTTPS──> Cloudflare edge ──tunnel──> cloudflared ──HTTP──> waitress (Django :8000)
```

## One-time setup

1. **Install** the [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
   binary and a Python 3.11+ environment.

2. **Configure the app:**
   ```powershell
   pip install -r requirements.txt
   copy .env.example .env        # then edit .env
   ```
   In `.env` set `APP_ENV=production`, a fresh `SECRET_KEY`, your
   `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` (with `https://`).

3. **Create the tunnel + DNS route:**
   ```powershell
   cloudflared tunnel login
   cloudflared tunnel create onboardhub
   cloudflared tunnel route dns onboardhub onboard.example.com
   ```
   Then copy `deploy/cloudflared-config.example.yml` to
   `~/.cloudflared/config.yml` and fill in the tunnel ID + hostname.

## Running

Two processes — the app, then the tunnel:

```powershell
# Terminal 1 — the Django app (migrates, collects static, serves on :8000)
.\deploy\serve.ps1

# Terminal 2 — the Cloudflare tunnel
cloudflared tunnel run onboardhub
```

Visit `https://onboard.example.com`.

## Notes

- **Static files** are served by WhiteNoise from the WSGI app, so no separate
  web server (nginx) is needed. `serve.ps1` runs `collectstatic` for you.
- **Media uploads** (`media/`) are served by Django in DEBUG only. For
  production uploads behind the tunnel, front them with WhiteNoise/object
  storage or add an explicit media route — fine to defer for an internal tool.
- **Database** is SQLite by default. For multi-worker/production load, point
  `DATABASES` at PostgreSQL (see `onboardhub/settings.py`).
- **Quick demo** without a named tunnel/DNS:
  `cloudflared tunnel --url http://127.0.0.1:8000` gives a temporary
  `*.trycloudflare.com` URL — add it to `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`.
- The Linux equivalent of `serve.ps1` is the same commands with
  `gunicorn onboardhub.wsgi` instead of waitress.
=======
# Deployment

## Cloudflare Tunnel (recommended)

1. Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/
2. Copy `cloudflared-config.example.yml` → `~/.cloudflared/config.yml` and fill in your tunnel credentials.
3. Start the app with waitress, then cloudflared:

```bash
# Terminal 1 — app server
waitress-serve --host=127.0.0.1 --port=8000 onboardhub.wsgi:application

# Terminal 2 — tunnel
cloudflared tunnel run onboardhub
```

## Environment Variables

All required variables are documented in `.env.example` in the project root.

## Static Files

Run `python manage.py collectstatic --no-input` after every deployment.

## Database Migrations

Run `python manage.py migrate` after every deployment.
>>>>>>> origin/main
