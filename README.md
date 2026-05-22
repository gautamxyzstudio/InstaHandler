# MOZART Multi-Platform Handler

A local web app to manage Instagram + YouTube together.
One caption input → auto-generates Instagram Reel caption + YouTube Short title/description → bulk upload → schedule or post now.

Built for managing multiple brands (e.g. *Mozart India* = Instagram page + YouTube channel linked together).
No limit on the number of brands — 4, 10, 20, more.

---

## What it does

- **Brand groups** — each brand bundles one Instagram + one YouTube account. Add as many brands as you want.
- **Bulk upload** — drag any number of videos onto the dropzone for one brand.
- **Dual auto-captions** — drop a video, the app generates the Instagram caption (with 25 trending hashtags) and the YouTube Short title + description + tags. Edit each side separately before posting.
- **Per-video platform toggles** — by default posts to both IG and YT, but you can untick one per video.
- **Per-video scheduling** — leave the schedule box empty to post now, or pick a date + time to schedule.
- **One-click "Post all drafts"** — bulk schedules/posts every draft for the current brand.
- **Background worker** — handles the queue one job at a time, with throttling between posts to avoid rate limits.
- **Live status** — every video shows real-time pills: `draft → queued/scheduled → uploading → publishing → posted/partial/failed`. Each platform has its own status badge inside the job card.
- **History tab** — full log of every post with IG media ID and YT video URL.

---

## How to launch (Mac)

### One-time setup

Open Terminal and run:

```
chmod +x "/Users/gautamk/Documents/Claude/Projects/MOZART insta handler/start.command"
```

### Every day after

Double-click `start.command`. First run installs all Python dependencies (Flask, Google API client, requests) — takes ~30 seconds. Subsequent runs start instantly. Browser opens at `http://127.0.0.1:5050`.

### Stop the app

Close the Terminal window, or press `Ctrl + C` inside it.

---

## First-time setup inside the app

### 1. Add a brand

1. Click **Brands & Accounts** tab.
2. Click **+ Add brand**.
3. Fill in name (e.g. "Mozart India"), niche (controls hashtag pool), caption style, default CTA, hashtag count.

### 2. Connect Instagram side

Inside the same brand editor:

- **IG Business Account ID** — numeric ID (`17841…`), get it from Graph API Explorer → `me/accounts` → pick your FB Page → `instagram_business_account.id`.
- **Access token** — long-lived token with `instagram_content_publish`, `instagram_basic`, `pages_show_list`, `pages_read_engagement`.

### 3. Connect YouTube side

Follow [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md) once per Google account (~15 minutes). It walks you through:
- Creating a Google Cloud project
- Enabling YouTube Data API v3
- Configuring the OAuth consent screen
- Generating OAuth credentials

Then in the brand editor:
- Paste **OAuth Client ID** and **OAuth Client Secret**.
- Click **Save brand**.
- Click **Connect YouTube →**. A Google sign-in tab opens. Sign in with the account that owns this channel, grant permission. The tab closes itself. You'll see "connected ✓" in the editor.

### 4. Repeat for each brand

Add Mozart India, Mozart US, Mozart EU, etc. The same Google Cloud OAuth Client ID + Secret can be reused across all your brands — just connect each one with its own Google sign-in.

---

## Daily use

1. Click a brand in the left sidebar.
2. Drag videos onto the dropzone (any number at once).
3. For each video card you'll see:
   - The Instagram caption (left side, editable).
   - The YouTube title + description (right side, editable).
   - Two checkboxes: **Post to IG**, **Post to YT**.
   - A schedule picker (leave empty to post now).
   - **Post now** button (says "Schedule" if you've picked a future time).
4. Click **Post all drafts** to queue everything at once.
5. Watch the status pills update in real time.
6. Done videos move to `uploads/_posted/`, failed ones to `uploads/_failed/`.

Anything you don't want to post: click **Remove**. The file is deleted.

---

## File layout

```
MOZART insta handler/
├── start.command           # double-click to launch
├── start.bat               # Windows version
├── app.py                  # Flask web app
├── youtube_uploader.py     # YouTube OAuth + resumable upload
├── caption_generator.py    # IG and YT caption builders
├── hashtags.json           # trending hashtag bank (10 niches)
├── requirements.txt        # Python deps
├── config.json             # YOUR brands + tokens (created automatically)
├── templates/index.html    # UI markup
├── static/style.css        # UI styles
├── static/app.js           # UI logic
├── uploads/                # in-flight videos
│   ├── _posted/            # successfully posted
│   └── _failed/            # failed (kept for re-upload)
├── output/post_log.json    # history (newest 500 posts)
├── README.md               # this file
├── YOUTUBE_SETUP.md        # Google Cloud + YT API setup guide
└── QUICKSTART_MAC.md       # Mac-specific quickstart
```

---

## Limits & caveats

- **Instagram rate limit** — ~25 published posts per IG account per 24 hours.
- **YouTube quota** — default 10,000 units/day per Google Cloud project; each video upload costs ~1,600 units (~6 uploads/day). Request a quota increase in Cloud Console if you need more.
- **Reel / Short specs** — vertical 9:16, MP4 or MOV, under 60 seconds for YouTube to mark as a Short, under 90 seconds for Instagram Reels.
- **Token expiry** — IG long-lived tokens expire after ~60 days. YT refresh tokens don't expire unless revoked or if you re-run the consent flow.
- **Video hosting (Instagram)** — IG fetches via public URL. The app uploads each video to `file.io` (one-time download, then expires) before calling IG. Falls back to `catbox.moe`. YouTube uses direct resumable upload (no public host needed).
- **Trending audio** — neither API lets third-party apps attach Instagram's or YouTube's licensed library audio. Mix the audio into the video before uploading.
- **In-memory queue** — if you close the app while drafts are pending, those drafts are lost (the videos in `uploads/` remain). Posted/failed history is persisted.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Browser didn't open | Open `http://127.0.0.1:5050` manually. |
| Install errors on first run | Run `pip3 install --user --break-system-packages -r requirements.txt` from Terminal in the project folder. |
| IG post fails with permissions error | Token missing `instagram_content_publish` scope. Regenerate in Graph API Explorer. |
| IG `invalid_user_id` | That field needs the IG **Business Account ID** (`17841…`), not the FB Page ID. |
| YT `redirect_uri_mismatch` | The Authorized redirect URI in Google Cloud Console must be exactly `http://127.0.0.1:5050/oauth/youtube/callback`. |
| YT "quota exceeded" | Default cap is ~6 uploads/day per Cloud project. Request a quota increase. |
| Scheduled post didn't fire | App must be running at the scheduled time. The worker only fires when the app is open. |
| Mac says "unidentified developer" | Right-click `start.command` → Open → Open. Once unblocked, double-click works. |

---

## What's NOT included yet

Tell me which you want and I'll add it:

- AI-rewritten captions via Claude / GPT (richer than templates).
- Image and carousel posts (currently only video reels/shorts).
- Auto-DM to first commenters.
- Analytics — pull back reach/saves/views per post into a dashboard.
- Persisting drafts across app restarts.
- Cross-brand multi-select bulk operations.
