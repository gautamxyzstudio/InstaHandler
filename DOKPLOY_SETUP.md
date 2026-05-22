# Deploy to Dokploy

This guide gets the MOZART app running on your Dokploy server with HTTPS, a login screen, and persistent storage. You'll end up with a URL like `https://mozart.yourdomain.com` you can use from any device.

Time required: ~20 minutes (most of it waiting for the first build).

---

## What you need before starting

- [x] Dokploy installed on a server you control (you said you have this).
- [x] A domain name you can change DNS for. You'll point one subdomain (e.g. `mozart.yourdomain.com`) at the Dokploy server.
- [x] The code from this folder either:
  - pushed to a private Git repo (GitHub/GitLab), **or**
  - uploaded directly to the server.

---

## Step 1 — DNS

In your domain registrar's DNS panel, add an **A record**:

| Type | Name | Value |
|---|---|---|
| A | `mozart` (or any subdomain you want) | the IP of your Dokploy server |

Save. Wait 1–5 minutes for it to propagate. Test: `ping mozart.yourdomain.com` from your Mac should return the server's IP.

---

## Step 2 — Create the app in Dokploy

1. In Dokploy, click **Projects** → **+ Create Project**.
   - Name: `mozart-insta-handler`.
2. Inside the project, click **+ Create Service** → **Application**.
3. **Source** — pick one:
   - **From Git** (recommended): connect your GitHub/GitLab, pick the repo + branch.
   - **From local Docker Compose**: paste the contents of `docker-compose.yml` from this folder. Upload the rest of the source via Dokploy's file panel or git.
4. **Build Type**: **Dockerfile** (Dokploy auto-detects the `Dockerfile` in the root).

---

## Step 3 — Set environment variables

In Dokploy → your service → **Environment** tab, add:

```
PUBLIC_BASE_URL=https://mozart.yourdomain.com
APP_USERNAME=mozartadmin
APP_PASSWORD=<paste a long random string here>
FLASK_SECRET_KEY=<paste another long random string>
TZ=Asia/Kolkata
```

Tips:
- Generate random strings with: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` on your Mac, or use any password manager.
- Don't quote the values in Dokploy's env editor — it adds the quotes for you.
- Keep these values somewhere safe. You'll need `APP_USERNAME` + `APP_PASSWORD` to log in.

---

## Step 4 — Set up the domain

In Dokploy → your service → **Domains** tab → **+ Add Domain**:

| Field | Value |
|---|---|
| Host | `mozart.yourdomain.com` |
| Path | `/` |
| Container Port | `5050` |
| HTTPS | ✓ enabled |
| Certificate Provider | Let's Encrypt |

Save. Dokploy/Traefik will fetch an SSL cert automatically within ~30 seconds.

---

## Step 5 — Add a persistent volume

This is so your `config.json`, posted videos, and history don't disappear on rebuild.

In Dokploy → your service → **Volumes** (or **Mounts**) tab → **+ Add Volume**:

| Field | Value |
|---|---|
| Type | Volume (named) |
| Name | `mozart_data` |
| Mount Path | `/data` |

Save.

---

## Step 6 — Deploy

Click **Deploy**. First build takes 2–4 minutes (downloading Python image, installing deps). You'll see logs streaming.

When the log shows something like:

```
[INFO] Listening at: http://0.0.0.0:5050
[INFO] Booting worker with pid: ...
```

…it's ready.

Open `https://mozart.yourdomain.com` in your browser. You should see the **MOZART** login screen. Sign in with the username + password you set in Step 3.

---

## Step 7 — Update Google Cloud OAuth redirect URI

This is critical — without it, "Connect YouTube" will fail with `redirect_uri_mismatch`.

1. Open https://console.cloud.google.com/
2. Make sure the right project is selected at the top.
3. Left menu → **APIs & Services** → **Credentials**.
4. Click your OAuth client (the one named **Mozart Uploader Local** or similar from `YOUTUBE_SETUP.md`).
5. Under **Authorized redirect URIs** → **+ Add URI** → paste:
   ```
   https://mozart.yourdomain.com/oauth/youtube/callback
   ```
   (Use *your* actual domain, with `https://`.)
6. Click **Save**.

You can keep the old `http://127.0.0.1:5050/oauth/youtube/callback` too — it stays valid for local Mac usage.

---

## Step 8 — Use it

Same as locally:

1. Sign in at `https://mozart.yourdomain.com`.
2. **Brands & Accounts** → **+ Add brand** → fill in IG + paste YT OAuth credentials → **Save** → **Connect YouTube →**.
3. **Dashboard** → pick a brand → drag videos → schedule or post now.

Because the server runs 24/7, **scheduled posts now fire on time even when your Mac is off**.

---

## Backups

Your data lives in the `mozart_data` Docker volume. To back it up from the Dokploy server:

```bash
# on the Dokploy server
docker run --rm -v mozart_data:/data -v $PWD:/backup alpine \
  tar czf /backup/mozart-backup-$(date +%F).tar.gz -C /data .
```

That single `.tar.gz` contains all your tokens, history, and unposted uploads.

---

## Updating the app

If you connected from Git:
- Push a new commit → Dokploy auto-rebuilds (if "Auto Deploy" is on), or click **Deploy** manually.

If you uploaded files directly:
- Replace the changed files in Dokploy's file panel → click **Rebuild**.

The `mozart_data` volume persists across rebuilds, so accounts, tokens, and history stay.

---

## Troubleshooting

**Browser shows "502 Bad Gateway"**
→ Build/deploy is still in progress, or the container crashed. Check Dokploy logs.

**"redirect_uri_mismatch" when connecting YouTube**
→ You missed Step 7. Add `https://yourdomain.com/oauth/youtube/callback` to the OAuth client's Authorized redirect URIs.

**Stuck on login screen even with correct password**
→ The session cookie isn't sticking because `FLASK_SECRET_KEY` changed between deploys. Set a fixed long random value in env and redeploy.

**Uploads fail / timeout on large videos**
→ Dokploy's reverse proxy (Traefik) has a body size limit. In Dokploy domain settings, increase **Max Body Size** to e.g. 4G. The Dockerfile inside is already configured for large uploads.

**Scheduled posts didn't fire at the expected time**
→ Container time zone is off. Set `TZ=Asia/Kolkata` (or your zone) in env. Restart the service.

**YouTube uploads fail with "quota exceeded"**
→ Default YT Data API quota is 10,000 units/day per Cloud project (~6 uploads/day). Request a quota increase in Google Cloud Console → APIs & Services → YouTube Data API v3 → Quotas.

**"Couldn't connect to Instagram"**
→ Your long-lived IG token expired (60-day lifespan). Regenerate in Graph API Explorer and update under **Brands & Accounts** → edit brand → paste new token → Save.

---

## Local + Dokploy together?

Yes — they can coexist. The same `config.json` schema works in both places, but they're separate stores (one on your Mac, one in the Dokploy volume). Pick one as your primary, or use Mac for testing and Dokploy for the real schedule.

If you want them to share data, you can rsync the Mac's `config.json` and `uploads/` to the Dokploy server, but that's manual.
