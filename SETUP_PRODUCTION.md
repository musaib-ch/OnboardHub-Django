# OnboardHub Production Setup Guide (PostgreSQL)

## Architecture
- **Database**: PostgreSQL (managed database)
- **App Server**: Gunicorn + Nginx
- **Cache**: Redis
- **Email**: SMTP (SendGrid / AWS SES / Custom)
- **Static Files**: WhiteNoise + CDN
- **Deployment**: Docker / Cloud Platform

## Prerequisites
- PostgreSQL 12+
- Redis 6+
- Python 3.11+
- Nginx 1.20+
- SSL Certificate (Let's Encrypt)

---

## Option 1: AWS Deployment

### Step 1: Create RDS PostgreSQL
```
1. Go to AWS RDS Console
2. Create Database
3. Engine: PostgreSQL 14
4. DB Instance: db.t3.micro (or larger)
5. Storage: 100GB, auto-scaling enabled
6. Multi-AZ: Yes (for production)
7. Backup retention: 30 days
8. Note: Endpoint, username, password
```

### Step 2: Create ElastiCache Redis
```
1. Go to AWS ElastiCache
2. Create Cluster
3. Engine: Redis 6.x
4. Node type: cache.t3.micro
5. Number of nodes: 1 (or 3+ for HA)
6. Note: Endpoint, port
```

### Step 3: Create EC2 Instance
```
1. Launch instance: Ubuntu 22.04 LTS
2. Instance type: t3.medium (or larger)
3. Storage: 50GB
4. Security Group: Allow 80, 443, 22
5. Key pair: Create & download
```

### Step 4: Connect to EC2
```bash
ssh -i your-key.pem ubuntu@your-instance-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3.11-venv python3-pip nginx \
  postgresql-client redis-tools git curl supervisor
```

### Step 5: Clone & Setup
```bash
cd /home/ubuntu
git clone https://github.com/your-org/onboardhub.git
cd OnboardHub-Django

# Create venv
python3.11 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install gunicorn psycopg2-binary
```

### Step 6: Environment Setup
```bash
# Create .env file
sudo nano /etc/onboardhub/.env
```

```
DEBUG=False
SECRET_KEY=generate-secure-key-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
DATABASE_URL=postgresql://user:password@rds-endpoint.amazonaws.com:5432/onboardhub

# Redis
CELERY_BROKER_URL=redis://redis-endpoint.amazonaws.com:6379/0
CACHE_URL=redis://redis-endpoint.amazonaws.com:6379/1

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True

# Zoom
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id

# AWS (if using S3 for media)
USE_S3=True
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1
```

### Step 7: Collect Static Files
```bash
# Set environment
export $(cat /etc/onboardhub/.env | xargs)

# Collect statics
python manage.py collectstatic --noinput --clear
```

### Step 8: Create Database
```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### Step 9: Gunicorn Configuration
```bash
# Create gunicorn config
sudo nano /etc/systemd/system/gunicorn.service
```

```
[Unit]
Description=Gunicorn application server
After=network.target

[Service]
Type=notify
User=ubuntu
WorkingDirectory=/home/ubuntu/OnboardHub-Django
Environment="PATH=/home/ubuntu/OnboardHub-Django/venv/bin"
EnvironmentFile=/etc/onboardhub/.env
ExecStart=/home/ubuntu/OnboardHub-Django/venv/bin/gunicorn \
  --workers 4 \
  --worker-class sync \
  --bind unix:/run/gunicorn.sock \
  --access-logfile - \
  --error-logfile - \
  onboardhub.wsgi:application

[Install]
WantedBy=multi-user.target
```

```bash
# Enable & start
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
```

### Step 10: Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/onboardhub
```

```nginx
upstream gunicorn {
    server unix:/run/gunicorn.sock;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # SSL config
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    client_max_body_size 10M;
    
    location /static/ {
        alias /home/ubuntu/OnboardHub-Django/staticfiles/;
        expires 30d;
    }
    
    location /media/ {
        alias /home/ubuntu/OnboardHub-Django/media/;
    }
    
    location / {
        proxy_pass http://gunicorn;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

```bash
# Enable & test
sudo ln -s /etc/nginx/sites-available/onboardhub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 11: SSL Certificate (Let's Encrypt)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot certonly --nginx -d yourdomain.com -d www.yourdomain.com
```

### Step 12: Celery Workers
```bash
# Create celery worker service
sudo nano /etc/systemd/system/celery-worker.service
```

```
[Unit]
Description=Celery Worker
After=network.target redis-server.service

[Service]
Type=forking
User=ubuntu
WorkingDirectory=/home/ubuntu/OnboardHub-Django
Environment="PATH=/home/ubuntu/OnboardHub-Django/venv/bin"
EnvironmentFile=/etc/onboardhub/.env
ExecStart=/home/ubuntu/OnboardHub-Django/venv/bin/celery -A onboardhub worker -l info --logfile=/var/log/celery/worker.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/log/celery
sudo chown ubuntu:ubuntu /var/log/celery
sudo systemctl enable celery-worker
sudo systemctl start celery-worker
```

### Step 13: Celery Beat (Scheduler)
```bash
# Create celery beat service
sudo nano /etc/systemd/system/celery-beat.service
```

```
[Unit]
Description=Celery Beat Scheduler
After=network.target redis-server.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OnboardHub-Django
Environment="PATH=/home/ubuntu/OnboardHub-Django/venv/bin"
EnvironmentFile=/etc/onboardhub/.env
ExecStart=/home/ubuntu/OnboardHub-Django/venv/bin/celery -A onboardhub beat -l info --logfile=/var/log/celery/beat.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable celery-beat
sudo systemctl start celery-beat
```

### Step 14: Backups
```bash
# Database backup script
sudo nano /usr/local/bin/backup-db.sh
```

```bash
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/onboardhub"
mkdir -p $BACKUP_DIR

# RDS backup (automated)
# Manual backup if needed:
# aws rds create-db-snapshot --db-instance-identifier onboardhub-prod \
#   --db-snapshot-identifier onboardhub-backup-$TIMESTAMP

echo "Backup completed: $TIMESTAMP"
```

```bash
sudo chmod +x /usr/local/bin/backup-db.sh
# Add to crontab: 0 2 * * * /usr/local/bin/backup-db.sh
```

---

## Option 2: Google Cloud Deployment

### Step 1: Create Cloud SQL (PostgreSQL)
```
1. Go to Cloud SQL
2. Create Instance > PostgreSQL 14
3. Instance ID: onboardhub-prod
4. Password: Generate strong password
5. Configuration: high availability
6. Storage: 100GB, auto-expand enabled
```

### Step 2: Create Cloud Memorystore (Redis)
```
1. Go to Memorystore
2. Create Redis Instance
3. Instance ID: onboardhub-redis
4. Tier: Standard
5. Size: 2GB
6. Region: Same as App Engine
```

### Step 3: Create App Engine
```bash
# Create app.yaml
cat > app.yaml << 'EOF'
runtime: python311
env: standard
entrypoint: gunicorn -b :$PORT onboardhub.wsgi:application

env_variables:
  DEBUG: "False"
  ENVIRONMENT: "production"

automatic_scaling:
  min_instances: 2
  max_instances: 10
  target_cpu_utilization: 0.65

handlers:
- url: /static
  static_dir: staticfiles/

- url: /.*
  script: auto
  secure: always
  redirect_http_response_code: 301

EOF

# Deploy
gcloud app deploy
```

### Step 4: Environment Variables (Cloud Build)
```bash
# Set secrets in Cloud Secret Manager
gcloud secrets create DATABASE_URL --data-file=-
gcloud secrets create SECRET_KEY --data-file=-
gcloud secrets create ZOOM_CLIENT_ID --data-file=-

# Grant App Engine access to secrets
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:PROJECT_ID@appspot.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

---

## Monitoring & Logging

### Application Logs
```bash
# AWS CloudWatch
# GCP Cloud Logging
# Datadog
# New Relic

# View logs:
# AWS: tail -f /var/log/gunicorn.log
# GCP: gcloud app logs read
```

### Database Monitoring
- **CloudWatch**: Monitor RDS/PostgreSQL metrics
- **Slow query logs**: Enable for optimization
- **Automated backups**: Retention policy 30 days

### Alerts
```
- High CPU usage (> 80%)
- Low disk space (< 10% free)
- Connection pool exhaustion
- Slow queries (> 1 second)
- Error rate (> 1%)
```

---

## Maintenance

### Regular Tasks
- **Daily**: Monitor error logs
- **Weekly**: Review database size, backup verification
- **Monthly**: Security updates, dependency updates
- **Quarterly**: Performance optimization, capacity planning

### Scaling
- **Database**: Increase storage/compute as needed (RDS/Cloud SQL handles auto)
- **App Servers**: Increase worker count or instance count
- **Cache**: Monitor Redis memory usage
- **Static Files**: Use CDN (CloudFront, Cloud CDN)

---

## Database Commands (Production)

```bash
# PostgreSQL admin
psql -h your-rds-endpoint.amazonaws.com -U postgres -d onboardhub

# Backup
pg_dump -h endpoint -U user -d onboardhub > backup.sql

# Restore
psql -h endpoint -U user -d onboardhub < backup.sql

# Check size
SELECT pg_size_pretty(pg_database_size('onboardhub'));

# Monitor connections
SELECT * FROM pg_stat_activity;
```

---

## Security Checklist

- [ ] Enable SSL/TLS (HTTPS)
- [ ] Set DEBUG=False
- [ ] Strong SECRET_KEY
- [ ] Database user with limited permissions
- [ ] Redis password/AUTH enabled
- [ ] Firewall rules restrict access
- [ ] WAF (Web Application Firewall) enabled
- [ ] Regular security updates
- [ ] Database encryption at rest & transit
- [ ] Backup encryption
- [ ] VPN/Private network for admin access
- [ ] 2FA for admin users
- [ ] Regular security audits
- [ ] GDPR/compliance data handling

---

## Troubleshooting

### 502 Bad Gateway
- Check gunicorn status: `sudo systemctl status gunicorn`
- Check gunicorn logs: `sudo journalctl -u gunicorn`
- Verify database connection

### Database Connection Issues
- Check PostgreSQL is running
- Verify credentials in .env
- Check security groups allow connection
- Test: `psql -h endpoint -U user -d onboardhub`

### Celery Tasks Not Running
- Check Redis connection: `redis-cli -h endpoint ping`
- Check celery worker status: `sudo systemctl status celery-worker`
- Check beat scheduler: `sudo systemctl status celery-beat`
- Test: `celery -A onboardhub inspect active`

---

## Support
For issues or questions, contact devops@company.com
