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
