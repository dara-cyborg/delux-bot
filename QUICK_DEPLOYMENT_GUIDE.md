# Quick Deployment Guide

## Status: ✅ READY FOR PRODUCTION

All 6 phases of the Postgres migration are complete. The app is ready to deploy to production with Neon Postgres.

## Pre-Deployment Checklist

- ✅ All code compiles without errors
- ✅ Phases 1-6 implemented and tested
- ✅ Security features: audit logging, rate limiting, webhook validation
- ✅ Database schema supports SQLite (dev) and Postgres (prod)
- ✅ Migration script ready for data transfer

## Deployment Steps (5 minutes)

### Step 1: Create Neon Postgres (2 min)
1. Go to https://console.neon.tech/
2. Sign up or log in
3. Create new project
4. Copy the **pooled** connection string (includes `?pooler_mode=transaction`)
5. Keep it secure - don't commit to git

### Step 2: Deploy to Heroku (2 min)
```powershell
# Set environment variable
heroku config:set DATABASE_URL="<paste-neon-pooled-string-here>"

# Verify it's set
heroku config:get DATABASE_URL

# Deploy
git push heroku main
```

### Step 3: Verify Deployment (1 min)
```powershell
# Check logs
heroku logs --tail

# Should see: "SQLite fallback disabled: using Postgres backend"
```

## Data Migration (if migrating from SQLite)

```powershell
# Set local environment variable
$env:DATABASE_URL="<neon-pooled-string>"

# Run migration
python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db

# Verify counts match
# Check per-tenant statistics printed at end
```

## Smoke Test (5 min)

### 1. Configure Test Tenant
```bash
curl -X POST https://your-app.herokuapp.com/api/tenants/test-tenant/telegram/config \
  -H "X-Access-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
    "telegram_chat_id": "YOUR_CHAT_ID_HERE"
  }'
```

Expected response includes `webhook_url` and `webhook_secret`.

### 2. Register Webhook with Telegram
```bash
curl -X POST https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook \
  -d "url=https://your-app.herokuapp.com/telegram/tenant-webhook/test-tenant/WEBHOOK_SECRET"
```

### 3. Send Test Order
```bash
curl -X POST https://your-app.herokuapp.com/api/tenants/test-tenant/orders \
  -H "X-Access-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "smoke-test",
    "commenter": "Test User",
    "comment": "Test order",
    "comment_id": "test123",
    "collected_at": "2024-01-15T10:30:00Z",
    "profile_url": "https://example.com",
    "order_date": "2024-01-15",
    "source_host": "example.com"
  }'
```

### 4. Test Telegram Commands
1. Open your test bot in Telegram
2. Send `/start` → Should see welcome message
3. Send `/menu` → Should see menu
4. Send `/sessions` → Should see "smoke-test" session
5. Send `/today` → Should see test order
6. Click buttons → Navigation should work

✅ If all commands work, deployment is successful!

## Monitoring in Production

```powershell
# Watch logs in real-time
heroku logs --tail

# Check specific errors
heroku logs --grep "ERROR"

# Check audit logs
heroku logs --grep "AUDIT"

# Check rate limiting
heroku logs --grep "RateLimit"
```

## Production Configuration

### Environment Variables Required
- `DATABASE_URL` - Neon pooled connection string (set on Heroku)
- `APP_DOMAIN` - Your Heroku app URL (e.g., `https://your-app.herokuapp.com`)
- `TELEGRAM_BOT_TOKEN` - Shared bot token (still used for alerts)
- `TELEGRAM_CHAT_ID` - Shared chat ID (still used for alerts)
- `X_ACCESS_TOKEN` - Service token for API access

### Rate Limits
- Webhook endpoints: 1000 requests/min per IP
- API endpoints: 100 requests/min per IP
- Health check: unlimited

### Security Features Active
- ✅ Per-tenant webhook secrets (256-bit)
- ✅ Chat ID validation on webhooks
- ✅ No raw tokens in API responses
- ✅ Audit logging for config changes
- ✅ Rate limiting with 429 responses
- ✅ Unique enabled chat ID constraint

## Rollback Plan

If critical issue occurs:
```powershell
# Disable Postgres
heroku config:unset DATABASE_URL

# Restart app
heroku dyno:restart

# App will fall back to SQLite
heroku logs --tail
```

Then fix the issue and redeploy:
```powershell
# Fix code
git commit -am "Fix issue"

# Redeploy
git push heroku main

# Re-enable Postgres
heroku config:set DATABASE_URL="<neon-string>"

# Restart
heroku dyno:restart
```

## Key Files Reference

- **Server**: [server.py](server.py) - FastAPI app, endpoints, webhooks
- **Database**: [telegram_bot/database.py](telegram_bot/database.py) - SQLite/Postgres abstraction
- **Storage**: [telegram_bot/tenant_store.py](telegram_bot/tenant_store.py) - Tenant data access
- **Audit**: [telegram_bot/audit.py](telegram_bot/audit.py) - Logging system
- **Rate Limiting**: [telegram_bot/middleware.py](telegram_bot/middleware.py) - Rate limiter
- **Migration**: [scripts/migrate_sqlite_to_postgres.py](scripts/migrate_sqlite_to_postgres.py) - Data migration
- **Plan**: [docs/POSTGRES_TENANT_BOT_MIGRATION_PLAN.md](docs/POSTGRES_TENANT_BOT_MIGRATION_PLAN.md) - Full details

## Support

Check logs for issues:
```powershell
heroku logs --tail
heroku logs --grep "ERROR"
heroku logs --grep "AUDIT"
```

See full migration plan in [docs/POSTGRES_TENANT_BOT_MIGRATION_PLAN.md](docs/POSTGRES_TENANT_BOT_MIGRATION_PLAN.md) for detailed documentation.

## Summary

**Status**: ✅ Ready to deploy
**Time to deploy**: ~5 minutes
**Downtime**: None (blue/green deployment)
**Rollback**: < 1 minute if needed

You can now deploy to production with confidence! 🚀
