"""Manual upload portal for tutors.

Provides a simple web UI to upload videos directly to Bunny.net libraries,
with PIN authentication, collection management, and renaming.
"""
import hashlib
import time
import logging
import requests
from flask import Blueprint, request, jsonify, render_template_string, session

from config import LIBRARIES, PORTAL_PIN

logger = logging.getLogger(__name__)

portal_bp = Blueprint("portal", __name__)

BUNNY_VIDEO_API = "https://video.bunnycdn.com"


def _require_auth():
    return session.get("authed") is True


def _get_library(key):
    lib = LIBRARIES.get(key)
    if not lib or not lib["api_key"]:
        return None
    return lib


@portal_bp.route("/")
def index():
    return render_template_string(PORTAL_HTML)


@portal_bp.route("/api/auth", methods=["POST"])
def auth():
    pin = (request.json or {}).get("pin", "")
    if pin == PORTAL_PIN:
        session["authed"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Invalid PIN"}), 401


@portal_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@portal_bp.route("/api/libraries")
def libraries():
    if not _require_auth():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify([
        {"key": k, "name": v["name"], "id": v["library_id"]}
        for k, v in LIBRARIES.items()
        if v["api_key"]
    ])


@portal_bp.route("/api/libraries/<lib_key>/collections")
def list_collections(lib_key):
    if not _require_auth():
        return jsonify({"error": "unauthorized"}), 401
    lib = _get_library(lib_key)
    if not lib:
        return jsonify({"error": "unknown library"}), 404
    resp = requests.get(
        f"{BUNNY_VIDEO_API}/library/{lib['library_id']}/collections",
        headers={"AccessKey": lib["api_key"]},
        params={"page": 1, "itemsPerPage": 100, "orderBy": "date"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return jsonify([
        {"guid": c["guid"], "name": c["name"]}
        for c in data.get("items", [])
    ])


@portal_bp.route("/api/libraries/<lib_key>/collections", methods=["POST"])
def create_collection(lib_key):
    if not _require_auth():
        return jsonify({"error": "unauthorized"}), 401
    lib = _get_library(lib_key)
    if not lib:
        return jsonify({"error": "unknown library"}), 404
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    resp = requests.post(
        f"{BUNNY_VIDEO_API}/library/{lib['library_id']}/collections",
        headers={"AccessKey": lib["api_key"]},
        json={"name": name},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return jsonify({"guid": data["guid"], "name": data["name"]})


@portal_bp.route("/api/libraries/<lib_key>/videos", methods=["POST"])
def create_video(lib_key):
    """Create a video entry and return TUS upload credentials for direct browser upload."""
    if not _require_auth():
        return jsonify({"error": "unauthorized"}), 401
    lib = _get_library(lib_key)
    if not lib:
        return jsonify({"error": "unknown library"}), 404
    body = request.json or {}
    title = body.get("title", "").strip()
    collection_id = body.get("collection_id") or None
    if not title:
        return jsonify({"error": "title required"}), 400

    payload = {"title": title}
    if collection_id:
        payload["collectionId"] = collection_id

    resp = requests.post(
        f"{BUNNY_VIDEO_API}/library/{lib['library_id']}/videos",
        headers={"AccessKey": lib["api_key"]},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    video = resp.json()
    video_id = video["guid"]

    # Generate TUS authorization signature
    # Signature = sha256(libraryId + apiKey + expires + videoId)
    expires = int(time.time()) + 86400  # 24 hour expiry for large uploads
    sig_input = f"{lib['library_id']}{lib['api_key']}{expires}{video_id}"
    signature = hashlib.sha256(sig_input.encode("utf-8")).hexdigest()

    return jsonify({
        "video_id": video_id,
        "library_id": lib["library_id"],
        "signature": signature,
        "expires": expires,
    })


PORTAL_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mr Khemistry – Upload Portal</title>
<script src="https://cdn.jsdelivr.net/npm/tus-js-client@4.1.0/dist/tus.min.js"></script>
<style>
  :root { --primary: #f59e0b; --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --muted: #94a3b8; --border: #334155; --success: #10b981; --error: #ef4444; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
  .card { background: var(--card); border-radius: 12px; padding: 32px; max-width: 560px; width: 100%; box-shadow: 0 10px 40px rgba(0,0,0,.3); }
  h1 { margin: 0 0 4px; font-size: 24px; }
  .subtitle { color: var(--muted); font-size: 14px; margin-bottom: 24px; }
  label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; margin-top: 16px; }
  input, select { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 10px 12px; border-radius: 6px; font-size: 14px; }
  input:focus, select:focus { outline: none; border-color: var(--primary); }
  button { background: var(--primary); color: #0f172a; border: none; padding: 12px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; width: 100%; margin-top: 24px; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  button.secondary { background: transparent; color: var(--muted); border: 1px solid var(--border); margin-top: 8px; }
  .row { display: flex; gap: 8px; }
  .row input, .row select { flex: 1; }
  .row button { width: auto; margin: 0; padding: 10px 16px; font-size: 13px; }
  .progress { margin-top: 20px; background: var(--bg); border-radius: 6px; height: 8px; overflow: hidden; display: none; }
  .progress.active { display: block; }
  .progress-bar { background: var(--primary); height: 100%; transition: width .2s; width: 0; }
  .status { margin-top: 12px; font-size: 13px; color: var(--muted); text-align: center; }
  .status.success { color: var(--success); }
  .status.error { color: var(--error); }
  .hidden { display: none !important; }
  .logout { background: none; border: none; color: var(--muted); font-size: 12px; cursor: pointer; width: auto; margin: 0; padding: 0; float: right; }
</style>
</head>
<body>

<div class="card">

  <!-- Login -->
  <div id="login">
    <h1>Upload Portal</h1>
    <div class="subtitle">Enter the PIN to continue</div>
    <label>PIN</label>
    <input type="password" id="pin" inputmode="numeric" autocomplete="off" />
    <button id="loginBtn">Continue</button>
    <div class="status" id="loginStatus"></div>
  </div>

  <!-- Upload -->
  <div id="uploader" class="hidden">
    <button class="logout" id="logoutBtn">Sign out</button>
    <h1>Upload Recording</h1>
    <div class="subtitle">Upload to a 2026 Bunny.net library</div>

    <label>Library</label>
    <select id="library"></select>

    <label>Collection</label>
    <div class="row">
      <select id="collection"></select>
      <button class="secondary" id="newCollBtn" style="margin: 0; padding: 10px 14px;">+ New</button>
    </div>
    <div id="newCollRow" class="row hidden" style="margin-top: 8px;">
      <input type="text" id="newCollName" placeholder="Collection name" />
      <button class="secondary" id="createCollBtn" style="margin: 0;">Create</button>
    </div>

    <label>Video Title</label>
    <input type="text" id="title" placeholder="e.g. 27 - Tutorial SQ 1 - 5bii" />

    <label>File</label>
    <input type="file" id="file" accept="video/*" />

    <button id="uploadBtn">Upload</button>

    <div class="progress" id="progress"><div class="progress-bar" id="progressBar"></div></div>
    <div class="status" id="status"></div>
  </div>

</div>

<script>
const $ = id => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  if (!res.ok) throw new Error((await res.json()).error || res.statusText);
  return res.json();
}

$("loginBtn").onclick = async () => {
  const pin = $("pin").value.trim();
  $("loginStatus").textContent = "";
  try {
    await api("/api/auth", { method: "POST", body: { pin } });
    $("login").classList.add("hidden");
    $("uploader").classList.remove("hidden");
    loadLibraries();
  } catch (e) {
    $("loginStatus").textContent = e.message;
    $("loginStatus").className = "status error";
  }
};

$("pin").addEventListener("keydown", e => { if (e.key === "Enter") $("loginBtn").click(); });

$("logoutBtn").onclick = async () => {
  await api("/api/logout", { method: "POST" });
  $("uploader").classList.add("hidden");
  $("login").classList.remove("hidden");
  $("pin").value = "";
};

async function loadLibraries() {
  const libs = await api("/api/libraries");
  $("library").innerHTML = libs.map(l => `<option value="${l.key}">${l.name}</option>`).join("");
  loadCollections();
}

$("library").onchange = loadCollections;

async function loadCollections() {
  const key = $("library").value;
  $("collection").innerHTML = `<option value="">(none)</option>`;
  try {
    const cols = await api(`/api/libraries/${key}/collections`);
    cols.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.guid;
      opt.textContent = c.name;
      $("collection").appendChild(opt);
    });
  } catch (e) { console.error(e); }
}

$("newCollBtn").onclick = () => $("newCollRow").classList.toggle("hidden");

$("createCollBtn").onclick = async () => {
  const name = $("newCollName").value.trim();
  if (!name) return;
  const key = $("library").value;
  try {
    const col = await api(`/api/libraries/${key}/collections`, { method: "POST", body: { name } });
    const opt = document.createElement("option");
    opt.value = col.guid;
    opt.textContent = col.name;
    opt.selected = true;
    $("collection").appendChild(opt);
    $("newCollName").value = "";
    $("newCollRow").classList.add("hidden");
  } catch (e) { alert(e.message); }
};

$("uploadBtn").onclick = async () => {
  const key = $("library").value;
  const title = $("title").value.trim();
  const collectionId = $("collection").value;
  const file = $("file").files[0];

  if (!title) return alert("Enter a title");
  if (!file) return alert("Choose a file");

  $("uploadBtn").disabled = true;
  $("status").textContent = "Creating video...";
  $("status").className = "status";
  $("progress").classList.add("active");
  $("progressBar").style.width = "0%";

  try {
    const body = { title };
    if (collectionId) body.collection_id = collectionId;
    const { video_id, library_id, signature, expires } = await api(
      `/api/libraries/${key}/videos`, { method: "POST", body }
    );

    const upload = new tus.Upload(file, {
      endpoint: "https://video.bunnycdn.com/tusupload",
      retryDelays: [0, 3000, 5000, 10000, 20000, 60000],
      headers: {
        AuthorizationSignature: signature,
        AuthorizationExpire: expires,
        VideoId: video_id,
        LibraryId: library_id,
      },
      metadata: { filetype: file.type, title },
      onError: err => {
        $("status").textContent = "Upload failed: " + err.message;
        $("status").className = "status error";
        $("uploadBtn").disabled = false;
      },
      onProgress: (sent, total) => {
        const pct = ((sent / total) * 100).toFixed(1);
        $("progressBar").style.width = pct + "%";
        $("status").textContent = `Uploading ${pct}% (${(sent/1e6).toFixed(1)} / ${(total/1e6).toFixed(1)} MB)`;
      },
      onSuccess: () => {
        $("status").textContent = "Uploaded successfully! Processing on Bunny.net…";
        $("status").className = "status success";
        $("progressBar").style.width = "100%";
        $("uploadBtn").disabled = false;
        $("title").value = "";
        $("file").value = "";
      },
    });
    upload.start();
  } catch (e) {
    $("status").textContent = e.message;
    $("status").className = "status error";
    $("uploadBtn").disabled = false;
  }
};
</script>

</body>
</html>
"""
