# Deployment Guide

## Prerequisites

- Heroku CLI installed and authenticated (`heroku login`)
- Git repository initialized with Heroku app configured
- Neon Postgres database ready (or create one)

## Deployment Steps

### 1. Create Neon Postgres Database

Visit [Neon Console](https://console.neon.tech) and:

1. Create a new project
2. Copy the **pooled connection string** (important for connection pooling)
3. Connection string format: `postgresql://user:password@host/dbname?sslmode=require`

### 2. Set Heroku Environment Variables

```powershell
# Set the Postgres connection string
heroku config:set DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require"

# Telegram bot token (the global shared bot, for backwards compatibility)
heroku config:set TELEGRAM_BOT_TOKEN="your-bot-token-here"

# Webhook secret for the global webhook endpoint
heroku config:set TELEGRAM_WEBHOOK_SECRET="your-webhook-secret-here"

# API access token for tenant config and order endpoints
heroku config:set X_ACCESS_TOKEN="your-api-token-here"

# Your Heroku app domain (for webhook URL generation)
heroku config:set APP_DOMAIN="https://your-app-name.herokuapp.com"

# Verify all vars are set
heroku config
```

### 3. Deploy to Heroku

```powershell
# Add Heroku remote if not already present
heroku git:remote -a your-app-name

# Deploy
git push heroku main
```

The `Procfile` specifies the startup command:
```
web: uvicorn server:app --host 0.0.0.0 --port $PORT
```

### 4. Run Database Migration (if migrating from SQLite)

If you have existing SQLite data to migrate:

```powershell
# Run the migration script
$env:DATABASE_URL="postgresql://..."
python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db
```

Alternatively, use Heroku one-off dyno:

```powershell
heroku run "python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db"
```

### 5. Verify Deployment

```powershell
# Check app logs
heroku logs -t

# Test the health endpoint
heroku open /health
# Should return: {"status":"ok"}

# Test the API (needs X-Access-Token header)
curl -X POST https://your-app.herokuapp.com/api/tenants/test-tenant/telegram/config \
  -H "X-Access-Token: your-api-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": false
  }'
```

## Tenant Setup

After deployment, each tenant can be configured:

```powershell
# 1. Create a Telegram bot with BotFather
# 2. Get tenant ID, bot token, and chat ID
# 3. Configure the tenant

$headers = @{
    "X-Access-Token" = "your-api-token-here"
    "Content-Type" = "application/json"
}

$body = @{
    enabled = $true
    telegram_bot_token = "123456789:ABC..."
    telegram_chat_id = "-1001234567890"
    telegram_message_template = $null  # Optional custom template
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://your-app.herokuapp.com/api/tenants/tenant-1/telegram/config" `
  -Method POST `
  -Headers $headers `
  -Body $body
```

Response will include:
```json
{
  "ok": true,
  "tenant_id": "tenant-1",
  "webhook_url": "https://your-app.herokuapp.com/telegram/tenant-webhook/tenant-1/webhook-secret-here",
  "webhook_secret": "webhook-secret-here",
  "telegram_config": {...}
}
```

### Register Webhook with Telegram

For each tenant bot, register the webhook:

```bash
# Use the webhook_url from the config response
curl -X POST \
  https://api.telegram.org/bot{BOT_TOKEN}/setWebhook \
  -d "url=https://your-app.herokuapp.com/telegram/tenant-webhook/tenant-1/webhook-secret-here"

# Verify webhook is set
curl https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo | jq .
```

## Ingest Orders

Send orders to the tenant API:

```powershell
$headers = @{
    "X-Access-Token" = "your-api-token-here"
    "Content-Type" = "application/json"
}

$body = @{
    session_id = "session-1"
    commenter = "John Doe"
    comment = "Please add 2 pizzas"
    comment_id = "comment-123"
    collected_at = "2024-06-26T10:30:00"
    profile_url = "https://example.com/profile"
    order_date = "2024-06-26"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://your-app.herokuapp.com/api/tenants/tenant-1/orders" `
  -Method POST `
  -Headers $headers `
  -Body $body
```

## Monitoring

### View Logs

```powershell
# Live logs
heroku logs -t

# Last 100 lines
heroku logs -n 100

# Filter by source
heroku logs -t --source app
heroku logs -t --source postgres
```

### Check Database

```powershell
# Connect to remote Postgres
heroku pg:psql

# Then run SQL queries
SELECT COUNT(*) FROM tenants;
SELECT COUNT(*) FROM orders;
SELECT * FROM tenant_telegram_config;
```

### Performance

```powershell
# Check dyno type and usage
heroku ps

# Upgrade if needed
heroku ps:type Standard-1x
```

## Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` | Yes (production) | Postgres connection string | `postgresql://...` |
| `TELEGRAM_BOT_TOKEN` | Yes | Global shared bot token | `123456789:ABC...` |
| `TELEGRAM_WEBHOOK_SECRET` | Yes | Secret for global webhook | Random string |
| `X_ACCESS_TOKEN` | Yes | API access token | Random string |
| `APP_DOMAIN` | No | App domain for webhook URLs | `https://app.herokuapp.com` |

## Rollback

If you need to rollback to a previous version:

```powershell
# See deployment history
heroku releases

# Rollback to previous version
heroku rollback v42

# Or redeploy specific commit
git push heroku commit-hash:main
```

## Troubleshooting

### "psycopg is required for Postgres support"

This error means `psycopg` is not installed. Heroku automatically installs dependencies from `requirements.txt` during deployment. Verify:

```powershell
heroku run "pip list | grep psycopg"
```

### Database connection issues

```powershell
# Verify DATABASE_URL is set correctly
heroku config:get DATABASE_URL

# Test connection
heroku run "python -c \"from telegram_bot.database import get_database_backend; print(type(get_database_backend()).__name__)\""
```

Should print: `PostgresBackend`

### Webhook not receiving updates

1. Verify webhook URL is accessible: `curl https://your-app.herokuapp.com/health`
2. Check Telegram webhook status: `heroku run "curl https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"`
3. View logs for errors: `heroku logs -t`

### Slow queries

Check for missing indexes:

```powershell
heroku pg:diagnose
```

Add missing indexes if suggested.

## Security Best Practices

1. **Never commit secrets**: Use environment variables only
2. **Rotate tokens regularly**: Update bot tokens and API keys
3. **Use HTTPS only**: Telegram requires HTTPS for webhooks
4. **Validate webhook secrets**: Always validate `X-Telegram-Bot-Api-Secret-Token` header
5. **Encrypt sensitive data**: Consider encrypting bot tokens at rest
6. **Monitor logs**: Watch for unauthorized access attempts
7. **Rate limiting**: Consider adding rate limits to API endpoints

## Performance Tuning

For high-volume order ingestion:

1. **Increase dyno type**: `heroku ps:type Standard-1x` or higher
2. **Add Postgres extensions**: Consider `pg_stat_statements` for query analysis
3. **Implement caching**: Cache frequently accessed tenant configs
4. **Monitor database**: Use `heroku pg:diagnose` regularly

## Scaling

### Horizontal Scaling (Multiple Dynos)

```powershell
heroku ps:scale web=2
```

### Database Scaling

Upgrade Postgres plan on Neon console for better performance.

## Cost Estimation

- **Heroku**: Free tier or $7-50/month depending on dyno type
- **Neon Postgres**: Free tier (4 compute hours/month) or paid plans
- **Total minimum**: ~$7/month with free tier Postgres

## Next Steps

1. ✅ Deploy app to Heroku
2. ✅ Create Postgres database on Neon
3. ✅ Configure environment variables
4. ✅ Register tenant webhooks with Telegram
5. ✅ Ingest test orders
6. ✅ Monitor logs and performance
7. 📋 Set up alerts for errors
8. 📋 Implement rate limiting
9. 📋 Add bot token encryption
