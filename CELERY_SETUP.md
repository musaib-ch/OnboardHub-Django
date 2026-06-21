# Celery Setup for OnboardHub

## Overview

OnboardHub uses Celery with Redis to handle background tasks like sending scheduled reminders. The reminder system is configured to dispatch pending reminders every hour automatically.

## Prerequisites

### For Development

1. **Redis** — required as the message broker and result backend
   - Install: `redis-server` (Windows: use WSL or Docker)
   - Or use Docker: `docker run -p 6379:6379 redis`

2. **Python packages** (already in requirements.txt)
   ```
   celery==5.3.4
   redis==5.0.1
   ```

## Running Locally

### Option 1: Redis in Docker (Recommended for Windows)

```bash
docker run -d -p 6379:6379 redis:latest
```

### Option 2: Manual Redis

```bash
# macOS
brew install redis
redis-server

# Ubuntu/Debian
sudo apt-get install redis-server
redis-server

# Windows (WSL)
wsl redis-server
```

## Running the Celery Worker

Open a **new terminal** and start the Celery worker:

```bash
cd C:\Users\H&M\Desktop\OnboardHub-Django
celery -A onboardhub worker -l info
```

Output should look like:
```
 -------------- celery@HOSTNAME v5.3.4 (emerald-rush)
--- ***** -----
-- ******* ----
- *** --- * ---
- ** ---------- [config]
- ** ----------
- ** ----------
[Tasks]
  . core.tasks.send_pending_reminders

[2026-06-18 09:30:00,000: INFO/MainProcess] celery@HOSTNAME ready.
```

## Running Celery Beat (Scheduler)

In a **separate terminal**, start the Celery beat scheduler:

```bash
celery -A onboardhub beat -l info
```

Output should show:
```
celery beat v5.3.4 (emerald-rush) is starting.
... 
Scheduler: Sending due tasks every 1 second.
```

Celery beat will automatically dispatch `send_pending_reminders` **every hour at :00** (e.g., 9:00, 10:00, 11:00).

## Configuration

### Broker & Backend (Redis)

Set via environment variables or in `onboardhub/settings.py`:

```python
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
```

### Changing the Reminder Schedule

Edit `onboardhub/celery.py`:

```python
app.conf.beat_schedule = {
    'send-pending-reminders': {
        'task': 'core.tasks.send_pending_reminders',
        'schedule': crontab(minute=0),  # Every hour (change as needed)
    },
}
```

Common schedules:
- `crontab(minute=0)` — Every hour
- `crontab(minute=0, hour=9)` — Daily at 9 AM
- `crontab(minute='*/15')` — Every 15 minutes

## Testing Celery Locally

### Send a test task directly:

```bash
python
>>> from core.tasks import send_pending_reminders
>>> result = send_pending_reminders.delay()
>>> result.get()  # Wait for result
```

### Check Redis connection:

```bash
redis-cli
> PING
PONG
```

### View Celery logs:

Worker logs show task execution:
```
[2026-06-18 09:30:00,123: INFO/PoolWorker-1] Task core.tasks.send_pending_reminders[abc123] sent 3 reminders
```

## Production Deployment

For production (e.g., on Cloudflare Tunnel):

1. **Start Redis** (managed service recommended: AWS ElastiCache, Heroku Redis, etc.)

2. **Set environment variables:**
   ```
   CELERY_BROKER_URL=redis://your-redis-host:6379/0
   CELERY_RESULT_BACKEND=redis://your-redis-host:6379/0
   ```

3. **Run worker in background** (using supervisor, systemd, or Docker):
   ```bash
   celery -A onboardhub worker -l info --concurrency=4
   ```

4. **Run beat scheduler** (single instance):
   ```bash
   celery -A onboardhub beat -l info
   ```

## Monitoring

### Using Flower (optional web UI):

```bash
pip install flower
celery -A onboardhub events -c flower.Flower
```

Then visit http://localhost:5555

### Manual checks:

```bash
# Show active tasks
celery -A onboardhub inspect active

# Show registered tasks
celery -A onboardhub inspect registered
```

## Troubleshooting

**Connection refused?**
- Ensure Redis is running: `redis-cli PING` should return `PONG`

**Task not executing?**
- Check worker is running: look for `[Tasks]` output with `send_pending_reminders`
- Check beat is running: should show `Scheduler: Sending due tasks`
- Verify time: Celery uses UTC; ensure server time is correct

**Reminders not sending?**
- Check email configuration in `onboardhub/settings.py`
- Verify employee has an email address
- Check `Reminder` table status column in admin

## Summary

```bash
# Terminal 1: Redis (if not using Docker/managed service)
redis-server

# Terminal 2: Django dev server
python manage.py runserver

# Terminal 3: Celery worker
celery -A onboardhub worker -l info

# Terminal 4: Celery beat scheduler
celery -A onboardhub beat -l info
```

Reminders will now auto-dispatch every hour!
