import hashlib
import hmac
import logging
import os
import tempfile
import threading

from flask import Flask, request, jsonify

from config import ZOOM_WEBHOOK_SECRET_TOKEN, LIBRARY_MAP
from zoom_client import download_recording_to_file
from bunny_client import create_video, upload_video_from_file
from gdrive_client import upload_file_to_drive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-change-me")


def match_library(topic):
    """Match a Zoom meeting topic to a Bunny.net library using keywords."""
    topic_upper = topic.upper()
    for keyword, lib_info in LIBRARY_MAP.items():
        if keyword.upper() in topic_upper:
            return keyword, lib_info
    return None, None


def process_recording(topic, recording_files, download_token):
    """Download recording from Zoom and upload to Bunny.net (runs in background thread)."""
    keyword, lib_info = match_library(topic)
    if not lib_info:
        logger.warning("No library match for topic: %s", topic)
        return

    logger.info("Matched topic '%s' to library '%s' (keyword: %s)", topic, lib_info["name"], keyword)

    # Filter for MP4 files only
    mp4_files = [f for f in recording_files if f.get("file_type") == "MP4" and f.get("status") == "completed"]

    if not mp4_files:
        logger.warning("No completed MP4 files found for topic: %s", topic)
        return

    for rec_file in mp4_files:
        download_url = rec_file["download_url"]
        file_type = rec_file.get("recording_type", "unknown")
        title = f"{topic} - {file_type}"

        logger.info("Processing: %s", title)

        # Buffer the Zoom download to disk (not RAM) so memory stays flat
        # regardless of video size. /tmp is ephemeral on Render — fine for our
        # use since we delete after upload anyway.
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            size = download_recording_to_file(download_url, download_token, tmp_path)
            logger.info("Downloaded %d bytes from Zoom to %s", size, tmp_path)

            video_guid = create_video(lib_info["library_id"], lib_info["api_key"], title)
            upload_video_from_file(lib_info["library_id"], lib_info["api_key"], video_guid, tmp_path)

            logger.info("Successfully uploaded to Bunny: %s", title)

            try:
                drive_filename = f"{title}.mp4"
                upload_file_to_drive(drive_filename, tmp_path)
            except Exception:
                logger.exception("Google Drive backup failed (non-fatal): %s", title)

        except Exception:
            logger.exception("Failed to process recording: %s", title)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle Zoom webhook events."""
    body = request.get_json(force=True)
    event = body.get("event", "")

    # Handle Zoom CRC (Challenge-Response Check) URL validation
    if event == "endpoint.url_validation":
        plain_token = body["payload"]["plainToken"]
        hash_token = hmac.new(
            ZOOM_WEBHOOK_SECRET_TOKEN.encode("utf-8"),
            plain_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return jsonify({"plainToken": plain_token, "encryptedToken": hash_token})

    # Handle recording completed event
    if event == "recording.completed":
        payload = body.get("payload", {})
        download_token = body.get("download_token", "")
        topic = payload.get("object", {}).get("topic", "")
        recording_files = payload.get("object", {}).get("recording_files", [])

        logger.info("Recording completed: %s (%d files)", topic, len(recording_files))

        # Process in background so we respond to Zoom quickly
        thread = threading.Thread(
            target=process_recording,
            args=(topic, recording_files, download_token),
            daemon=True,
        )
        thread.start()

        return jsonify({"status": "processing"}), 200

    logger.info("Ignoring event: %s", event)
    return jsonify({"status": "ignored"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
