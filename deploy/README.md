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
