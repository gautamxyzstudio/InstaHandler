"""
MOZART Insta Handler — Web UI (multi-platform: Instagram + YouTube Shorts)
===========================================================================

Local Flask app. Run:  python3 app.py
Then open:             http://127.0.0.1:5050

Features:
  - Brand groups: each brand bundles 1 Instagram + 1 YouTube account.
    You can also have standalone IG or YT accounts (not linked to a brand).
  - Drag-and-drop bulk video upload per brand/account.
  - One caption input -> auto IG caption + YT title/description/tags.
    Editable separately before posting.
  - Per-video platform toggles (post to IG, YT, or both).
  - Per-video scheduling: post now, or pick a future date/time.
  - Background worker handles the queue safely (one post at a time, throttled).
  - Live status, history log.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory, redirect, session, url_for

from caption_generator import (
    build_post_text, build_youtube_short, build_dual_post,
)
import youtube_uploader as yt


# ---------------- env-based config ----------------

def env(key: str, default: str = "") -> str:
    v = os.environ.get(key, default)
    return v.strip() if isinstance(v, str) else v


# When deployed publicly (Dokploy), set:
#   PUBLIC_BASE_URL=https://mozart.yourdomain.com
#   APP_USERNAME=you
#   APP_PASSWORD=long-random-string
#   FLASK_SECRET_KEY=another-long-random-string
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://127.0.0.1:5050")
APP_USERNAME    = env("APP_USERNAME", "")          # empty = no auth (local-only mode)
APP_PASSWORD    = env("APP_PASSWORD", "")
FLASK_SECRET    = env("FLASK_SECRET_KEY", "dev-only-secret-change-me-for-prod")
DATA_DIR        = env("DATA_DIR", "")              # if set, store config + uploads here (for Docker volumes)


# ---------------- paths & state ----------------

HERE = Path(__file__).parent
DATA_ROOT = Path(DATA_DIR) if DATA_DIR else HERE
CONFIG_PATH = DATA_ROOT / "config.json"
UPLOADS_DIR = DATA_ROOT / "uploads"
POSTED_DIR = DATA_ROOT / "uploads" / "_posted"
FAILED_DIR = DATA_ROOT / "uploads" / "_failed"
LOG_PATH = DATA_ROOT / "output" / "post_log.json"

for d in (UPLOADS_DIR, POSTED_DIR, FAILED_DIR, LOG_PATH.parent):
    d.mkdir(parents=True, exist_ok=True)

JOBS: Dict[str, dict] = {}
JOB_QUEUE: "Queue[str]" = Queue()
LOCK = threading.Lock()

GRAPH = "https://graph.facebook.com/v21.0"

# OAuth state holder (single user, single app, no DB needed)
OAUTH_PENDING: Dict[str, dict] = {}  # state -> { brand_id, client_id, client_secret }


# ---------------- config helpers ----------------

DEFAULT_CONFIG = {
    "brands": [],   # [{id, name, niche, caption_style, default_cta, hashtag_count, ig: {...}, yt: {...}}]
    "settings": {
        "video_host_method": "fileio",
        "min_delay_between_posts_seconds": 60,
    }
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # one-time migration from old "pages" schema
    if "pages" in cfg and "brands" not in cfg:
        brands = []
        for p in cfg.get("pages", []):
            brands.append({
                "id": p.get("id", uuid.uuid4().hex[:8]),
                "name": p.get("name", "Brand"),
                "niche": p.get("niche", "default"),
                "caption_style": p.get("caption_style", "friendly"),
                "default_cta": p.get("default_cta", ""),
                "hashtag_count": p.get("hashtag_count", 25),
                "ig": {
                    "ig_user_id": p.get("ig_user_id", ""),
                    "access_token": p.get("access_token", ""),
                },
                "yt": {"client_id": "", "client_secret": "", "refresh_token": ""},
            })
        cfg = {"brands": brands, "settings": cfg.get("settings", DEFAULT_CONFIG["settings"])}
        save_config(cfg)
    cfg.setdefault("brands", [])
    cfg.setdefault("settings", DEFAULT_CONFIG["settings"])
    return cfg


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_brand(cfg: dict, brand_id: str) -> Optional[dict]:
    return next((b for b in cfg["brands"] if b.get("id") == brand_id), None)


# ---------------- log helpers ----------------

def append_log(entry: dict) -> None:
    log = []
    if LOG_PATH.exists():
        try:
            log = json.loads(LOG_PATH.read_text())
        except Exception:
            log = []
    log.insert(0, entry)
    LOG_PATH.write_text(json.dumps(log[:500], indent=2))


def read_log() -> List[dict]:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text())
        except Exception:
            return []
    return []


# ---------------- video hosting (for Instagram fetch) ----------------

def upload_to_fileio(p: Path) -> Optional[str]:
    try:
        with open(p, "rb") as f:
            r = requests.post("https://file.io", files={"file": f}, timeout=180)
        r.raise_for_status()
        d = r.json()
        return d.get("link") if d.get("success") else None
    except Exception as e:
        print(f"[host] file.io error: {e}")
        return None


def upload_to_catbox(p: Path) -> Optional[str]:
    try:
        with open(p, "rb") as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=180,
            )
        r.raise_for_status()
        url = r.text.strip()
        return url if url.startswith("http") else None
    except Exception as e:
        print(f"[host] catbox error: {e}")
        return None


def host_video(p: Path, method: str) -> Optional[str]:
    primary = upload_to_fileio if method == "fileio" else upload_to_catbox
    fallback = upload_to_catbox if method == "fileio" else upload_to_fileio
    return primary(p) or fallback(p)


# ---------------- Instagram Graph API ----------------

def ig_post_reel(ig_user_id: str, access_token: str, video_url: str, caption: str) -> dict:
    r = requests.post(f"{GRAPH}/{ig_user_id}/media", data={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": access_token,
    }, timeout=60)
    if r.status_code != 200:
        return {"ok": False, "media_id": None, "error": f"container create: {r.text[:300]}"}
    container_id = r.json().get("id")

    deadline = time.time() + 600
    while time.time() < deadline:
        s = requests.get(f"{GRAPH}/{container_id}", params={
            "fields": "status_code", "access_token": access_token,
        }, timeout=30)
        if s.status_code != 200:
            return {"ok": False, "media_id": None, "error": f"status: {s.text[:300]}"}
        code = s.json().get("status_code", "")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            return {"ok": False, "media_id": None, "error": f"container: {code}"}
        time.sleep(8)
    else:
        return {"ok": False, "media_id": None, "error": "timeout waiting for container"}

    p = requests.post(f"{GRAPH}/{ig_user_id}/media_publish", data={
        "creation_id": container_id, "access_token": access_token,
    }, timeout=60)
    if p.status_code != 200:
        return {"ok": False, "media_id": None, "error": f"publish: {p.text[:300]}"}
    return {"ok": True, "media_id": p.json().get("id"), "error": None}


# ---------------- background worker ----------------

def parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def worker_loop():
    """
    Single worker thread. Pops a job, checks if it's due (scheduled_for in the past),
    and either processes it or pushes it back onto the queue after a short sleep.
    """
    while True:
        try:
            job_id = JOB_QUEUE.get(timeout=1)
        except Empty:
            continue

        try:
            with LOCK:
                job = JOBS.get(job_id)
            if not job:
                JOB_QUEUE.task_done()
                continue

            sched = parse_iso(job.get("scheduled_for") or "")
            if sched and sched > datetime.now():
                # not due yet — put it back, sleep a bit, continue
                JOB_QUEUE.task_done()
                time.sleep(5)
                JOB_QUEUE.put(job_id)
                continue

            process_job(job_id)
        except Exception as e:
            with LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "failed"
                    JOBS[job_id]["error"] = f"worker crash: {e}"
        finally:
            try:
                JOB_QUEUE.task_done()
            except ValueError:
                pass


def process_job(job_id: str) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["status"] = "uploading"
        job["started_at"] = datetime.now().isoformat(timespec="seconds")

    cfg = load_config()
    brand = get_brand(cfg, job["brand_id"])
    if not brand:
        with LOCK:
            job["status"] = "failed"
            job["error"] = "brand not found in config"
        return

    video_path = UPLOADS_DIR / job["file"]
    if not video_path.exists():
        with LOCK:
            job["status"] = "failed"
            job["error"] = "video file missing"
        return

    platforms = job.get("platforms", ["ig"])
    ig_result = None
    yt_result = None
    method = cfg.get("settings", {}).get("video_host_method", "fileio")

    # ----- INSTAGRAM -----
    if "ig" in platforms and brand.get("ig", {}).get("ig_user_id"):
        with LOCK:
            job["status"] = "publishing"
            job["platform_status"] = job.get("platform_status", {})
            job["platform_status"]["ig"] = "uploading"

        public_url = host_video(video_path, method)
        if not public_url:
            ig_result = {"ok": False, "error": "all hosts failed"}
        else:
            with LOCK:
                job["platform_status"]["ig"] = "publishing"
                job["public_url"] = public_url
            ig_result = ig_post_reel(
                brand["ig"]["ig_user_id"],
                brand["ig"]["access_token"],
                public_url,
                job["ig_caption"],
            )
        with LOCK:
            job["ig_result"] = ig_result
            job["platform_status"]["ig"] = "posted" if ig_result.get("ok") else "failed"

    # ----- YOUTUBE -----
    if "yt" in platforms and brand.get("yt", {}).get("refresh_token"):
        with LOCK:
            job["status"] = "publishing"
            job["platform_status"] = job.get("platform_status", {})
            job["platform_status"]["yt"] = "uploading"

        yt_result = yt.upload_short(
            client_id=brand["yt"]["client_id"],
            client_secret=brand["yt"]["client_secret"],
            refresh_token=brand["yt"]["refresh_token"],
            video_path=str(video_path),
            title=job["yt_title"],
            description=job["yt_description"],
            tags=job.get("yt_tags", []),
        )
        with LOCK:
            job["yt_result"] = yt_result
            job["platform_status"]["yt"] = "posted" if yt_result.get("ok") else "failed"

    # ----- final status -----
    with LOCK:
        results = [r for r in (ig_result, yt_result) if r is not None]
        any_ok = any(r.get("ok") for r in results)
        all_ok = results and all(r.get("ok") for r in results)
        job["finished_at"] = datetime.now().isoformat(timespec="seconds")
        if all_ok:
            job["status"] = "posted"
        elif any_ok:
            job["status"] = "partial"
        else:
            job["status"] = "failed"
            errs = [r.get("error") for r in results if r and not r.get("ok")]
            job["error"] = "; ".join([e for e in errs if e])

        append_log({
            "timestamp": job["finished_at"],
            "brand": brand["name"],
            "brand_id": brand["id"],
            "file": job["file"],
            "platforms": platforms,
            "ig_status": (ig_result or {}).get("ok"),
            "ig_media_id": (ig_result or {}).get("media_id"),
            "yt_status": (yt_result or {}).get("ok"),
            "yt_video_id": (yt_result or {}).get("video_id"),
            "yt_url": (yt_result or {}).get("url"),
            "status": job["status"],
            "error": job.get("error"),
            "caption_preview": job.get("ig_caption", "")[:120].replace("\n", " "),
        })

    # move file
    if job["status"] in ("posted", "partial"):
        _move(video_path, POSTED_DIR)
    else:
        _move(video_path, FAILED_DIR)

    delay = cfg.get("settings", {}).get("min_delay_between_posts_seconds", 60)
    time.sleep(max(0, int(delay)))


def _move(p: Path, dest_dir: Path) -> None:
    try:
        shutil.move(str(p), str(dest_dir / p.name))
    except Exception:
        pass


# ---------------- Flask app ----------------

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB per upload batch
app.secret_key = FLASK_SECRET


# ---------------- auth middleware ----------------

# Routes that do not require auth.
AUTH_EXEMPT = {"login", "do_login", "healthz", "static"}


@app.before_request
def _require_login():
    """If APP_USERNAME + APP_PASSWORD are set, gate every route behind a session login."""
    if not APP_USERNAME or not APP_PASSWORD:
        return  # no auth configured = open (local-only mode)
    # allow the OAuth callback through (Google needs to hit it directly)
    if request.path.startswith("/oauth/youtube/callback"):
        return
    endpoint = request.endpoint or ""
    if endpoint in AUTH_EXEMPT:
        return
    if session.get("authed"):
        return
    return redirect(url_for("login", next=request.path))


LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Sign in — MOZART</title>
<style>
  body{margin:0;background:#0f1115;color:#e6e9ef;font-family:-apple-system,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh;}
  .card{background:#161a22;border:1px solid #2a3142;border-radius:12px;padding:32px;
        width:320px;text-align:center;}
  .logo{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;
        border-radius:10px;background:linear-gradient(135deg,#ff3d7f,#ffa14b);color:#fff;font-size:18px;margin-bottom:12px;}
  h1{font-size:18px;font-weight:600;margin:4px 0 18px;}
  input{display:block;width:100%;padding:10px 12px;margin-bottom:10px;background:#0f1115;
        border:1px solid #2a3142;border-radius:8px;color:#e6e9ef;font-size:14px;}
  button{width:100%;padding:10px;background:linear-gradient(135deg,#ff3d7f,#ffa14b);
         color:#fff;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-size:14px;}
  .err{color:#ff5c5c;font-size:12px;margin-bottom:8px;}
  .muted{color:#8a93a6;font-size:11px;margin-top:14px;}
</style></head>
<body><form class="card" method="POST" action="/login">
  <div class="logo">▶</div>
  <h1>MOZART Multi-Platform Handler</h1>
  {error}
  <input type="text"     name="username" placeholder="Username" required autofocus />
  <input type="password" name="password" placeholder="Password" required />
  <input type="hidden"   name="next" value="{next}" />
  <button type="submit">Sign in</button>
  <div class="muted">This server is private. Unauthorized access is not allowed.</div>
</form></body></html>"""


