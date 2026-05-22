"""
YouTube Shorts uploader.

Each brand stores a refresh_token (obtained once via the OAuth flow in app.py).
This module exchanges the refresh_token for an access_token at call time,
then resumable-uploads the video and sets Shorts metadata.

Dependencies (pulled in via requirements.txt):
  google-auth, google-auth-oauthlib, google-api-python-client
"""

from __future__ import annotations

import os
from typing import Optional

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# Scope must match the one used when generating the refresh token.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _make_credentials(client_id: str, client_secret: str, refresh_token: str) -> Credentials:
    """Build a Credentials object that auto-refreshes its access token."""
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds


def upload_short(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "22",          # 22 = People & Blogs (good default)
    privacy_status: str = "public",   # "public" | "unlisted" | "private"
    made_for_kids: bool = False,
) -> dict:
    """
    Upload a vertical video as a YouTube Short.

    YouTube auto-classifies a video as a Short when:
      - aspect ratio is vertical (9:16)
      - duration <= 60 seconds
    Including `#shorts` in the title or description boosts discoverability.

    Returns:
      {"ok": bool, "video_id": str | None, "url": str | None, "error": str | None}
    """
    if not os.path.exists(video_path):
        return {"ok": False, "video_id": None, "url": None, "error": "video file not found"}

    try:
        creds = _make_credentials(client_id, client_secret, refresh_token)
    except Exception as e:
        return {"ok": False, "video_id": None, "url": None, "error": f"oauth refresh: {e}"}

    try:
        youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=creds,
                        cache_discovery=False)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:15],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

        media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True,
                                mimetype="video/*")
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            # status.progress() returns 0..1 — could be reported back to UI

        video_id = response.get("id")
        return {
            "ok": True,
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}" if video_id else None,
            "error": None,
        }

    except HttpError as e:
        return {"ok": False, "video_id": None, "url": None, "error": f"youtube api: {e}"}
    except Exception as e:
        return {"ok": False, "video_id": None, "url": None, "error": f"upload: {e}"}


# ------------- OAuth helpers -------------

def build_oauth_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the Google consent URL the user opens to grant permission."""
    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": YOUTUBE_UPLOAD_SCOPE,
        "access_type": "offline",         # gets us a refresh token
        "prompt": "consent",              # forces refresh_token issue each time
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_code_for_refresh_token(client_id: str, client_secret: str,
                                    code: str, redirect_uri: str) -> dict:
    """Exchange the OAuth `code` for a refresh_token. Returns dict with error or token."""
    import requests
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=30)
    if r.status_code != 200:
        return {"ok": False, "error": f"token exchange: {r.status_code} {r.text[:300]}"}
    data = r.json()
    if "refresh_token" not in data:
        return {
            "ok": False,
            "error": "Google didn't return a refresh_token. Make sure prompt=consent and access_type=offline.",
        }
    return {"ok": True, "refresh_token": data["refresh_token"]}
