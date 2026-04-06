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


def download_recording(download_url):
    """Download a recording file from Zoom, returning the response for streaming.

    Returns a requests.Response with stream=True so the caller can iterate chunks.
    """
    token = get_access_token()
    resp = requests.get(
        download_url,
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=600,
    )
    resp.raise_for_status()
    return resp
