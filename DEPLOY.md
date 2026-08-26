# Deploy to Railway — Step-by-Step

Railway gives you a **free tier** with $5/month of compute credit (enough for a portfolio demo).
Cold starts are ~30s on first request. After that, responses are fast.

---

## Prerequisites

- GitHub account with this repo pushed
- Railway account: https://railway.app (sign in with GitHub)
- **HuggingFace account** (free): https://huggingface.co → Settings → Access Tokens → create a **Read** token

> **Only ONE free API key needed — HuggingFace powers both embeddings and LLM chat.**

---

## Step 1 — Push Your Code to GitHub

```bash
cd "g:\Projects\Document Intelligence API"

git add .
git commit -m "Switch to HuggingFace free API for Railway"
git push origin main
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
| `HF_API_KEY` | `hf_...` (your HuggingFace read token) |
| `LLM_PROVIDER` | `huggingface` |
| `LLM_MODEL` | `meta-llama/Llama-3.3-70B-Instruct` |
| `EMBEDDING_PROVIDER` | `huggingface` |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` |
| `DEBUG` | `false` |
| `CHROMA_PERSIST_DIRECTORY` | `./chroma_store` |
| `CHROMA_COLLECTION_NAME` | `documents` |
| `MAX_UPLOAD_SIZE_MB` | `20` |

> **Note:** Railway automatically injects `PORT`. Do NOT set it manually — the Dockerfile already handles it.

> **Why HuggingFace for everything?**
> - Embeddings + LLM both run on HuggingFace's servers (free)
> - No local model download needed — stays under Railway's 512MB RAM limit
> - Only ONE API key to manage

---

## Step 4 — Wait for Build (~3–5 min)

The build is much faster now since no heavy ML models are downloaded at build time.

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
| Build fails — OOM / memory crash | Ensure `EMBEDDING_PROVIDER=huggingface` (NOT `local`) |
| 500 on upload — HuggingFace timeout | Model may be cold-starting on HF servers. Retry in 30s. |
| 500 on query — HF auth error | Verify `HF_API_KEY` is set correctly in Railway Variables |
| `EMBEDDING_MODEL not set` error | Add `EMBEDDING_MODEL` to Railway variables |

---

## Alternative: Render.com (also free)

If Railway free credits run out:

1. Go to https://render.com → New → **Web Service**
2. Connect your GitHub repo
3. Set **Environment**: `Docker`
4. Set same environment variables as above
5. Deploy

Render's free tier sleeps after 15 min inactivity. Railway is better for demos.
