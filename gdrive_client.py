import json
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

logger = logging.getLogger(__name__)

# Load service account credentials from env var (JSON string)
_credentials = None
_service = None

GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "")
# drive.file scope only grants access to files/folders the service account
# created OR has been explicitly shared into. The backup parent folder must
# be shared with the service account email.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_service():
    """Lazy-init the Google Drive API service."""
    global _credentials, _service
    if _service:
        return _service

    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON not set — Google Drive backup disabled")
        return None

    sa_info = json.loads(sa_json)
    _credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    _service = build("drive", "v3", credentials=_credentials, cache_discovery=False)
    return _service


def upload_to_drive(filename, video_data):
    """Upload video bytes to Google Drive backup folder.

    Args:
        filename: Name for the file in Drive (e.g. "JC1 - speaker_view.mp4")
        video_data: Raw bytes of the video file
    """
    if not GDRIVE_FOLDER_ID:
        logger.info("GDRIVE_FOLDER_ID not set — skipping Google Drive backup")
        return None

    service = _get_service()
    if not service:
        return None

    file_metadata = {
        "name": filename,
        "parents": [GDRIVE_FOLDER_ID],
    }

    media = MediaInMemoryUpload(video_data, mimetype="video/mp4", resumable=True)

    logger.info("Uploading %s (%.1f MB) to Google Drive...", filename, len(video_data) / 1024 / 1024)

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, size",
    ).execute()

    logger.info("Google Drive upload complete: %s (id: %s)", file["name"], file["id"])
    return file["id"]


# ---------------------------------------------------------------------------
# Generic helpers used by backup_cron.py
# ---------------------------------------------------------------------------

_FOLDER_MIME = "application/vnd.google-apps.folder"


def create_folder(name, parent_id):
    """Create a folder under parent_id. Returns the folder ID.

    Drive allows multiple folders with the same name — we don't dedupe here.
    The caller is responsible for choosing unique names if needed.
    """
    service = _get_service()
    if not service:
        raise RuntimeError("Google Drive service unavailable")

    metadata = {
        "name": name,
        "mimeType": _FOLDER_MIME,
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id, name").execute()
    logger.info("Created Drive folder '%s' (id: %s)", folder["name"], folder["id"])
    return folder["id"]


def find_child_folder(name, parent_id):
    """Find a folder with the given name under parent_id. Returns id or None."""
    service = _get_service()
    if not service:
        return None

    # Escape single quotes in the name for the Drive query syntax.
    safe_name = name.replace("'", "\\'")
    query = (
        f"name = '{safe_name}' "
        f"and mimeType = '{_FOLDER_MIME}' "
        f"and '{parent_id}' in parents "
        f"and trashed = false"
    )
    resp = service.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
    ).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def upload_bytes(filename, data, mimetype, parent_id):
    """Upload arbitrary bytes to Drive under parent_id. Returns the file ID."""
    service = _get_service()
    if not service:
        raise RuntimeError("Google Drive service unavailable")

    metadata = {"name": filename, "parents": [parent_id]}
    media = MediaInMemoryUpload(data, mimetype=mimetype, resumable=False)
    file = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, size",
    ).execute()
    size_kb = len(data) / 1024
    logger.info("Uploaded %s (%.1f KB) to Drive (id: %s)", filename, size_kb, file["id"])
    return file["id"]


def list_child_folders(parent_id):
    """List all non-trashed folders directly under parent_id.

    Returns a list of {id, name}. Paginates through all results.
    """
    service = _get_service()
    if not service:
        return []

    query = (
        f"mimeType = '{_FOLDER_MIME}' "
        f"and '{parent_id}' in parents "
        f"and trashed = false"
    )
    folders = []
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()
        folders.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return folders


def delete_folder(folder_id):
    """Permanently delete a folder (and its contents) from Drive.

    Uses Files.delete (permanent). For soft-delete, use Files.update with
    trashed=true instead.
    """
    service = _get_service()
    if not service:
        raise RuntimeError("Google Drive service unavailable")
    service.files().delete(fileId=folder_id).execute()
    logger.info("Deleted Drive folder id: %s", folder_id)
