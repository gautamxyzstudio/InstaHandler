"""
Instagram Reel Auto-Poster
===========================

Watches a folder per Instagram page. When a new video drops in, it:
  1. Auto-generates a caption + trending hashtags based on the page's niche.
  2. Uploads the video to a temporary public host (so Instagram can fetch it).
  3. Creates a Reel container via the Instagram Graph API.
  4. Publishes the Reel.
  5. Logs the post to output/post_log.csv and moves the file to videos/<page>/posted/.

Requirements:
  - Instagram Business or Creator account
  - Connected to a Facebook Page
  - Meta for Developers app with `instagram_content_publish` permission
  - Long-lived access token for each page
  - Instagram Business Account ID for each page

Run:
  pip install -r requirements.txt
  cp config.example.json config.json   # fill in tokens
  python insta_agent.py

Stop:
  Ctrl+C
"""

import csv
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from caption_generator import build_post_text


# ---------------- video hosting ----------------

def upload_to_fileio(video_path: Path) -> Optional[str]:
    """
    Upload to file.io — free, no signup, link expires after one download or 14 days.
    Instagram fetches the video once, so single-download is fine.
    Returns a public URL or None on failure.
    """
    try:
        with open(video_path, "rb") as f:
            r = requests.post("https://file.io", files={"file": f}, timeout=120)
        r.raise_for_status()
        data = r.json()
        if data.get("success") and data.get("link"):
            return data["link"]
        print(f"  [host] file.io rejected: {data}")
    except Exception as e:
        print(f"  [host] file.io error: {e}")
    return None


def upload_to_catbox(video_path: Path) -> Optional[str]:
    """
    Upload to catbox.moe — free, anonymous, links don't expire.
    Good fallback if file.io is being weird.
    """
    try:
        with open(video_path, "rb") as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=180,
            )
        r.raise_for_status()
        url = r.text.strip()
        if url.startswith("http"):
            return url
        print(f"  [host] catbox rejected: {url}")
    except Exception as e:
        print(f"  [host] catbox error: {e}")
    return None


def host_video(video_path: Path, method: str = "fileio") -> Optional[str]:
    """Try the configured host first, then fall back to the other one."""
    primary = upload_to_fileio if method == "fileio" else upload_to_catbox
    fallback = upload_to_catbox if method == "fileio" else upload_to_fileio
    return primary(video_path) or fallback(video_path)


# ---------------- Instagram Graph API ----------------

GRAPH = "https://graph.facebook.com/v21.0"


def ig_create_reel_container(ig_user_id: str, video_url: str, caption: str,
                              access_token: str) -> Optional[str]:
    """Step 1: create a REELS media container. Returns container ID."""
    url = f"{GRAPH}/{ig_user_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": access_token,
    }
    r = requests.post(url, data=payload, timeout=60)
    if r.status_code != 200:
        print(f"  [ig] container create failed: {r.status_code} {r.text}")
        return None
    return r.json().get("id")


def ig_wait_for_ready(container_id: str, access_token: str,
                      max_wait_seconds: int = 600) -> bool:
    """Step 2: poll the container until Instagram says FINISHED (or ERROR)."""
    url = f"{GRAPH}/{container_id}"
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        r = requests.get(url, params={"fields": "status_code,status", "access_token": access_token}, timeout=30)
        if r.status_code != 200:
            print(f"  [ig] status check failed: {r.status_code} {r.text}")
            return False
        status_code = r.json().get("status_code", "UNKNOWN")
        if status_code == "FINISHED":
            return True
        if status_code in ("ERROR", "EXPIRED"):
            print(f"  [ig] container failed: {r.json()}")
            return False
        print(f"  [ig] processing... ({status_code})")
        time.sleep(10)
    print("  [ig] timed out waiting for container to finish")
    return False


def ig_publish(ig_user_id: str, container_id: str, access_token: str) -> Optional[str]:
    """Step 3: publish the container. Returns the published media ID."""
    url = f"{GRAPH}/{ig_user_id}/media_publish"
    r = requests.post(url, data={"creation_id": container_id, "access_token": access_token}, timeout=60)
    if r.status_code != 200:
        print(f"  [ig] publish failed: {r.status_code} {r.text}")
        return None
    return r.json().get("id")


