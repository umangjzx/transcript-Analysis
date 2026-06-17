# Cloud Run Deployment Log — June 17, 2026

## What Was Done Today

### 1. Backend Deployed to Google Cloud Run ✅
- **Service URL**: `https://audio-safety-backend-781782361175.us-central1.run.app`
- **Project**: `melodywings` (GCP)
- **Region**: `us-central1`
- **Config**: 2 vCPU, 2Gi RAM, 900s timeout, min-instances=1

### 2. Google OAuth (Drive Integration) Configured ✅
- OAuth Client ID configured in GCP Console
- Redirect URI added: `https://audio-safety-backend-781782361175.us-central1.run.app/api/v1/google-drive/callback`
- Authorized JS origins: `https://transcript-analysis-yo1h.vercel.app`
- **Credential persistence**: Modified `credential_encryption.py` to store Google OAuth tokens in MongoDB (survives container restarts)

### 3. Upstash Redis (Free Tier) Set Up ✅
- **URL**: `rediss://...@usable-shiner-110285.upstash.io:6379`
- Connected to Celery as broker + result backend
- Fixed TLS `ssl_cert_reqs` issue for `rediss://` connections

### 4. Celery Worker Running in Same Container ✅
- `start.sh` runs both uvicorn (FastAPI) and Celery worker
- Using `--pool=threads` (avoids PyMongo fork issues)
- Worker connected to Redis and receiving tasks

### 5. GCP Org Policy Fixed ✅
- Overrode `iam.allowedPolicyMemberDomains` to allow `allUsers`
- Added `roles/run.invoker` to `allUsers` for public access
- Added `roles/storage.admin` to compute service account

### 6. Vercel Frontend Updated ✅
- `BACKEND_URL` env var set to Cloud Run URL
- Frontend deployed at `https://transcript-analysis-yo1h.vercel.app`

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Cloud Run Service | ✅ Running | Healthy, responding to requests |
| FastAPI Server | ✅ Working | Auth, uploads, reports all functional |
| Celery Worker | ⚠️ Partially Working | Connects to Redis, receives tasks, but analysis results not saving to MongoDB properly |
| MongoDB Atlas | ✅ Connected | From FastAPI (main process) |
| Upstash Redis | ✅ Connected | Celery broker working |
| Google Drive OAuth | ✅ Configured | Needs re-auth from frontend after deployment |
| S3 Upload | ✅ Working | PDF reports uploading to S3 |
| ML Classifier | ❌ Disabled | `ENABLE_ML_CLASSIFIER=false` (saves cold-start time) |

---

## Known Issues (To Fix Tomorrow)

### 1. Analysis results not persisting to MongoDB from Celery worker
- **Root cause**: The `save_full_analysis` function works from the main process but fails silently from the Celery thread worker. The risk score IS computed (48.9 Moderate), PDF IS generated and uploaded to S3, but the final MongoDB write to update `findings`, `severity`, `risk_score`, and `status=COMPLETED` doesn't complete.
- **Likely fix**: Add explicit logging in `save_full_analysis` / `_save_full_analysis_no_transaction` to identify where exactly it fails. May need to force a fresh MongoDB connection in the worker thread context.

### 2. SentenceTransformer model download fails in container
- **Error**: `[Errno 2] No such file or directory: '.../1_Pooling/config.json'`
- **Impact**: Chatbot RAG embeddings (non-critical for analysis)
- **Fix**: Either pre-download the model in Dockerfile or disable the chatbot embedding step

### 3. Cold start time (~5 min)
- **Cause**: Distilbert-mnli model downloads from HuggingFace on every new container
- **Fix Options**:
  - Pre-download models in Dockerfile (increases image size by ~500MB but eliminates cold start)
  - Use Google Artifact Registry to cache the Docker image layers
  - Keep `min-instances=1` (current setting — container stays warm)

---

## Tomorrow's Plan

1. **Fix `save_full_analysis` in Celery worker context**
   - Add debug logging to `_save_full_analysis_no_transaction`
   - Test MongoDB writes from within a Celery thread task
   - Consider creating a fresh `MongoClient` per-task if the global one is stale

2. **Pre-download ML models in Dockerfile**
   - Add `RUN python -c "from transformers import pipeline; pipeline('zero-shot-classification', model='typeform/distilbert-base-uncased-mnli')"` to Dockerfile
   - This eliminates cold-start model downloads entirely

3. **Test full end-to-end from Vercel frontend**
   - Login → Submit transcript → Verify analysis completes → Check report in UI

4. **Google Drive re-authorization**
   - Connect Google Drive from the frontend UI (one-time OAuth flow)
   - Verify credentials persist in MongoDB across container restarts

5. **(Optional) Reduce min-instances to 0 once cold-start is fixed**
   - With pre-downloaded models, cold start drops to ~30s instead of ~5min
   - Can remove `min-instances=1` to save cost

---

## Environment Variables on Cloud Run

All env vars are set via `gcloud run services update --update-env-vars`:

```
MONGO_URI, MONGO_DB_NAME, JWT_SECRET, JWT_EXPIRE_MINUTES, ENV=production,
COOKIE_SECURE=true, ALLOWED_ORIGINS, APP_URL, GOOGLE_CLIENT_ID,
GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME, ENABLE_ML_CLASSIFIER=false,
MAX_UPLOAD_MB=300, API_KEY, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
DRIVE_AUTO_WATCH=true, DRIVE_POLL_INTERVAL_SECONDS=120, DRIVE_WATCH_FOLDER_ID,
USE_CELERY=true, REDIS_URL, CREDENTIAL_ENCRYPTION_KEY
```

---

## Useful Commands

```bash
# View logs
gcloud run services logs read audio-safety-backend --region=us-central1 --limit=50

# Update env vars
gcloud run services update audio-safety-backend --region=us-central1 --update-env-vars "KEY=VALUE"

# Deploy new code
cd New-Rmsi-Latest/backend
gcloud run deploy audio-safety-backend --source . --region us-central1 --memory 2Gi --cpu 2 --timeout 900 --port 8000 --min-instances=1

# Check service status
gcloud run services describe audio-safety-backend --region=us-central1 --format="get(status.url)"
```
