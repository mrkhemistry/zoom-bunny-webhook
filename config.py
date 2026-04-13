import os

# Zoom Server-to-Server OAuth credentials
ZOOM_ACCOUNT_ID = os.environ["ZOOM_ACCOUNT_ID"]
ZOOM_CLIENT_ID = os.environ["ZOOM_CLIENT_ID"]
ZOOM_CLIENT_SECRET = os.environ["ZOOM_CLIENT_SECRET"]
ZOOM_WEBHOOK_SECRET_TOKEN = os.environ["ZOOM_WEBHOOK_SECRET_TOKEN"]

# Bunny.net account API key
BUNNY_API_KEY = os.environ["BUNNY_API_KEY"]

# Manual upload portal PIN
PORTAL_PIN = os.environ.get("PORTAL_PIN", "1633")

# All 2026 libraries available in the manual upload portal
LIBRARIES = {
    "JC1": {
        "library_id": 631959,
        "api_key": os.environ.get("BUNNY_JC1_API_KEY", ""),
        "name": "AY 2026 H2 JC1 Lesson Recording",
        "portal": False,  # auto-uploaded via Zoom webhook
    },
    "JC2": {
        "library_id": 631965,
        "api_key": os.environ.get("BUNNY_JC2_API_KEY", ""),
        "name": "AY 2026 H2 JC2 Lesson Recording",
        "portal": False,  # auto-uploaded via Zoom webhook
    },
    "SEC3": {
        "library_id": 636447,
        "api_key": os.environ.get("BUNNY_SEC3_API_KEY", ""),
        "name": "AY 2026 Sec 3 Pure Chemistry Recordings",
        "portal": True,
    },
    "SEC4": {
        "library_id": 636448,
        "api_key": os.environ.get("BUNNY_SEC4_API_KEY", ""),
        "name": "AY 2026 Sec 4 Combined Chemistry Recordings",
        "portal": True,
    },
}

# Keyword -> library mapping for Zoom webhook routing
# Meeting topic containing keyword routes to that library
LIBRARY_MAP = {
    "JC1": LIBRARIES["JC1"],
    "JC2": LIBRARIES["JC2"],
}