@app.route("/login", methods=["GET"])
def login():
    return LOGIN_HTML.format(error="", next=request.args.get("next", "/"))


@app.route("/login", methods=["POST"])
def do_login():
    u = request.form.get("username", "")
    p = request.form.get("password", "")
    nxt = request.form.get("next") or "/"
    if u == APP_USERNAME and p == APP_PASSWORD:
        session["authed"] = True
        session.permanent = True
        return redirect(nxt if nxt.startswith("/") else "/")
    return LOGIN_HTML.format(
        error='<div class="err">Wrong username or password.</div>',
        next=nxt,
    ), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/")
def index():
    return render_template("index.html")


# ----- config / brands -----

@app.route("/api/config", methods=["GET"])
def api_get_config():
    cfg = load_config()
    safe = json.loads(json.dumps(cfg))
    for b in safe.get("brands", []):
        ig = b.get("ig", {}) or {}
        yt_ = b.get("yt", {}) or {}
        ig_tok = ig.get("access_token", "") or ""
        yt_rt = yt_.get("refresh_token", "") or ""
        yt_cs = yt_.get("client_secret", "") or ""
        b["ig_token_preview"] = f"...{ig_tok[-6:]}" if ig_tok else ""
        b["yt_connected"] = bool(yt_rt and yt_.get("client_id"))
        b["yt_client_secret_preview"] = f"...{yt_cs[-6:]}" if yt_cs else ""
        # blank actual secrets in the response
        if "ig" in b:
            b["ig"]["access_token"] = ""
        if "yt" in b:
            b["yt"]["client_secret"] = ""
            b["yt"]["refresh_token"] = ""
    return jsonify(safe)


