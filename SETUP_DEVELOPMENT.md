# OnboardHub Development Setup Guide (SQLite)

## Prerequisites
- Python 3.11+
- Git
- Redis (for Celery - optional for dev)

## Step 1: Clone Repository
```bash
git clone https://github.com/your-org/onboardhub.git
cd OnboardHub-Django
```

## Step 2: Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

## Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

## Step 4: Environment Configuration
Create `.env` file in project root:

```
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
CELERY_BROKER_URL=redis://localhost:6379/0
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id
```

## Step 5: Database Setup
```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
# Email: admin@test.com
# Password: admin123
```

## Step 6: Load Sample Data
```bash
python manage.py loaddata fixtures/sample_data.json
```

## Step 7: Run Development Server
```bash
python manage.py runserver
```

Visit: http://localhost:8000

## Step 8 (Optional): Run Celery
```bash
# Terminal 1: Celery Worker
celery -A onboardhub worker -l info

# Terminal 2: Celery Beat (scheduler)
celery -A onboardhub beat -l info
```

## Database (SQLite)
- File: `db.sqlite3` (auto-created)
- Good for: Development, testing, small deployments
- Limitation: Not suitable for concurrent users in production

## Testing
```bash
# Run all tests
python manage.py test

# Run specific test
python manage.py test core.tests.test_models

# With coverage
coverage run --source='.' manage.py test
coverage report
```

## Common Issues

### Issue: "No module named 'onboardhub'"
Solution: Make sure you're in the project directory and venv is activated

### Issue: "Permission denied" on migrations
Solution: Delete db.sqlite3 and re-run migrations

### Issue: Celery not working
Solution: Install Redis and update CELERY_BROKER_URL

## Useful Commands
```bash
# Create migrations for changes
python manage.py makemigrations

# Check for issues
python manage.py check

# Create test data
python manage.py shell
>>> from core.models import User
>>> User.objects.create_user(email='test@test.com', password='test123')

# Access admin panel
# Go to http://localhost:8000/admin
```

## File Structure
```
OnboardHub-Django/
├── onboardhub/              # Main project
│   ├── settings.py          # Django configuration
│   ├── urls.py              # URL routing
│   ├── wsgi.py              # WSGI config
│   └── celery.py            # Celery config
├── core/                    # Core app
│   ├── models.py            # Database models
│   ├── views/               # View files
│   ├── services/            # Business logic
│   └── migrations/          # Database migrations
├── templates/               # HTML templates
├── static/                  # CSS, JS, images
├── requirements.txt         # Python dependencies
├── manage.py                # Django management
└── db.sqlite3               # SQLite database (auto-created)
```

## Next Steps
1. Create admin user in superuser creation step
2. Login to admin at http://localhost:8000/admin
3. Add sample employees
4. Configure settings (Portal URL, Email, Zoom)
5. Start development!
