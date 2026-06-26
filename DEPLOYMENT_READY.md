# Deployment Checklist

## Pre-Deployment ✅

- [x] Python code syntax verified
- [x] All imports working correctly  
- [x] Database abstraction layer implemented (SQLite + Postgres)
- [x] Migration script created and tested
- [x] Tenant webhook system implemented
- [x] Security validations in place
  - [x] Webhook secret validation
  - [x] Chat ID validation
  - [x] API token validation
  - [x] Constant-time secret comparison
- [x] Environment variables documented
- [x] Error handling comprehensive
- [x] Logging enabled

## Heroku Setup

### Step 1: Create Heroku App

```powershell
heroku create your-app-name
# Or attach to existing app
heroku git:remote -a your-app-name
```

### Step 2: Create Neon Postgres Database

1. Visit [Neon Console](https://console.neon.tech)
2. Create new project
3. Copy **pooled connection string**

### Step 3: Configure Environment Variables

```powershell
# Critical - Postgres connection (use pooled connection string)
heroku config:set DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require"

# Telegram configuration
heroku config:set TELEGRAM_BOT_TOKEN="your-bot-token"
heroku config:set TELEGRAM_WEBHOOK_SECRET="random-secret-string"

# API security
heroku config:set X_ACCESS_TOKEN="random-api-token"

# Webhook configuration (for tenant webhook URLs)
heroku config:set APP_DOMAIN="https://your-app-name.herokuapp.com"

# Verify
heroku config
```

### Step 4: Deploy

```powershell
git add .
git commit -m "Deploy Postgres migration and tenant webhook system"
git push heroku main
```

### Step 5: Monitor Deployment

```powershell
# Watch logs during deployment
heroku logs -t

# Test health endpoint
Invoke-WebRequest https://your-app-name.herokuapp.com/health
# Should return: {"status":"ok"}
```

### Step 6: Verify Database Setup

```powershell
# Check that Postgres backend is being used
heroku run "python -c \"from telegram_bot.database import get_database_backend; print(f'Using: {type(get_database_backend()).__name__}')\""

# Should print: Using: PostgresBackend

# Check database tables created
heroku pg:psql
\dt
# Should show: tenants, tenant_telegram_config, sessions, orders, tenant_webhook_secrets
\q
```

## Migration (Optional - if migrating from SQLite)

If you have existing SQLite data:

```powershell
# Run migration to Postgres
$env:DATABASE_URL=$(heroku config:get DATABASE_URL)
python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db

# Or use Heroku one-off dyno
heroku run "python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db"
```

## Post-Deployment Testing

### 1. Health Check

```powershell
$url = "https://your-app-name.herokuapp.com/health"
Invoke-WebRequest $url
# Should return: {"status":"ok"}
```

### 2. Tenant Configuration

```powershell
$headers = @{
    "X-Access-Token" = (heroku config:get X_ACCESS_TOKEN)
    "Content-Type" = "application/json"
}

$body = @{
    enabled = $false
} | ConvertTo-Json

$url = "https://your-app-name.herokuapp.com/api/tenants/test-tenant/telegram/config"
Invoke-WebRequest -Uri $url -Method POST -Headers $headers -Body $body
# Should return: {"ok":true,"tenant_id":"test-tenant",...}
```

### 3. Order Ingestion

```powershell
$headers = @{
    "X-Access-Token" = (heroku config:get X_ACCESS_TOKEN)
    "Content-Type" = "application/json"
}

$body = @{
    session_id = "test-session"
    commenter = "Test User"
    comment = "Test order"
    comment_id = "test-123"
    collected_at = (Get-Date -AsUTC -Format 'o')
} | ConvertTo-Json

$url = "https://your-app-name.herokuapp.com/api/tenants/test-tenant/orders"
Invoke-WebRequest -Uri $url -Method POST -Headers $headers -Body $body
# Should return: {"ok":true,"tenant_id":"test-tenant",...}
```

### 4. Verify Database Persistence

```powershell
# Connect to Postgres
heroku pg:psql

# Check data was saved
SELECT COUNT(*) FROM tenants;
SELECT * FROM tenant_telegram_config WHERE tenant_id = 'test-tenant';
SELECT COUNT(*) FROM orders;

\q
```

## Monitoring

```powershell
# View real-time logs
heroku logs -t

# View errors only
heroku logs -t --source app | findstr "ERROR"

# Check dyno status
heroku ps

# Check database size and stats
heroku pg:info
```

## Rollback Plan (if needed)

```powershell
# See recent deployments
heroku releases

# Rollback to previous version
heroku rollback v<NUMBER>

# Or redeploy specific git commit
git push heroku <COMMIT>:main -f
```

## Post-Deployment

### Configure Tenant Webhooks

For each tenant with a Telegram bot:

1. Get webhook URL from tenant config response:
```powershell
# Already includes webhook_url and webhook_secret
$response = Invoke-WebRequest ... | ConvertFrom-Json
$webhook_url = $response.webhook_url
```

2. Register with Telegram:
```bash
curl -X POST \
  https://api.telegram.org/bot{TENANT_BOT_TOKEN}/setWebhook \
  -d "url={webhook_url}"
```

### Test Tenant Webhook

1. Send a message to tenant's Telegram bot
2. Check Heroku logs for webhook receipt: `heroku logs -t`
3. Should see: `Tenant webhook message from {tenant_id} in chat {chat_id}`

## Performance Optimization

For production:

1. **Upgrade Dyno** (if needed):
   ```powershell
   heroku ps:type Standard-1x  # $7/month
   heroku ps:scale web=2       # Multiple dynos for load balancing
   ```

2. **Optimize Database**:
   ```powershell
   heroku pg:diagnose
   ```

3. **Monitor Connections**:
   ```powershell
   heroku pg:connections
   ```

## Security Checklist

- [ ] All environment variables set and verified
- [ ] `X_ACCESS_TOKEN` is cryptographically random (not a simple string)
- [ ] `TELEGRAM_WEBHOOK_SECRET` is cryptographically random
- [ ] Database backups enabled on Neon
- [ ] HTTPS enforced (Heroku provides this by default)
- [ ] Logs monitored for errors
- [ ] Rate limiting considered for API endpoints
- [ ] API tokens rotated periodically

## Troubleshooting

### PostgresBackend not being used

```powershell
# Verify DATABASE_URL is set
heroku config:get DATABASE_URL

# Should return a postgresql:// connection string, not empty
```

### Slow deployments

```powershell
# Check for stuck dyno processes
heroku ps:kill web.1

# Redeploy
git push heroku main -f
```

### Database errors

```powershell
# Check Postgres logs
heroku logs -t --dyno postgres

# Run diagnostics
heroku pg:diagnose
```

### Webhook not receiving updates

```powershell
# Verify webhook is registered
curl https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo | jq .

# Check webhook URL is accessible
curl https://your-app.herokuapp.com/health

# View webhook processing logs
heroku logs -t | grep "tenant_webhook"
```

## Deployment Summary

✅ **Code is production-ready**

- Zero breaking changes to existing code
- Graceful fallback to SQLite if Postgres unavailable
- Comprehensive error handling and logging
- Security validations on all endpoints
- Webhook system fully functional
- Migration path from SQLite to Postgres available

**Ready to deploy to Heroku!**

## Support

For issues, check:
1. Heroku logs: `heroku logs -t`
2. Postgres connection: `heroku pg:psql`
3. Environment variables: `heroku config`
4. App status: `heroku ps`

