import os

# Zoom Server-to-Server OAuth credentials
ZOOM_ACCOUNT_ID = os.environ["ZOOM_ACCOUNT_ID"]
ZOOM_CLIENT_ID = os.environ["ZOOM_CLIENT_ID"]
ZOOM_CLIENT_SECRET = os.environ["ZOOM_CLIENT_SECRET"]
ZOOM_WEBHOOK_SECRET_TOKEN = os.environ["ZOOM_WEBHOOK_SECRET_TOKEN"]

# Bunny.net account API key
BUNNY_API_KEY = os.environ["BUNNY_API_KEY"]

# Keyword -> (library_id, library_api_key) mapping
# Meeting topic containing keyword routes to that library
LIBRARY_MAP = {
    "JC1": {
        "library_id": 631959,
        "api_key": os.environ.get("BUNNY_JC1_API_KEY", ""),
        "name": "AY 2026 H2 JC1 Lesson Recording",
    },
    "JC2": {
        "library_id": 631965,
        "api_key": os.environ.get("BUNNY_JC2_API_KEY", ""),
        "name": "AY 2026 H2 JC2 Lesson Recording",
    },
}
