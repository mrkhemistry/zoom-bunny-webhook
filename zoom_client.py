import requests
from config import ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET

_token_cache = {"access_token": None, "expires_at": 0}


def get_access_token():
    """Get a Zoom Server-to-Server OAuth access token."""
    import time

    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    resp = requests.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID},
        auth=(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data["expires_in"]

    return data["access_token"]


def download_recording_to_file(download_url, download_token, file_path):
    """Stream a recording from Zoom to disk. Returns size in bytes.

    Uses the webhook's `download_token` (not the OAuth access token).
    Streams in 8 MiB chunks so memory usage stays flat regardless of
    video size — important for hosts with low RAM ceilings.
    """
    with requests.get(
        download_url,
        headers={"Authorization": f"Bearer {download_token}"},
        stream=True,
        timeout=600,
    ) as resp:
        resp.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
    import os
    return os.path.getsize(file_path)
