"""Monthly Supabase -> Google Drive backup.

Run via Railway cron service on the 1st of each month. Dumps every table in
the `public` schema of each Supabase project to CSV, uploads to a dated Drive
folder, and prunes folders older than RETENTION_MONTHS.

Drive layout produced:
    <GDRIVE_BACKUP_PARENT_ID>/
        2026-05-01/
            chembank/
                questions.csv
                user_profiles.csv
                ...
                manifest.json
            invoicing/
                students.csv
                ...
                manifest.json
        2026-04-01/
            ...

Required env vars:
    GOOGLE_SERVICE_ACCOUNT_JSON   JSON for the Drive service account
    GDRIVE_BACKUP_PARENT_ID       Drive folder ID (must be shared with the
                                  service account as Editor)
    SUPABASE_CHEMBANK_DB_URL      Postgres connection string (session pooler)
    SUPABASE_INVOICING_DB_URL     Postgres connection string (session pooler)

Exit codes:
    0  all projects backed up successfully
    1  configuration / credential problem — nothing was attempted
    2  ran, but one or more projects failed (see logs)
"""

import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

import psycopg2
from dateutil.relativedelta import relativedelta

from gdrive_client import (
    _get_service,
    create_folder,
    delete_folder,
    find_child_folder,
    list_child_folders,
    upload_bytes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backup_cron")

RETENTION_MONTHS = 12

# Matches "2026-05-01" and also re-run suffixes like "2026-05-01-0302".
DATE_FOLDER_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:-\d{4})?$")

PROJECTS = [
    {"name": "chembank", "db_url_env": "SUPABASE_CHEMBANK_DB_URL"},
    {"name": "invoicing", "db_url_env": "SUPABASE_INVOICING_DB_URL"},
]


def list_public_tables(conn):
    """Return all base tables in the public schema, sorted alphabetically."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [row[0] for row in cur.fetchall()]


def dump_table_csv(conn, table_name):
    """Dump a single table to CSV bytes. Returns (csv_bytes, row_count)."""
    buf = io.StringIO()
    with conn.cursor() as cur:
        # Identifier is quoted and sourced from information_schema — not user
        # input — so SQL injection isn't a risk here.
        cur.copy_expert(
            f'COPY "public"."{table_name}" TO STDOUT WITH CSV HEADER',
            buf,
        )
        cur.execute(f'SELECT count(*) FROM "public"."{table_name}"')
        row_count = cur.fetchone()[0]
    return buf.getvalue().encode("utf-8"), row_count


def backup_project(project, date_folder_id):
    """Back up one Supabase project. Returns a manifest dict.

    The manifest has an "error" key if the backup could not be attempted,
    otherwise a "tables" dict with row counts (or the string "ERROR").
    """
    name = project["name"]
    db_url = os.environ.get(project["db_url_env"])
    if not db_url:
        logger.error("Missing env var %s — skipping %s", project["db_url_env"], name)
        return {"project": name, "error": f"missing env var {project['db_url_env']}"}

    logger.info("Backing up Supabase project: %s", name)
    conn = psycopg2.connect(db_url)
    try:
        conn.set_session(readonly=True)
        project_folder_id = create_folder(name, date_folder_id)
        tables = list_public_tables(conn)
        logger.info("%s: found %d tables in public schema", name, len(tables))

        table_stats = {}
        for table in tables:
            try:
                csv_bytes, row_count = dump_table_csv(conn, table)
                upload_bytes(
                    f"{table}.csv",
                    csv_bytes,
                    "text/csv",
                    project_folder_id,
                )
                table_stats[table] = row_count
                logger.info("  %s.%s: %d rows", name, table, row_count)
            except Exception:
                logger.exception("Failed to dump %s.%s", name, table)
                table_stats[table] = "ERROR"
    finally:
        conn.close()

    manifest = {
        "project": name,
        "backup_date_utc": datetime.now(timezone.utc).isoformat(),
        "total_tables": len(tables),
        "tables": table_stats,
    }
    manifest_bytes = json.dumps(manifest, indent=2, default=str).encode("utf-8")
    upload_bytes(
        "manifest.json",
        manifest_bytes,
        "application/json",
        project_folder_id,
    )
    return manifest


def _pick_date_folder_name(parent_id):
    """Pick today's folder name, appending -HHMM if the plain date exists.

    Protects against accidental duplicate-content on same-day re-runs.
    """
    now = datetime.now(timezone.utc)
    base = now.strftime("%Y-%m-%d")
    if find_child_folder(base, parent_id) is None:
        return base
    suffix = now.strftime("%H%M")
    return f"{base}-{suffix}"


def prune_old_backups(parent_id):
    """Delete date folders older than RETENTION_MONTHS. Returns list of names deleted.

    Only folders whose name matches DATE_FOLDER_RE are candidates — anything
    else is left alone.
    """
    cutoff = (datetime.now(timezone.utc) - relativedelta(months=RETENTION_MONTHS)).date()
    folders = list_child_folders(parent_id)
    deleted = []
    for folder in folders:
        match = DATE_FOLDER_RE.match(folder["name"])
        if not match:
            continue
        try:
            folder_date = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            ).date()
        except ValueError:
            continue
        if folder_date < cutoff:
            logger.info("Pruning old backup folder: %s", folder["name"])
            try:
                delete_folder(folder["id"])
                deleted.append(folder["name"])
            except Exception:
                logger.exception("Failed to delete folder %s", folder["name"])
    return deleted


def main():
    parent_id = os.environ.get("GDRIVE_BACKUP_PARENT_ID", "")
    if not parent_id:
        logger.error("GDRIVE_BACKUP_PARENT_ID not set")
        return 1

    if _get_service() is None:
        logger.error("Google Drive service unavailable (check GOOGLE_SERVICE_ACCOUNT_JSON)")
        return 1

    folder_name = _pick_date_folder_name(parent_id)
    logger.info("Starting monthly backup. Drive folder: %s", folder_name)
    date_folder_id = create_folder(folder_name, parent_id)

    results = []
    for project in PROJECTS:
        try:
            results.append(backup_project(project, date_folder_id))
        except Exception:
            logger.exception("Fatal error backing up %s", project["name"])
            results.append({"project": project["name"], "error": "fatal exception"})

    # Write a top-level summary manifest for the whole run.
    summary = {
        "run_date_utc": datetime.now(timezone.utc).isoformat(),
        "retention_months": RETENTION_MONTHS,
        "projects": results,
    }
    upload_bytes(
        "run_summary.json",
        json.dumps(summary, indent=2, default=str).encode("utf-8"),
        "application/json",
        date_folder_id,
    )

    # Retention cleanup runs AFTER today's backup succeeds so we never
    # delete old backups if the new one failed to start.
    deleted = prune_old_backups(parent_id)
    logger.info("Pruned %d old backup folder(s): %s", len(deleted), deleted)

    had_errors = any("error" in r or "ERROR" in (r.get("tables") or {}).values() for r in results)
    if had_errors:
        logger.warning("Backup completed with errors — see logs")
        return 2
    logger.info("Backup complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