@app.route("/api/brands", methods=["POST"])
def api_save_brand():
    data = request.get_json(force=True)
    cfg = load_config()
    brand_id = data.get("id") or uuid.uuid4().hex[:8]

    new = {
        "id": brand_id,
        "name": data.get("name", "Brand"),
        "niche": data.get("niche", "default"),
        "caption_style": data.get("caption_style", "friendly"),
        "default_cta": data.get("default_cta", ""),
        "hashtag_count": int(data.get("hashtag_count", 25)),
        "ig": {
            "ig_user_id": (data.get("ig") or {}).get("ig_user_id", "").strip(),
            "access_token": (data.get("ig") or {}).get("access_token", "").strip(),
        },
        "yt": {
            "client_id": (data.get("yt") or {}).get("client_id", "").strip(),
            "client_secret": (data.get("yt") or {}).get("client_secret", "").strip(),
            "refresh_token": (data.get("yt") or {}).get("refresh_token", "").strip(),
        },
    }

    # preserve existing secrets if the form left them blank
    existing = get_brand(cfg, brand_id)
    if existing:
        if not new["ig"]["access_token"]:
            new["ig"]["access_token"] = existing.get("ig", {}).get("access_token", "")
        if not new["yt"]["client_secret"]:
            new["yt"]["client_secret"] = existing.get("yt", {}).get("client_secret", "")
        if not new["yt"]["refresh_token"]:
            new["yt"]["refresh_token"] = existing.get("yt", {}).get("refresh_token", "")
        cfg["brands"][cfg["brands"].index(existing)] = new
    else:
        cfg["brands"].append(new)

    save_config(cfg)
    return jsonify({"ok": True, "id": brand_id})


