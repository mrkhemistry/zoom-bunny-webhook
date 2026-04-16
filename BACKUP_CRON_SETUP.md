# Monthly Supabase Backup — Setup Checklist

This guide walks through getting the monthly Supabase → Google Drive backup running on Railway. Work through it in order — each section unblocks the next.

---

## What was added to the repo

- **`backup_cron.py`** — entrypoint, runs once per cron fire, then exits.
- **`gdrive_client.py`** — extended with `create_folder`, `find_child_folder`, `upload_bytes`, `list_child_folders`, `delete_folder`. The existing Zoom webhook behaviour is untouched.
- **`requirements.txt`** — added `psycopg2-binary`, `python-dateutil`.

Behaviour on each run:
1. Creates `Backups/supabase/YYYY-MM-DD/` on Drive (appends `-HHMM` if today's folder already exists).
2. For each Supabase project, dumps every table in `public` to CSV via `COPY` and uploads it under `<date>/<project>/`.
3. Writes a `manifest.json` per project (row counts) and a `run_summary.json` at the date-folder level.
4. Deletes any sibling date folders older than **12 months**. Only folders matching `YYYY-MM-DD` or `YYYY-MM-DD-HHMM` are candidates — nothing else gets touched.

---

## Step 1 — Drive: create the parent folder and share it

1. In Google Drive, inside `Backups/`, create a subfolder named `supabase/` (if it doesn't already exist from the April backup — it does; use that one).
2. Right-click → Share → add the service account email as **Editor**:
   ```
   zoom-drive-backup@eric-kua-website-1549201801213.iam.gserviceaccount.com
   ```
3. Copy the folder's ID from its URL. The URL looks like `https://drive.google.com/drive/folders/1ABC...XYZ` — the ID is the part after `/folders/`. Keep it for Step 3.

> The service account uses the `drive.file` scope, which means it can only see folders it created OR folders explicitly shared with it. Sharing the parent is mandatory.

---

## Step 2 — Supabase: get the connection strings

For **each** project (chembank and invoicing):

1. Go to https://supabase.com/dashboard/project/<project_id>/settings/database
   - chembank: project `fvjqsohhitpnkvfirosc`
   - invoicing: project `ronealwwzaxsaznwvoab`
2. Under **Connection string**, choose **Session pooler** (NOT "Direct connection" — Railway's network is IPv4-only by default, and the session pooler supports `COPY` which the transaction pooler does not).
3. Click the URI tab and copy the string. It looks like:
   ```
   postgresql://postgres.fvjqsohhitpnkvfirosc:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
   ```
4. Replace `[YOUR-PASSWORD]` with the database password. If you don't have it saved, reset it from the same page — note that other apps using this DB will need the new password too.

Keep both full URLs ready for Step 3.

---

## Step 3 — Railway: create the cron service

1. Open the **refreshing-trust** project in Railway.
2. Click **New Service** → **GitHub Repo** → select the same repo as the existing Zoom webhook service. Pick the same branch.
3. Once the service is created, open it and rename it (e.g. `supabase-backup-cron`) so it's not confused with the webhook.
4. **Settings → Deploy**:
   - **Custom Start Command**: `python backup_cron.py`
   - **Cron Schedule**: `0 18 1 * *`  (= 1st of each month, 18:00 UTC = 02:00 SGT)
   - Leave health-check path blank (cron services don't need one).
5. **Variables**:
   - Copy these from the existing Zoom webhook service (Railway lets you "reference" variables from another service):
     - `GOOGLE_SERVICE_ACCOUNT_JSON`
   - Add new:
     - `GDRIVE_BACKUP_PARENT_ID` = the folder ID from Step 1
     - `SUPABASE_CHEMBANK_DB_URL` = chembank connection string from Step 2
     - `SUPABASE_INVOICING_DB_URL` = invoicing connection string from Step 2
6. **Deploy**. The first deploy builds the image; it won't actually run until the next cron fire unless you trigger it manually (next step).

---

## Step 4 — Test run

Don't wait a month for the first run. Trigger manually:

1. In the cron service, click **Deployments** → latest deployment → **⋯ menu** → **Restart** (or **Run now**, depending on the Railway UI version).
2. Open the **Logs** tab. You should see lines like:
   ```
   INFO backup_cron: Starting monthly backup. Drive folder: 2026-04-16
   INFO gdrive_client: Created Drive folder '2026-04-16' ...
   INFO backup_cron: Backing up Supabase project: chembank
   INFO backup_cron: chembank: found 13 tables in public schema
   INFO backup_cron:   chembank.questions: 1020 rows
   ...
   INFO backup_cron: Backup complete.
   ```
3. In Drive, open `Backups/supabase/` — you should see a new dated folder with `chembank/`, `invoicing/`, and `run_summary.json`.
4. Spot-check one CSV (open `students.csv` or `questions.csv`) and the `manifest.json` row counts.

If anything goes wrong, the exit code is logged:
- **0** — success
- **1** — configuration error (env var missing, Drive unreachable). Check variables.
- **2** — ran, but one or more tables or projects failed. Check logs for stack traces.

---

## Step 5 — (optional) Alerting

Railway will keep running the cron silently forever, so a failed run is easy to miss. Two cheap options:

- **Railway built-in**: Settings → Notifications → enable emails on deployment failure. (Only catches startup crashes, not logical errors with exit 2.)
- **Manual check**: glance at Drive once a month.

If you want real monitoring, use a service like healthchecks.io — I can wire that up later if useful.

---

## Restoring from a backup

Each table CSV was produced by Postgres `COPY ... TO STDOUT WITH CSV HEADER`. To restore one table into a fresh Supabase project:

```sql
-- In the Supabase SQL editor or psql:
COPY "public"."students" FROM STDIN WITH CSV HEADER;
-- then paste the CSV contents, end with \.
```

For bulk restore, `psql -c "\copy public.students FROM 'students.csv' CSV HEADER"` is the faster path.

---

## Files touched

- `backup_cron.py` (new)
- `gdrive_client.py` (extended, existing functions unchanged)
- `requirements.txt` (2 new pins)

Nothing else in the repo changed. The Zoom webhook (`app.py`, `bunny_client.py`, `zoom_client.py`, `portal.py`, `config.py`) is untouched.