def post_reel(ig_user_id: str, access_token: str, video_url: str, caption: str) -> Optional[str]:
    container_id = ig_create_reel_container(ig_user_id, video_url, caption, access_token)
    if not container_id:
        return None
    print(f"  [ig] container created: {container_id}")
    if not ig_wait_for_ready(container_id, access_token):
        return None
    media_id = ig_publish(ig_user_id, container_id, access_token)
    if media_id:
        print(f"  [ig] PUBLISHED: media_id={media_id}")
    return media_id


# ---------------- logging ----------------

def append_log(log_path: Path, row: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)


# ---------------- main loop ----------------

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def find_new_videos(folder: Path) -> list:
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS and not p.name.startswith(".")
    )


def process_one_video(page_cfg: dict, video_path: Path, settings: dict, log_path: Path) -> bool:
    print(f"\n[{page_cfg['name']}] new video: {video_path.name}")

    # 1. caption + hashtags
    caption = build_post_text(
        filename=video_path.name,
        niche=page_cfg.get("niche", "default"),
        caption_style=page_cfg.get("caption_style", "friendly"),
        cta=page_cfg.get("default_cta", ""),
        hashtag_count=page_cfg.get("hashtag_count", 25),
    )
    print(f"  [caption] {caption[:120].replace(chr(10), ' / ')}...")

    # 2. host video
    print("  [host] uploading to public host...")
    public_url = host_video(video_path, method=settings.get("video_host_method", "fileio"))
    if not public_url:
        print("  [host] all hosts failed, skipping")
        return False
    print(f"  [host] public URL: {public_url}")

    # 3. post
    media_id = post_reel(
        ig_user_id=page_cfg["ig_user_id"],
        access_token=page_cfg["access_token"],
        video_url=public_url,
        caption=caption,
    )
    success = bool(media_id)

    # 4. log
    append_log(log_path, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "page": page_cfg["name"],
        "file": video_path.name,
        "caption_preview": caption[:80].replace("\n", " "),
        "public_url": public_url,
        "media_id": media_id or "",
        "status": "posted" if success else "failed",
    })

    # 5. move file
    if success and settings.get("move_after_post", True):
        posted_dir = video_path.parent / "posted"
        posted_dir.mkdir(exist_ok=True)
        shutil.move(str(video_path), str(posted_dir / video_path.name))
        print(f"  [fs] moved to {posted_dir}")
    elif not success:
        failed_dir = video_path.parent / "failed"
        failed_dir.mkdir(exist_ok=True)
        shutil.move(str(video_path), str(failed_dir / video_path.name))
        print(f"  [fs] moved to {failed_dir}")

    return success


def main():
    here = Path(__file__).parent
    cfg_path = here / "config.json"
    if not cfg_path.exists():
        print("ERROR: config.json not found. Copy config.example.json to config.json and fill in your tokens.")
        sys.exit(1)

    with open(cfg_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    pages = config["pages"]
    settings = config.get("settings", {})
    log_path = here / settings.get("log_file", "output/post_log.csv")
    interval = settings.get("watch_interval_seconds", 30)
    min_delay = settings.get("min_delay_between_posts_seconds", 60)

    # make sure each page folder exists
    for page in pages:
        (here / page["folder"]).mkdir(parents=True, exist_ok=True)

    print(f"Watching {len(pages)} page folder(s). Drop videos in to post automatically.")
    print(f"Polling every {interval}s. Press Ctrl+C to stop.\n")

    while True:
        try:
            for page in pages:
                folder = here / page["folder"]
                for video in find_new_videos(folder):
                    process_one_video(page, video, settings, log_path)
                    time.sleep(min_delay)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped by user.")
            break
        except Exception as e:
            print(f"[main] unexpected error: {e}. Sleeping and continuing.")
            time.sleep(interval)


if __name__ == "__main__":
    main()
