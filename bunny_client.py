import logging
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


def upload_video(library_id, library_api_key, video_guid, zoom_response):
    """Upload a video file to Bunny.net from the Zoom download response."""
    upload_url = f"{BUNNY_VIDEO_API}/library/{library_id}/videos/{video_guid}"

    # Read full content so we can send Content-Length (Bunny needs this to finalize the upload)
    video_data = zoom_response.content
    logger.info("Downloaded %d bytes from Zoom, uploading to Bunny...", len(video_data))

    resp = requests.put(
        upload_url,
        headers={
            "AccessKey": library_api_key,
            "Content-Type": "application/octet-stream",
        },
        data=video_data,
        timeout=3600,
    )
    resp.raise_for_status()
    logger.info("Uploaded video %s to library %s", video_guid, library_id)
    return resp.json()
