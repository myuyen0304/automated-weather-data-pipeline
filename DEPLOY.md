# Deploy: a live, recruiter-clickable version

Goal: turn "here's a repo" into "here's something running you can click". This guide uses **one**
free path and reuses the pipeline as-is — the only change is pointing `.env` at a cloud database
instead of local Docker.

> The pipeline already reads its database connection from `.env`
> (`DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`). "Deploying the data" therefore
> means: point those five variables at a managed Postgres, then run the **same** commands you run
> locally. No code change.

## Path: Supabase (free Postgres) + Power BI Service

```text
Local pipeline (extract/transform)  ->  Supabase Postgres (free tier, cloud)  ->  Power BI report (published)
```

Why this path: Supabase gives a free, internet-reachable Postgres; because it is cloud-hosted,
Power BI Service can schedule refresh against it **without an on-premises data gateway**. The result
is a dashboard with a shareable link backed by a live database.

### Step 1 — Create the database  *(only you can do this — needs your account)*
1. Create a free project at <https://supabase.com>.
2. In **Project Settings → Database**, copy the connection info. You will get:
   - Host: `db.<project-ref>.supabase.co` (direct) — or the **Connection Pooling** host if your
     machine has no IPv6 (recommended on most home networks).
   - Port: `5432` (direct) or `6543` / `5432` (pooler, Session mode).
   - Database: `postgres`
   - User: `postgres` (or `postgres.<project-ref>` for the pooler)
   - Password: the one you set when creating the project.

### Step 2 — Point the pipeline at Supabase
Edit `.env` (do **not** commit it):

```text
DB_HOST=db.<project-ref>.supabase.co        # or the pooler host
DB_PORT=5432                                 # or 6543 for the pooler
DB_NAME=postgres
DB_USER=postgres                             # or postgres.<project-ref> for the pooler
DB_PASSWORD=<your-supabase-db-password>
```

### Step 3 — Build the schema and load data into the cloud  *(you run this locally)*
Same commands as local, now hitting Supabase:

```bash
python src/main.py --init-db            # creates dims, fact, weather marts, agriculture schema + FAO-56 mart
python src/backfill_weather.py --start-date 2026-05-10 --end-date 2026-06-08
python src/main.py --skip-extract --all-raw --load   # transform + validate + load star schema
python src/main.py --load-agriculture   # load dim_agri_region; mart_irrigation_need then has data
```

No local Python? Run the exact same steps through the Docker `pipeline` service, overriding
`DB_*` to point at Supabase instead of the compose Postgres (env passed with `-e` wins over the
service defaults via `override=False`):

```bash
docker compose build pipeline
docker compose run --rm \
  -e DB_HOST=db.<project-ref>.supabase.co -e DB_PORT=5432 -e DB_NAME=postgres \
  -e DB_USER=postgres -e DB_PASSWORD=<your-supabase-db-password> \
  pipeline python src/main.py --init-db
# ...then backfill / --load / --load-agriculture / `dbt build --project-dir weather_dbt`
# with the same four -e overrides.
```

Verify in the Supabase **SQL Editor**:

```sql
SELECT count(*) FROM mart_daily_weather_summary;
SELECT count(*), count(DISTINCT city) FROM mart_irrigation_need;
```

### Step 4 — Publish the dashboard  *(only you can do this — needs your Power BI account)*
1. In Power BI Desktop, repoint the PostgreSQL source to the Supabase host/database (same Server /
   Database fields, **Import** mode). Refresh.
2. **Publish** to the Power BI Service (a free account publishes to *My workspace*).
3. To get a public link, use **File → Embed report → Publish to web (public)** — note this makes the
   report world-readable, so only publish non-sensitive public weather data (which is all this uses).
4. Optional: set **Scheduled refresh** in the Service with the Supabase credentials stored — no
   gateway needed because the database is cloud-hosted.

Put the resulting public report URL at the top of the README so a recruiter can click it.

## Honest limitations (state these, don't hide them)
- Supabase free tier pauses a project after a week of inactivity; click the project to wake it
  before a demo.
- "Publish to web" is public and unauthenticated — fine for public weather data, never for anything
  private.
- This hosts the **data + dashboard**, not Airflow. Airflow stays a local/Docker demo; the cloud
  story is "the analytical layer is live", which is the part a recruiter actually clicks.

## Alternative (if you want a fully self-hosted public link)
A small **Streamlit** app on Streamlit Community Cloud (free) reading the same Supabase Postgres
gives a public URL that also shows your Python — but it is extra build beyond the existing pipeline.
The Supabase + Power BI path above reuses what you already have, so start there.
