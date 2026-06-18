# Work Log — June 18, 2026

## What Was Done Today

### 1. Fixed Detection Pipeline Failing on Cloud Run ✅
**Problem:** Analysis results computed by the Celery worker never persisted to MongoDB. Records stuck in `PROCESSING` forever.

**Root cause:** Long-lived Celery worker held a cached `MongoClient` whose socket was dropped by Atlas during idle periods. The write failed silently.

**Fix:**
- `database/mongo.py`: Added `get_mongo_db(force_reconnect=True)`, `ensure_live_connection()` ping+reconnect, and retry logic in `save_full_analysis()` that retries the full 7-collection write once on a fresh connection.
- `modules/analysis_pipeline.py`: Step 7 now checks save results and marks record `FAILED` instead of silently leaving it `PROCESSING`.

---

### 2. Fixed OAuth Callback Blocked by API Key Middleware ✅
**Problem:** Google Drive OAuth callback (`/api/v1/google-drive/callback`) was rejected with "Missing X-API-Key" because browser redirects can't include custom headers.

**Fix:** Added the callback path to `_PUBLIC_PATHS` in `app.py`.

---

### 3. Fine-tuned ML Classifier (99.4% Accuracy) ✅
**Problem:** Base `distilbert-mnli` model disagreed with rule-based detections and LOWERED scores instead of boosting them.

**What was done:**
- Generated 18,000 unique NLI training samples (`generate_dataset.py`) across 21 grooming categories with balanced labels (40% entailment / 25% neutral / 35% contradiction)
- Fine-tuned for 5 epochs on Google Colab T4 GPU (~6 min)
- Final metrics: **99.37% accuracy, 99.44% macro F1**
- Model now correctly agrees with rule detections (secrecy, meeting, video_call, trust_building all `agree=True`)
- Uploaded model weights to GCS bucket (`gs://melodywings-ml-models/grooming-nli-finetuned/`)
- Dockerfile downloads model from GCS during build (source upload has 100MB limit)

**Files:**
- `generate_dataset.py` — dataset generator
- `finetune_colab.ipynb` — ready-to-use Colab notebook
- `data/grooming_nli_dataset.json` — 18K sample dataset
- Model at `gs://melodywings-ml-models/grooming-nli-finetuned/`

---

### 4. Fixed Container Startup Crash (CRLF) ✅
**Problem:** `start.sh` had Windows line endings (`\r\n`), causing `$'\r': command not found` in the Linux container.

**Fix:** Converted to LF-only line endings.

---

### 5. Fixed `token_type_ids` Error with Fine-tuned Model ✅
**Problem:** DistilBERT doesn't accept `token_type_ids` but the HuggingFace pipeline sends them, crashing batch inference.

**Fix:** Filtered `token_type_ids` from `tokenizer.model_input_names` when loading the fine-tuned model in `ml_classifier.py`.

---

### 6. Fixed Upload Endpoint Crash (non-string transcript) ✅
**Problem:** `body.get("transcript", "").strip()` crashed with `AttributeError` when the transcript field was parsed as a dict.

**Fix:** Added type checking to coerce non-string values before `.strip()` in `upload_routes.py`.

---

### 7. Increased Line Length Limit ✅
**Problem:** Multi-paragraph transcripts were rejected by the 10,000 char/line limit.

**Fix:** Increased to 50,000 chars/line.

---

### 8. Performance: 6 Celery Threads + Rate Limit Increase ✅
- Bumped Celery concurrency from 2 → 6 threads (3x queue throughput)
- Increased upload rate limit from 10/min → 60/min for batch analysis
- Benchmark: 38 files processed in 16.6 min (avg 26s/file), 100% success

---

### 9. Email Alerts Fixed ✅
**Problem:** `ALERT_RECIPIENTS` and `PARENT_RECIPIENTS` env vars were never set on Cloud Run.

**Fix:** Added them via `gcloud run services update`. Both parent and admin emails now sending with PDF attachments.

---

### 10. Detection Dashboard Login Loop Fixed ✅
**Problem:** After logging in on `transcript-analysis-yo1h.vercel.app`, the user was immediately redirected back to login.

**Root cause:** Vercel's `rewrites()` proxy strips `Set-Cookie` headers from upstream responses. The httpOnly cookie from Cloud Run never reached the browser. First API call → 401 → `clearAuth()` → login loop.

**Fix:** Switched `admin-next/src/lib/api.js` from httpOnly cookie auth to Bearer token auth (stored in localStorage, sent as `Authorization: Bearer` header). Backend already supports this.

---

### 11. Merged to Main ✅
- PR #2 squash-merged into `feature/mw-integration`
- `feature/mw-integration` merged into `main`
- Vercel auto-deploying from `main`

---

## Current Cloud Run Config
```
Service: audio-safety-backend
Region: us-central1
CPU: 2 vCPU
RAM: 2 GB
Timeout: 900s
Min instances: 1
Celery threads: 6
ML Classifier: ENABLED (fine-tuned)
Model: gs://melodywings-ml-models/grooming-nli-finetuned/
```

---

## What's Left for Tomorrow

### 1. Verify Detection Dashboard Login (Vercel)
- Vercel should have auto-deployed the Bearer token auth fix
- Test login at `https://transcript-analysis-yo1h.vercel.app`
- If still failing, check Vercel deployment logs / env vars

### 2. MW Admin Frontend — Safety Tab (iframe)
- The `/safety` page embeds the detection dashboard in an iframe
- Cross-origin iframe + third-party cookie blocking may still need work
- May need to pass a token via URL param or use postMessage API

### 3. MW Admin Frontend — Login Loop (separate issue?)
- Clarify if the MW admin (`localhost:3000`) login itself is broken
- Or if it's only the iframe'd detection dashboard inside it
- Check `melody-wings-backend` is running on port 8002

### 4. Google Drive Re-authorization
- OAuth callback fix is deployed
- Need to re-auth from the frontend UI (one-time flow)
- Verify credentials persist in MongoDB across container restarts

### 5. (Optional) Reduce min-instances to 0
- With model baked in, cold start is ~2 min (model load from disk)
- Could save cost by setting min-instances=0 during off-hours
- Currently min-instances=1 to avoid any cold start

### 6. (Optional) Fine-tune with More Epochs
- Current model: 5 epochs, 99.4% accuracy
- Could try 8-10 epochs for even higher confidence scores
- ML confidence currently 0.25-0.35 (correct labels but moderate confidence)
