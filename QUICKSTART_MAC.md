# Quickstart for Mac

## Step 1 — Make the launcher runnable (one-time, ~30 seconds)

macOS blocks scripts by default. You need to allow it once.

**Easiest way:**

1. Open **Terminal** (press `Cmd + Space`, type "Terminal", hit Enter).
2. Copy-paste this command and press Enter:

   ```bash
   chmod +x "/Users/gautamk/Documents/Claude/Projects/MOZART insta handler/start.command"
   ```

That's it. Now `start.command` will work when you double-click it.

## Step 2 — Launch the app

Open the folder `MOZART insta handler/` in Finder and **double-click `start.command`**.

The first time:
- macOS may say "cannot be opened because it is from an unidentified developer". If so:
  → Right-click `start.command` → **Open** → click **Open** in the dialog.
- A Terminal window pops up.
- It installs Flask + requests (~10 seconds, one time only).
- Your browser opens at `http://127.0.0.1:5050`.

**Keep the Terminal window open** while you use the app. Closing it stops the app.

## Step 3 — Add your 4 Instagram pages

1. In the app, click the **Accounts & Settings** tab.
2. Click **+ Add account**.
3. Fill in for each page:
   - **Page name** — anything (e.g. "Gym Tips Daily")
   - **Niche** — pick from the dropdown (controls hashtags)
   - **Caption style** — energetic, friendly, trendy, funny, etc.
   - **Call to action** — appended to every caption
   - **Instagram Business Account ID** — your numeric IG ID (`17841...`)
   - **Long-lived access token** — your token with `instagram_content_publish` scope
4. Click **Save**. Repeat for all 4 pages.

Your tokens stay on your Mac in `config.json`. Nothing is sent anywhere except Instagram.

## Step 4 — Upload and post

1. Click **Dashboard** tab.
2. Click a page in the left sidebar.
3. Drag your videos onto the dropzone (or click to pick).
4. For each video: the caption is auto-generated. Edit it if you like, then click **Post now**.
5. Or click **Post all drafts** at the top right to bulk-post everything.

Watch the status pills change in real time:
`draft → queued → uploading → publishing → posted` ✓

## Step 5 — Stop the app

In the Terminal window: press `Ctrl + C`, or just close the window.

To restart later: double-click `start.command` again. Your accounts stay saved.

---

## Troubleshooting

**"Permission denied" when double-clicking `start.command`**
→ Run the `chmod +x` command in Step 1.

**"Python 3 is not installed"**
→ Open Terminal and run: `xcode-select --install` (installs Python 3 along with developer tools).

**Browser didn't open automatically**
→ Open any browser and go to `http://127.0.0.1:5050`.

**"Address already in use"**
→ The app is already running in another Terminal window. Close that one first, or open `http://127.0.0.1:5050` to use it.

**App started but I see "ModuleNotFoundError: flask"**
→ In Terminal, run:
   ```bash
   pip3 install --user --break-system-packages flask requests
   ```

**Post fails with "permissions" error**
→ Your access token is missing the `instagram_content_publish` scope. Regenerate it in Meta Graph API Explorer with that scope enabled, then update under **Accounts & Settings**.

**Posts fail with "invalid_user_id"**
→ The Instagram Business Account ID is wrong. It's the numeric ID (`17841...`), NOT the FB Page ID or the username. Get it from Graph API Explorer with `me/accounts?fields=instagram_business_account`.

---

If anything else breaks, copy the error text from the Terminal window and I can fix it.
