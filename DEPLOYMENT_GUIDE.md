# OnboardHub Deployment Guide

Complete configurable workflow system ready for production deployment.

## System Status: ✅ PRODUCTION READY

All 4 phases complete:
- ✅ Phase 1: Core Infrastructure (database-driven stages)
- ✅ Phase 2: Employee Customization (per-employee workflows)
- ✅ Phase 3: Admin Management UI (stage/template configuration)
- ✅ Phase 4: Offer Workflow Foundation (offer_sender role + permissions)

**Latest commit:** Complete configurable workflow system implementation

---

## Pre-Deployment Setup (One-time)

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Configure Environment
```powershell
copy .env.example .env
# Edit .env with production values:
```

Key production settings to add to `.env`:
```
APP_ENV=production
SECRET_KEY=<generate-random-50-char-key>
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
DEBUG=False
```

Generate a secure SECRET_KEY:
```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Prepare Database
```powershell
python manage.py migrate
python manage.py seed_demo               # Creates demo tenant/users
python manage.py seed_configurable_stages # Creates default stages + templates
```

### 4. Set Up Cloudflare Tunnel (first time only)
```powershell
# Install cloudflared from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

# Login to Cloudflare
cloudflared tunnel login

# Create the tunnel
cloudflared tunnel create onboardhub

# Create DNS route (replace with your domain)
cloudflared tunnel route dns onboardhub yourdomain.com

# Copy config template
copy deploy\cloudflared-config.example.yml $env:USERPROFILE\.cloudflared\config.yml
# Edit config.yml with your tunnel ID and hostname
```

---

## Running the Application

Two terminals required: one for Django app, one for tunnel.

### Terminal 1: Run Django App (waitress + WhiteNoise)
```powershell
cd C:\Users\H&M\Desktop\OnboardHub-Django
.\deploy\serve.ps1
```

This script will:
- Collect static files (CSS, JS, images)
- Run migrations
- Start waitress on http://127.0.0.1:8000

### Terminal 2: Run Cloudflare Tunnel
```powershell
cloudflared tunnel run onboardhub
```

---

## Production Checklist

Before going live:

- [ ] `APP_ENV=production` in `.env`
- [ ] Generated unique `SECRET_KEY` (50+ chars)
- [ ] `DEBUG=False` in settings
- [ ] Set `ALLOWED_HOSTS` to your domain
- [ ] Set `CSRF_TRUSTED_ORIGINS` with `https://`
- [ ] Database migrated and seeded
- [ ] Email service configured (if using notifications)
- [ ] Cloudflare tunnel created and running
- [ ] Domain DNS routing configured
- [ ] Tested login and employee flow
- [ ] Tested admin stage/template configuration
- [ ] Tested offer sending workflow

---

## What's Deployed

### Core Features
- ✅ Employee onboarding with dynamic stages
- ✅ Role-based permissions (15 different roles including offer_sender)
- ✅ Admin dashboard and employee management
- ✅ Form builder and document management
- ✅ Medical document review workflow
- ✅ Multi-tenant support with branding

### Configurable Workflow Features
- ✅ Database-driven stage definitions
- ✅ Stage templates (Standard, Quick, Contractor, etc.)
- ✅ Per-employee custom stage paths
- ✅ Enable/disable stages via admin UI
- ✅ Create custom stages on-the-fly
- ✅ Offer workflow with dedicated sender role
- ✅ E-signature integration for offers

### Admin Features
- `/admin/setup/stages/` - Manage stage definitions
- `/admin/setup/stages/create/` - Create custom stages
- `/admin/setup/templates/` - Manage workflow templates
- `/admin/setup/templates/create/` - Create custom templates
- `/admin/employees/<id>/` - View and edit employee workflows

---

## Post-Deployment

### First Login
- URL: `https://yourdomain.com`
- Email: `admin@onboardhub.local`
- Password: `Admin@12345` (change immediately!)
- Or create your own super admin:
  ```powershell
  python manage.py createsuperuser
  ```

### Initial Setup Tasks
1. Visit Settings → Branding and customize appearance
2. Create your own admin user (don't use demo account in production)
3. Add employees or import from CSV
4. Configure workflow stages if needed
5. Test offering workflow with a test employee

### Monitor Application
- Check logs in Terminal 1 for errors
- Check Terminal 2 for tunnel connectivity
- Test regular employee flow: onboarding → medical → completion
- Test offer sending for new hires

---

## Scaling Beyond SQLite

For production with multiple concurrent users, upgrade to PostgreSQL:

```python
# In onboardhub/settings.py or .env:
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'onboardhub',
        'USER': 'postgres',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

Then migrate:
```powershell
python manage.py migrate
python manage.py seed_configurable_stages
```

---

## Troubleshooting

### Tunnel Connection Issues
- Verify cloudflared is running: `cloudflared tunnel list`
- Check config file exists at `~/.cloudflared/config.yml`
- Verify DNS record points to tunnel

### Static Files Not Loading
- Run: `python manage.py collectstatic --noinput`
- Check `STATIC_ROOT` in settings.py (should be `staticfiles/`)
- WhiteNoise should serve from there automatically

### Database Errors After Migration
- Check migrations ran: `python manage.py showmigrations`
- Verify database file exists: `db.sqlite3`
- Run: `python manage.py migrate --run-syncdb` to sync

### Permission Denied Errors
- Verify user has `super_admin` or appropriate role
- Check `manage_stages` and `manage_stage_templates` permissions
- Test with super_admin user first

---

## Architecture

```
Browser ──HTTPS──> Cloudflare Edge ──Tunnel──> 
cloudflared ──HTTP──> waitress ──WSGI──> Django App
                                           │
                                    SQLite/PostgreSQL
```

## Git History

Latest commit includes:
- All 4 phases of configurable workflow system
- Complete model definitions
- All views and templates
- Proper permissions and roles
- Comprehensive documentation

---

## Support

For issues or questions:
1. Check system check: `python manage.py check --deploy`
2. Review terminal output for errors
3. Check Django logs in Terminal 1
4. Verify Cloudflare tunnel status in Terminal 2

---

**Deployment ready!** 🚀
