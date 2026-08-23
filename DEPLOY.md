# Deploy to Railway — Step-by-Step

Railway gives you a **free tier** with $5/month of compute credit (enough for a portfolio demo).
Cold starts are ~30s on first request. After that, responses are fast.

---

## Prerequisites

- GitHub account with this repo pushed
- Railway account: https://railway.app (sign in with GitHub)
- An OpenAI API key (or Bytez key)

---

## Step 1 — Push Your Code to GitHub

```bash
cd "g:\Projects\Document Intelligence API"

git init
git add .
git commit -m "Initial commit — Document Intelligence API"

# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/document-intelligence-api.git
git branch -M main
git push -u origin main
```

> ⚠️ **Confirm `.env` is in `.gitignore` before pushing** — your API keys must NOT go to GitHub.
> The `.gitignore` already excludes `.env`. Double-check with `git status` — `.env` should not appear.

---

## Step 2 — Create a Railway Project

1. Go to https://railway.app → **New Project**
2. Choose **Deploy from GitHub repo**
3. Authorize Railway to access your GitHub account
4. Select your `document-intelligence-api` repo
5. Railway auto-detects the `Dockerfile` and `railway.toml` → click **Deploy**

---

## Step 3 — Set Environment Variables in Railway

In the Railway dashboard → your service → **Variables** tab, add:

| Key | Value |
|---|---|
| `OPENAI_API_KEY` | `sk-proj-...` (your OpenAI key) |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-4o-mini` |
| `EMBEDDING_PROVIDER` | `local` |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` |
| `DEBUG` | `false` |
| `CHROMA_PERSIST_DIRECTORY` | `./chroma_store` |
| `CHROMA_COLLECTION_NAME` | `documents` |
| `MAX_UPLOAD_SIZE_MB` | `20` |

> **Note:** Railway automatically injects `PORT`. Do NOT set it manually — the Dockerfile already handles it.

---

## Step 4 — Wait for Build (~5–10 min first time)

The first build downloads:
- Python 3.11 slim base image
- All pip dependencies (including `sentence-transformers` and `BAAI/bge-large-en-v1.5`)

BGE-Large is ~1.3GB. The model downloads at **first request**, not at build time.

To force it to download at startup (avoiding cold-start delay on first query), you can add a startup script — but for a portfolio demo, cold-start is acceptable.

---

## Step 5 — Get Your Public URL

Railway → your service → **Settings** → **Networking** → **Generate Domain**

Your API will be live at: `https://your-service-name.up.railway.app`

**Test it:**
```bash
curl https://your-service-name.up.railway.app/health
# Should return: {"status": "ok", "version": "0.1.0"}
```

**Swagger UI:**
```
https://your-service-name.up.railway.app/docs
```

---

## Step 6 — Verify End-to-End

1. Open `/docs` in your browser
2. Upload a document via `POST /documents/upload`
3. Copy the `document_id` from the response
4. Query it via `POST /documents/{id}/query`
5. Verify you get a cited answer with `References:` block

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Build fails — `langchain_community` not found | Confirm `langchain-community>=0.2.0` is in `requirements.txt` |
| 500 on first upload | Check Railway logs — BGE-Large may still be downloading |
| `EMBEDDING_MODEL not set` error | Add `EMBEDDING_MODEL` to Railway variables |
| Cold start >60s | Normal for BGE-Large first load. Subsequent requests are fast. |

---

## Alternative: Render.com (also free)

If Railway free credits run out:

1. Go to https://render.com → New → **Web Service**
2. Connect your GitHub repo
3. Set **Environment**: `Docker`
4. Set same environment variables as above
5. Deploy

Render's free tier sleeps after 15 min inactivity. Railway is better for demos.