@app.route("/api/brands/<brand_id>", methods=["DELETE"])
def api_delete_brand(brand_id):
    cfg = load_config()
    cfg["brands"] = [b for b in cfg["brands"] if b.get("id") != brand_id]
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/brands/<brand_id>/disconnect_yt", methods=["POST"])
def api_disconnect_yt(brand_id):
    cfg = load_config()
    b = get_brand(cfg, brand_id)
    if b:
        b["yt"] = {"client_id": "", "client_secret": "", "refresh_token": ""}
        save_config(cfg)
    return jsonify({"ok": True})


# ----- YouTube OAuth flow -----

@app.route("/oauth/youtube/start")
def oauth_yt_start():
    brand_id = request.args.get("brand_id")
    client_id = request.args.get("client_id", "").strip()
    client_secret = request.args.get("client_secret", "").strip()
    if not brand_id or not client_id or not client_secret:
        return "Missing brand_id, client_id, or client_secret", 400

    state = uuid.uuid4().hex
    redirect_uri = PUBLIC_BASE_URL.rstrip("/") + "/oauth/youtube/callback"
    OAUTH_PENDING[state] = {
        "brand_id": brand_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    url = yt.build_oauth_authorize_url(client_id, redirect_uri, state)
    return redirect(url)


@app.route("/oauth/youtube/callback")
def oauth_yt_callback():
    state = request.args.get("state")
    code = request.args.get("code")
    err = request.args.get("error")
    if err:
        return f"<h2>Google returned an error: {err}</h2><p>You can close this window.</p>", 400
    if not state or state not in OAUTH_PENDING:
        return "<h2>OAuth state mismatch.</h2>", 400
    pending = OAUTH_PENDING.pop(state)

    result = yt.exchange_code_for_refresh_token(
        client_id=pending["client_id"],
        client_secret=pending["client_secret"],
        code=code,
        redirect_uri=pending["redirect_uri"],
    )
    if not result.get("ok"):
        return f"<h2>OAuth exchange failed</h2><pre>{result.get('error')}</pre>", 400

    # store on brand
    cfg = load_config()
    b = get_brand(cfg, pending["brand_id"])
    if not b:
        return "<h2>Brand no longer exists.</h2>", 400
    b["yt"] = {
        "client_id": pending["client_id"],
        "client_secret": pending["client_secret"],
        "refresh_token": result["refresh_token"],
    }
    save_config(cfg)

    return """
      <!doctype html><meta charset="utf-8">
      <body style="font-family:-apple-system,sans-serif;background:#0f1115;color:#e6e9ef;
                   display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;">
        <div>
          <h2 style="color:#2ecc71">YouTube connected ✓</h2>
          <p>You can close this tab and return to the app.</p>
          <script>setTimeout(()=>window.close(), 1500);</script>
        </div>
      </body>
    """


# ----- upload + queue -----

ALLOWED = {".mp4", ".mov", ".m4v"}


@app.route("/api/upload", methods=["POST"])
def api_upload():
    brand_id = request.form.get("brand_id")
    cfg = load_config()
    brand = get_brand(cfg, brand_id)
    if not brand:
        return jsonify({"ok": False, "error": "brand not found"}), 400

    saved = []
    for f in request.files.getlist("videos"):
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED:
            continue
        unique = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
        dest = UPLOADS_DIR / unique
        f.save(dest)

        dual = build_dual_post(
            filename=f.filename,
            niche=brand.get("niche", "default"),
            caption_style=brand.get("caption_style", "friendly"),
            cta=brand.get("default_cta", ""),
            ig_hashtag_count=brand.get("hashtag_count", 25),
            yt_hashtag_count=15,
        )

        # default platforms = whichever the brand has connected
        platforms = []
        if (brand.get("ig") or {}).get("ig_user_id"):
            platforms.append("ig")
        if (brand.get("yt") or {}).get("refresh_token"):
            platforms.append("yt")
        if not platforms:
            platforms = ["ig"]  # let user know in UI

        job_id = uuid.uuid4().hex[:10]
        with LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "brand_id": brand_id,
                "brand_name": brand["name"],
                "file": unique,
                "original_name": f.filename,
                "ig_caption": dual["instagram"]["caption"],
                "yt_title": dual["youtube"]["title"],
                "yt_description": dual["youtube"]["description"],
                "yt_tags": dual["youtube"]["tags"],
                "platforms": platforms,
                "scheduled_for": None,
                "status": "draft",
                "platform_status": {},
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        saved.append({"id": job_id, "file": unique})

    return jsonify({"ok": True, "jobs": saved})


@app.route("/api/jobs/<job_id>", methods=["PATCH"])
def api_update_job(job_id):
    data = request.get_json(force=True)
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "job not found"}), 404
        if job["status"] not in ("draft", "failed"):
            return jsonify({"ok": False, "error": "cannot edit now"}), 400
        for key in ("ig_caption", "yt_title", "yt_description"):
            if key in data:
                job[key] = data[key]
        if "yt_tags" in data and isinstance(data["yt_tags"], list):
            job["yt_tags"] = data["yt_tags"]
        if "platforms" in data and isinstance(data["platforms"], list):
            job["platforms"] = [p for p in data["platforms"] if p in ("ig", "yt")]
        if "scheduled_for" in data:
            job["scheduled_for"] = data["scheduled_for"] or None
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/queue", methods=["POST"])
def api_queue_job(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "job not found"}), 404
        if job["status"] not in ("draft", "failed"):
            return jsonify({"ok": False, "error": "already in flight"}), 400
        job["status"] = "scheduled" if job.get("scheduled_for") else "queued"
    JOB_QUEUE.put(job_id)
    return jsonify({"ok": True})


