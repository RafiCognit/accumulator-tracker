# Deploying the Accumulator Tracker to Streamlit Community Cloud

You get a free public link like `https://your-app-name.streamlit.app`.
Anyone with the link can use it, with live Yahoo Finance search and prices.

## Files to upload
- `accumulator_tracker.py`
- `requirements.txt`

## 1. Put the files on GitHub (about 2 minutes)
1. Sign in at https://github.com (create a free account if you don't have one).
2. Click **+** (top right) → **New repository**.
   - Name: `accumulator-tracker`
   - Visibility: **Public** (simplest; the free tier also allows one private app)
   - Click **Create repository**.
3. On the new repo page, click **uploading an existing file**.
4. Drag in `accumulator_tracker.py` and `requirements.txt`, then click **Commit changes**.

## 2. Deploy on Streamlit (about 3 minutes)
1. Go to https://share.streamlit.io and click **Continue with GitHub**. Approve access.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - Repository: `<your-github-name>/accumulator-tracker`
   - Branch: `main`
   - Main file path: `accumulator_tracker.py`
   - App URL: pick a name, e.g. `sp-accumulator`
4. Click **Deploy**. The first build takes 2–3 minutes.

Your shareable link is the App URL, e.g. `https://sp-accumulator.streamlit.app`.

## Updating later
Edit or re-upload `accumulator_tracker.py` on GitHub. The app redeploys automatically.

## Good to know
- Anyone with the link can open a public app. To limit it to specific people, open
  the app's **Settings → Sharing** on share.streamlit.io and invite viewers by email
  (this requires the repo to be private).
- Free apps go to sleep after a few days without visitors. The next visitor clicks
  "Wake up" and waits about 30 seconds.
- Yahoo Finance sometimes rate-limits shared cloud servers. If a search or price load
  fails, wait a minute and reload.
