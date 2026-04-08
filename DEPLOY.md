# Deploying Templar's Website on Render

## Option 1: Deploy via Render UI (Recommended)

### Step 1: Push to GitHub
```bash
cd /home/freshkied/moneymaker/templar
git init
git add .
git commit -m "Templar v1 — AI-powered digital product system"
git remote add origin https://github.com/YOUR_USERNAME/templar.git
git push -u origin master
```

### Step 2: Create a new Web Service on Render
1. Go to https://render.com → "New" → "Web Service"
2. Connect your GitHub repo
3. Configure:
   - **Name:** `templar-website`
   - **Region:** Oregon (or your closest)
   - **Branch:** `master`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements-website.txt`
   - **Start Command:** `gunicorn -k uvicorn.workers.UvicornWorker src.website.app:app --bind 0.0.0.0:$PORT`
4. Click "Create Web Service"

Render will auto-detect it's a FastAPI app, install dependencies, and deploy.

---

## Option 2: Deploy via renderctl CLI

```bash
pip install renderctl
renderctl deploy --spec render-website.yaml
```

---

## Custom Domain (Optional)

1. In Render dashboard → your service → Settings → Custom Domains
2. Add your domain (e.g., `templar.so` or `yoursite.com`)
3. Update DNS:
   - Add `CNAME` record: `www` → `templar-website.onrender.com`
   - Add `URL redirect` for bare domain → `www.yoursite.com` (or use Render's Netlify-style redirect)

---

## Free Tier Limits

Render's free tier:
- Service sleeps after 15 min of inactivity (first request after sleep takes ~30s cold start)
- 750 hours/month
- No custom domain SSL on free tier (use Render's free subdomain)

For a marketing site with low traffic, the free tier is fine.

---

## Environment Variables on Render

If you have custom config (not needed for the website itself):

1. In Render dashboard → your service → Environment
2. Add variables if needed (website doesn't require any API keys)

---

## Verify Deployment

Once deployed, visit:
- `https://templar-website.onrender.com` (Render subdomain)
- `https://your-custom-domain.com` (if configured)

Check:
- `/` — landing page
- `/templates` — all templates
- `/template/habit-tracker` — template detail page
- `/health` — health check endpoint

---

## Updating

Push to GitHub → Render auto-deploys within ~30 seconds.

---

## Troubleshooting

**404 on all routes except `/`:**
The site is behind a CDN that only routes `/` to the app. Make sure `render-website.yaml has `startCommand` correctly set to use gunicorn with uvicorn worker — this is required for FastAPI routing to work.

**Slow cold start:**
Free tier spins down after 15 min. Cold starts take ~30s. Upgrade to a paid plan ($7/mo) for always-on.

**Module import errors:**
Make sure `sys.path.insert(0, ...)` in `app.py` points to the right project root. The structure should be:
```
templar/
  src/
    website/
      app.py
  requirements-website.txt
```