@app.route("/api/jobs/queue_all", methods=["POST"])
def api_queue_all():
    brand_id = request.get_json(force=True).get("brand_id")
    queued = 0
    with LOCK:
        for jid, job in JOBS.items():
            if job["status"] == "draft" and (not brand_id or job["brand_id"] == brand_id):
                job["status"] = "scheduled" if job.get("scheduled_for") else "queued"
                JOB_QUEUE.put(jid)
                queued += 1
    return jsonify({"ok": True, "queued": queued})


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def api_delete_job(job_id):
    with LOCK:
        job = JOBS.pop(job_id, None)
    if job and job["status"] in ("draft", "failed"):
        try:
            (UPLOADS_DIR / job["file"]).unlink(missing_ok=True)
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/jobs", methods=["GET"])
def api_list_jobs():
    brand_id = request.args.get("brand_id")
    with LOCK:
        out = []
        for jid, job in JOBS.items():
            if brand_id and job["brand_id"] != brand_id:
                continue
            out.append(job)
    out.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jsonify({"jobs": out})


@app.route("/api/log", methods=["GET"])
def api_log():
    return jsonify({"log": read_log()})


@app.route("/api/regenerate_caption", methods=["POST"])
def api_regen_caption():
    data = request.get_json(force=True)
    cfg = load_config()
    b = get_brand(cfg, data.get("brand_id"))
    if not b:
        return jsonify({"ok": False, "error": "brand not found"}), 400
    dual = build_dual_post(
        filename=data.get("filename", "video.mp4"),
        niche=b.get("niche", "default"),
        caption_style=b.get("caption_style", "friendly"),
        cta=b.get("default_cta", ""),
        ig_hashtag_count=b.get("hashtag_count", 25),
        yt_hashtag_count=15,
    )
    return jsonify({"ok": True, **dual})


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOADS_DIR, filename)


# ---------------- launch ----------------

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5050")


# Start the background worker as soon as this module is imported (works under
# both `python app.py` and `gunicorn app:app`). Guard against double-start when
# Flask reloader spawns a child.
_WORKER_STARTED = False

def _ensure_worker():
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    _WORKER_STARTED = True
    threading.Thread(target=worker_loop, daemon=True).start()


_ensure_worker()


if __name__ == "__main__":
    # Local dev: open the browser, bind to localhost.
    if not os.environ.get("NO_OPEN_BROWSER"):
        threading.Thread(target=open_browser, daemon=True).start()
    host = env("HOST", "127.0.0.1")
    port = int(env("PORT", "5050"))
    print(f"\n  MOZART Insta+YT Handler — open http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False, use_reloader=False)
