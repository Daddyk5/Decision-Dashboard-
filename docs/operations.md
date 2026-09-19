# Operations Runbook

## Daily workflow

1. Confirm `.env` contains the Supabase Session Pooler host, username, password, and `DB_SSLMODE=require`.
2. Run `manage.py check` after code or configuration changes.
3. Apply migrations with `manage.py migrate` before using new model fields.
4. Review `/admin/` for new batches, delivery statuses, and payment statuses.
5. Review `/` for current stock, expiry risk, logistics, and receivables.
6. Run the metrics job when a log snapshot is required:

```powershell
.\env\Scripts\python.exe jobs\update_metrics.py
```

The job reads `inventory_inventorybatch` and `inventory_payment`, classifies expiry in PostgreSQL, and logs healthy stock, expired stock, and unpaid balances. It does not modify records.

## Dashboard behavior

The dashboard uses live database queries. The optional `from_date` and `to_date` query parameters filter inventory by `arrival_date`, deliveries by `scheduled_date`, and receivables by related order date:

```text
/?from_date=2026-01-01&to_date=2026-12-31
```

The page is responsive: KPI cards stack on narrow screens, charts stack below the large-screen two-column layout, and tables scroll horizontally when required.

## Troubleshooting

### `could not translate host name`

The direct Supabase database endpoint may be IPv6-only. Use the Session Pooler host from Supabase Connect. For the Mumbai project, the expected format is `aws-0-ap-south-1.pooler.supabase.com` with user `postgres.<project-ref>`.

### `password authentication failed`

Reset or verify the database password in Supabase Connect. A Supabase publishable or secret API key is not the PostgreSQL password.

### `connection refused` on `localhost:5432`

Django is using fallback values because `.env` is missing or not loaded. Confirm `.env` exists at the project root and contains `DB_HOST` and `DB_PORT`.

### Dashboard shows zero records

The migration creates tables but does not seed business data. Add records through `/admin/` or an approved import process. Empty states are expected until inventory, orders, deliveries, and payments exist.

### Production checklist

- Set `DEBUG=False`.
- Set an environment-specific `SECRET_KEY`.
- Set `ALLOWED_HOSTS` to the deployed hostnames only.
- Keep `.env` outside source control and rotate exposed credentials.
- Replace CDN Tailwind with a compiled asset pipeline for production.
- Run `manage.py check --deploy` before release.
- Use a production WSGI/ASGI server and HTTPS.
