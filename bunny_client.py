import logging
import os
import requests

logger = logging.getLogger(__name__)

BUNNY_VIDEO_API = "https://video.bunnycdn.com"


def create_video(library_id, library_api_key, title):
    """Create a new video entry in a Bunny.net library. Returns the video GUID."""
    resp = requests.post(
        f"{BUNNY_VIDEO_API}/library/{library_id}/videos",
        headers={"AccessKey": library_api_key},
        json={"title": title},
        timeout=30,
    )
    resp.raise_for_status()
    video = resp.json()
    logger.info("Created Bunny video %s in library %s", video["guid"], library_id)
    return video["guid"]


def upload_video_from_file(library_id, library_api_key, video_guid, file_path):
    """Stream-upload a video file to Bunny.net from a path on disk.

    Bunny rejects chunked transfer encoding (videos get stuck in 'Uploading'
    state forever), so we set Content-Length explicitly. The requests library
    will then stream the file body without buffering it in RAM.
    """
    size = os.path.getsize(file_path)
    upload_url = f"{BUNNY_VIDEO_API}/library/{library_id}/videos/{video_guid}"
    logger.info("Uploading %d bytes to Bunny...", size)

    with open(file_path, "rb") as f:
        resp = requests.put(
            upload_url,
            headers={
                "AccessKey": library_api_key,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(size),
            },
            data=f,
            timeout=3600,
        )
    resp.raise_for_status()
    logger.info("Uploaded video %s to library %s", video_guid, library_id)
    return resp.json()
