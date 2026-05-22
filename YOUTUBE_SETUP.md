# YouTube Setup — One-time, ~15 minutes per Google account

You need to do this **once** per Google account that owns YouTube channels. If all your YouTube channels are under the same Google account, you do this exactly once and reuse the same Client ID + Secret across all your brands.

What you'll end up with:
- An **OAuth Client ID** and **OAuth Client Secret** — you paste these into each brand's settings in the app.
- One-time per brand: click "Connect YouTube" in the app, sign in with the Google account that owns that channel, grant permission. The app stores the refresh token in `config.json`.

---

## Part 1 — Google Cloud project (5 min)

1. Open **https://console.cloud.google.com/**. Sign in with the Google account that owns your YouTube channels.

2. At the very top, click the **project dropdown** → **New Project**.
   - Project name: `mozart-uploader` (or whatever)
   - Click **Create**, wait ~10 seconds, then select the new project from the dropdown.

3. In the left menu (☰) → **APIs & Services** → **Library**.
   - Search **YouTube Data API v3** → click it → click **Enable**. Wait a moment.

---

## Part 2 — OAuth consent screen (5 min)

1. Left menu → **APIs & Services** → **OAuth consent screen**.

2. **User Type:** select **External** → **Create**.

3. **App information:**
   - App name: `Mozart Uploader`
   - User support email: (your email)
   - Developer contact email: (your email)
   - Skip "App logo", "App domain", and other optional fields.
   - Click **Save and Continue**.

4. **Scopes:** click **Add or Remove Scopes**.
   - In the filter, type: `youtube.upload`
   - Tick: `.../auth/youtube.upload`
   - Click **Update**, then **Save and Continue**.

5. **Test users:** click **+ Add Users** → add the Google account email(s) that own your YouTube channels (up to 100). Click **Save and Continue** → **Back to Dashboard**.

   This keeps the app in "Testing" mode. That is fine — Testing mode supports up to 100 test users and works indefinitely. You do NOT need to publish the app.

---

## Part 3 — Create OAuth credentials (3 min)

1. Left menu → **APIs & Services** → **Credentials**.

2. Click **+ Create Credentials** → **OAuth client ID**.

3. **Application type:** select **Web application**.

4. **Name:** `Mozart Uploader Local`.

5. **Authorized redirect URIs** → click **+ Add URI**, paste exactly:
   ```
   http://127.0.0.1:5050/oauth/youtube/callback
   ```
   (Important: this must match `127.0.0.1`, not `localhost`. The app uses `127.0.0.1`.)

6. Click **Create**.

7. A dialog pops up showing your **Client ID** and **Client Secret**. Click **Download JSON** to save a backup, but most importantly: **copy these two strings**, you'll paste them into the app.

---

## Part 4 — Connect a brand in the app

1. In the MOZART app, go to **Brands & Accounts**.
2. Click **+ Add brand** (or open an existing brand).
3. Fill in name, niche, caption style, CTA, hashtag count.
4. Fill in Instagram details (IG Business Account ID + token) if this brand has an IG account.
5. In the **YouTube** section, paste the **OAuth Client ID** and **OAuth Client Secret** from Part 3.
6. Click **Save brand**.
7. Click **Connect YouTube →**. A new tab opens to Google. Sign in with the Google account that owns the YouTube channel for this brand. Grant `youtube.upload` permission.
8. Tab will auto-close. Back in the app, you'll see **connected ✓** next to YouTube.

That's it. You can now bulk-upload videos to that brand and they'll publish to both Instagram and YouTube Shorts.

---

## Reusing one Client ID + Secret for multiple brands

If you have 4 YouTube channels under the same Google account (or split across a few Google accounts where you own multiple channels), you only need to create the OAuth credentials once. Just paste the same Client ID + Secret into each brand, and click "Connect YouTube" — Google will ask you to pick *which channel* to upload to during the consent flow.

If your YouTube channels are under completely different Google accounts, each Google account needs its own Cloud project + OAuth credentials (repeat Parts 1–3 for each one).

---

## Troubleshooting

**"Error 400: redirect_uri_mismatch"**
→ The Authorized redirect URI in Cloud Console doesn't match exactly. Confirm it is `http://127.0.0.1:5050/oauth/youtube/callback` (not `localhost`, not `https`, not a trailing slash).

**"Access blocked: This app's request is invalid"**
→ Either the scope is wrong or the consent screen wasn't fully configured. Re-check Part 2 step 4.

**"This app isn't verified"**
→ Normal. Click **Advanced** → **Go to Mozart Uploader (unsafe)**. Apps in Testing mode always show this warning. It's safe because you wrote it (well, I did, but it runs locally on your machine).

**"You aren't a test user"**
→ Add the Google account email under Part 2 step 5 (Test users).

**"Quota exceeded" later when uploading**
→ The default YT Data API quota is 10,000 units/day, and each upload uses ~1,600 units, so ~6 uploads/day is the free limit. Need more? Request a quota increase in Cloud Console → APIs & Services → YouTube Data API v3 → Quotas. Approval usually takes a few days.

**"The user does not have a YouTube channel"**
→ The Google account you used to authorize doesn't have a YouTube channel attached. Create or pick the right channel.
