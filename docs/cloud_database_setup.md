# Moving the database to managed PostgreSQL

The platform is PostgreSQL-only. Development runs against a local server; the
deployed app needs a managed instance that Streamlit Cloud can reach.

Current size: **~4.3 MB, 15,312 rows across 21 tables**. That fits inside every
free tier listed below with room to grow.

---

## 1. Pick a provider

| Provider | Free tier | Why you might pick it |
|---|---|---|
| **Neon** | 0.5 GB | Serverless, scales to zero, generous free tier, fast setup |
| **Supabase** | 500 MB | Postgres plus auth/storage if you want them later |
| **Railway** | trial credit | Simplest dashboard |
| **Render** | 1 GB (90 days) | Fine for a pilot, expires |
| **Aiven** | trial | Has EU regions, closer to Ghana than us-east |

There is no "official Postgres cloud" because Postgres is an open-source
project rather than a company. All of the above run stock PostgreSQL, so the
application code does not change between them.

**Recommendation: Neon.** The free tier does not expire, it supports the
`sslmode=require` the app now sets automatically, and the connection string is
a plain Postgres DSN.

Pick a region close to Ghana. `eu-central-1` (Frankfurt) or `eu-west-2`
(London) will be noticeably faster from Accra than a US region.

---

## 2. Create the database

1. Sign up and create a project.
2. Create a database named `amr_surveillance`.
3. Copy the connection string. It looks like:

   ```
   postgresql://USER:PASSWORD@ep-xxxx.eu-central-1.aws.neon.tech/amr_surveillance
   ```

   If the provider offers both a **direct** and a **pooled** connection string,
   take the pooled one for the deployed app — Streamlit opens and closes
   connections per page load.

---

## 3. Migrate

Dry run first. It writes nothing and tells you exactly what would move:

```bash
python scripts/migrate_to_cloud.py --target "postgresql://..." --dry-run
```

Then the real run:

```bash
python scripts/migrate_to_cloud.py --target "postgresql://..."
```

The script builds the schema on the target by calling the application's own
`init_database()`, so the cloud gets exactly the tables, constraints and
indexes the code expects. It then copies tables parent-first so foreign keys
are satisfied as it goes, resets sequences so the next insert cannot collide
with a copied id, and finishes with a row-count comparison. It exits non-zero
on any mismatch.

It refuses to write into a target table that already holds rows. If you are
re-running deliberately, add `--truncate`.

Check it again at any time:

```bash
python scripts/migrate_to_cloud.py --target "postgresql://..." --verify-only
```

---

## 4. Point the application at the cloud

**Local development** — edit `.env`:

```
DATABASE_URL=postgresql://USER:PASSWORD@host/amr_surveillance
```

**Streamlit Cloud** — open the app, then `Settings -> Secrets`, and add:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@host/amr_surveillance"
AMRSS_PATIENT_SALT = "<copy the value from your local .env>"
```

Both matter:

- **`DATABASE_URL` is now required.** The SQLite fallback was removed, so a
  missing or unreachable database fails at startup instead of quietly serving
  a stale local snapshot. If the deployed app shows a startup error after this
  change, this secret is the first thing to check.
- **`AMRSS_PATIENT_SALT` must match everywhere.** Patient pseudonyms are a
  salted hash. A different salt produces different pseudonyms for the same
  patient, which silently breaks linkage between specimens and makes
  first-isolate deduplication wrong. Back it up somewhere safe. Rotating it
  invalidates every existing pseudonym.

TLS is handled for you: the app adds `sslmode=require` automatically for any
non-local host, which managed providers demand.

---

## 5. Confirm

```bash
python -c "from src import db; print(len(db.get_all_samples()), 'samples')"
```

Then load the deployed app and check the sample and AST counts match what the
migration reported.

---

## Notes

- **Back up before switching.** `python scripts/export_data_snapshot.py` writes
  a compressed JSON snapshot of every table.
- **Free tiers sleep.** Neon and Supabase pause an idle database; the first
  request after a pause takes a few seconds. The app's `connect_timeout` is 8s
  by default — raise `DB_CONNECT_TIMEOUT` if you see timeouts on first load.
- **Do not commit connection strings.** `.env` and `.streamlit/secrets.toml`
  are both gitignored; keep it that way.
