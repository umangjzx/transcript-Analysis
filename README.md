# Melody Wings Safety — AI-Powered Audio Grooming Detection

> Detect grooming, manipulation, and harmful language in audio conversations using a multi-stage AI pipeline — regex patterns, context classification, ML zero-shot NLI, temporal weighting, LLM summaries, email alerts, real-time WebSocket progress, and a RAG chatbot.

![Version](https://img.shields.io/badge/Version-2.1.0-blue)
![Risk Score](https://img.shields.io/badge/Risk%20Score-0--100-red)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688)
![React](https://img.shields.io/badge/React-19-61DAFB)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248)
![AWS S3](https://img.shields.io/badge/AWS-S3-FF9900)
![Celery](https://img.shields.io/badge/Celery-5.4-37814A)
![Redis](https://img.shields.io/badge/Redis-Cache%20%2B%20Broker-DC382D)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

Melody Wings Safety accepts audio files, video files, plain-text transcripts, or Google Drive documents, and runs them through a layered detection pipeline that identifies **20 categories** of harmful behaviour — from grooming tactics and manipulation to explicit content, threats, gift-bribery, isolation, emotional exploitation, and age deception.

Every finding is scored, grouped, and surfaced in a React dashboard with confidence breakdowns, ML analysis, temporal weighting, a timeline view, and a downloadable PDF report. High-severity results trigger automatic email alerts. Real-time WebSocket progress updates keep the frontend informed during analysis.

All data is persisted to MongoDB (7 core collections, plus `users` and `counters` for auth and IDs) and AWS S3. Background processing is handled by Celery + Redis with a threading fallback for local dev.

---

## Key Features (v2.1.0)

- **Multi-input support** — Audio (.mp3/.wav/.m4a/.aac/.ogg), Video (.mp4/.mkv/.avi/.mov/.webm/.flv/.wmv), plain-text transcripts, Google Drive imports
- **20-category detection** — Compiled regex patterns covering the full grooming lifecycle
- **ML zero-shot NLI** — DistilBERT-MNLI classifier fused at 25% weight with regex confidence
- **Temporal weighting** — Late-conversation findings score higher; clustering and escalation detection
- **Leetspeak normalization** — Catches obfuscated text (m33t, s3cr3t, separator insertion)
- **Circuit breaker pattern** — Graceful degradation for Ollama and S3 failures
- **Celery task queue** — Redis-backed background processing with threading fallback
- **Real-time WebSocket progress** — Live analysis stage updates pushed to the frontend
- **Virus scanning** — ClamAV integration for uploaded file safety
- **Disk space pre-check** — Rejects uploads when disk is low
- **Credential encryption** — Google OAuth tokens encrypted at rest (Fernet/AES)
- **Database migrations** — Versioned, tracked MongoDB schema changes
- **Rate limiting** — Per-IP request throttling middleware
- **Security headers** — CSP, X-Frame-Options, HSTS-ready
- **JWT authentication** — bcrypt-hashed passwords, httpOnly cookies, configurable expiry
- **Batch upload** — Analyze multiple files in a single request
- **RAG chatbot** — ChromaDB + Ollama for per-report Q&A
- **Email alerts** — Auto-triggered on High/Critical severity with PDF attachment
- **PDF reports** — Downloadable analysis reports via ReportLab
- **Google Drive watcher** — Auto-import new files on a configurable polling interval

---

## Architecture

```mermaid
flowchart TD
    %% ─── INPUT LAYER ─────────────────────────────────────────────────────────
    subgraph INPUT["🎙️ INPUT SOURCES"]
        direction LR
        A1([🎵 Audio\n.mp3 .wav .m4a .aac .ogg])
        A2([🎬 Video\n.mp4 .mkv .avi .mov .webm .flv .wmv])
        A3([📄 Transcript\nPlain text / .txt upload])
        A4([☁️ Google Drive\n.txt / Google Docs])
    end

    %% ─── SECURITY GATE ──────────────────────────────────────────────────────
    subgraph SECURITY["🔒 UPLOAD SECURITY"]
        direction LR
        AUTH[JWT Auth\nBearer token validation]
        RATE[Rate Limiter\nPer-IP throttling]
        DISK[Disk Space Check\nMin 500 MB free]
        VIRUS[Virus Scanner\nClamAV integration]
        SIZE[Size Limit\n200 MB audio · 500 MB video]
    end

    %% ─── TASK QUEUE ─────────────────────────────────────────────────────────
    subgraph QUEUE["⚙️ TASK QUEUE"]
        direction LR
        REDIS_B[(Redis\nBroker + Result Backend)]
        CEL[Celery Workers\npool=solo · acks_late]
        BEAT[Celery Beat\nCleanup · Watcher · Recovery]
    end

    %% ─── TRANSCRIPTION ──────────────────────────────────────────────────────
    subgraph TRANSCRIPTION["① TRANSCRIPTION"]
        direction TB
        EXTRACT[PyAV\nVideo → Audio extraction\n1 MB streaming chunks]
        WHISPER[faster-whisper\nWhisper Base · CPU · int8 quantization]
        TRANSCRIPT[(Transcript Text\n+ Timeline with speaker labels)]
    end

    %% ─── DETECTION PIPELINE ─────────────────────────────────────────────────
    subgraph DETECTION["② GROOMING DETECTION PIPELINE"]
        direction TB
        LEET[🔤 Leetspeak Normalizer\nm33t→meet · s3cr3t→secret\nseparator removal · repetition collapse]
        SPLIT[Sentence Splitter\n+ Speaker Label Parser]
        PAT[📋 Pattern Matching\n20 compiled regex categories\n~200 patterns total]
        CTX[🎯 Context Classifier\n13 ContextTypes\n−0.40 to +0.50 multipliers]
        FIL[🚫 Filters\nNegation ±5 tokens\nJoke ±2 sentences]
        CONF[📊 Confidence Scorer\nbase + phrase bonus + keyword bonus\n+ context multiplier − penalties]
        ML[🧠 ML Classifier\ndistilbert-base-uncased-mnli\nZero-Shot NLI · 25% fusion weight\nLRU cache 512 entries]
        GROUP[Evidence Grouping\nDeduplication + category merge]
    end

    %% ─── RISK SCORING ────────────────────────────────────────────────────────
    subgraph SCORING["③ RISK SCORING & TEMPORAL ANALYSIS"]
        direction TB
        RISK[⚖️ Weighted Risk Scorer\nDiminishing returns\n100% → 50% → 25% → 12.5%\nCapped at 100]
        TEMPORAL[⏱️ Temporal Weighting\nEarly 0.8x · Middle 1.0x · Late 1.2x\nClustering bonus +0.15\nEscalation bonus +0.20]
        ESCALATION[📈 Escalation Detection\nProgression chains\ntrust→secrecy→meeting]
    end

    %% ─── OUTPUT GENERATION ───────────────────────────────────────────────────
    subgraph OUTPUT["④ OUTPUT GENERATION"]
        direction TB
        SEV[Severity Classifier\nSafe · Low · Moderate · High · Critical]
        RULESUM[Rule-Based Summary\nTop findings + risk breakdown]
        LLMSUM[🤖 LLM Summary\nOllama Llama 3.1\nCircuit breaker protected]
        LLMVAL[LLM Output Validator\nCross-reference with findings]
        PDF[📄 PDF Report\nReportLab · findings + charts]
        EMBED[Vector Embedding\nall-MiniLM-L6-v2\n→ ChromaDB storage]
        ALERT[📧 Email Alert\nHTML template · PDF attachment\nAuto-trigger on High/Critical]
    end

    %% ─── STORAGE LAYER ───────────────────────────────────────────────────────
    subgraph STORAGE["⑤ PERSISTENT STORAGE"]
        direction LR
        MONGO[(🍃 MongoDB Atlas\n7 collections + users + counters\nJSON Schema validation\nTTL indexes · Connection pooling)]
        S3[(☁️ AWS S3\n5 storage types\nAES-256 encryption\nPresigned URLs)]
        CHROMA[(🔮 ChromaDB\nPersistent vectors\nRAG retrieval)]
        REDIS_C[(⚡ Redis\nTTL cache · 60s default\nIn-memory fallback)]
    end

    %% ─── API LAYER ──────────────────────────────────────────────────────────
    subgraph API["⑥ REST API · FastAPI :8000"]
        direction TB
        subgraph MIDDLEWARE["Middleware Stack"]
            MW1[Request ID · Security Headers · CORS]
            MW2[API Key Auth · Rate Limiting]
        end
        subgraph ROUTES["Route Modules"]
            R1[POST /analyze · /analyze/video\n/analyze/transcript · /api/v1/analyze/batch]
            R2[GET /report · /history · /evidence\n/stats · /pdf · DELETE /report]
            R3[POST /chat · GET /analytics/summary]
            R4[POST /notify/alert · /notify/summary]
            R5[/api/v1/google-drive/*\nOAuth · Files · Import · Watcher]
            R6[/auth/login · /auth/logout · /auth/me]
        end
        WS[🔌 WebSocket /ws/progress\nReal-time analysis updates]
    end

    %% ─── FRONTEND ────────────────────────────────────────────────────────────
    subgraph FRONTEND["⑦ FRONTEND · React 19 + Vite 8 :5173"]
        direction TB
        subgraph PAGES["Pages (lazy-loaded)"]
            P1[🏠 Dashboard\nHistory · Search · Sort · Stats]
            P2[📤 Upload\nDrag-drop · Progress · Status polling]
            P3[📊 Report\n6 tabs · Risk ring · Chatbot sidebar]
            P4[☁️ Google Drive\nOAuth · Browser · Watcher]
            P5[🔐 Login\nJWT · Protected routes]
        end
        subgraph LIBS["Libraries"]
            L1[Recharts · Lucide · react-hot-toast]
            L2[Axios · React Router 7]
        end
    end

    %% ─── CONNECTIONS ─────────────────────────────────────────────────────────

    %% Input → Security → Queue
    A1 & A2 & A3 --> SECURITY
    A4 --> SECURITY
    SECURITY --> QUEUE

    %% Queue → Transcription
    CEL --> EXTRACT
    CEL --> WHISPER
    A2 -.-> EXTRACT --> WHISPER
    A1 -.-> WHISPER
    WHISPER --> TRANSCRIPT
    A3 -.-> TRANSCRIPT
    A4 -.-> TRANSCRIPT

    %% Transcription → Detection
    TRANSCRIPT --> LEET --> SPLIT --> PAT --> CTX --> FIL --> CONF
    CONF --> ML
    ML --> GROUP
    CONF --> GROUP

    %% Detection → Scoring
    GROUP --> RISK --> TEMPORAL --> ESCALATION

    %% Scoring → Output
    ESCALATION --> SEV & RULESUM & LLMSUM
    LLMSUM --> LLMVAL
    SEV & RULESUM & LLMVAL --> PDF
    TRANSCRIPT --> EMBED

    %% Output → Storage
    PDF --> MONGO & S3
    GROUP --> MONGO
    EMBED --> CHROMA
    A1 & A2 --> S3
    ALERT --> MONGO

    %% Storage → API
    MONGO --> ROUTES
    CHROMA --> R3
    REDIS_C --> ROUTES
    S3 --> R2

    %% API → Frontend
    API --> FRONTEND
    WS --> FRONTEND

    %% Beat tasks
    BEAT --> REDIS_B
    REDIS_B --> CEL

    %% Alert trigger
    SEV -->|High/Critical| ALERT
```

---

## Repository Structure

```
Melody Wings Safety/
├── backend/                        # FastAPI + Python detection pipeline
│   ├── app.py                      # Main FastAPI app — routes, middleware, startup/shutdown
│   ├── auth.py                     # JWT authentication — login, token validation, get_current_user
│   ├── config.py                   # Paths, SMTP, S3, MongoDB, Google Drive config
│   ├── celery_app.py               # Celery configuration — Redis broker, threading fallback
│   ├── celery_beat_schedule.py     # Periodic task schedule (cleanup, watcher)
│   ├── create_admin.py             # CLI script to create/reset admin user in MongoDB
│   ├── finetune_model.py           # Fine-tune the NLI model on custom grooming data
│   ├── requirements.txt            # Python dependencies
│   ├── start.bat                   # Windows one-click server start
│   ├── run_server.py               # Alternative uvicorn launcher
│   ├── test_pipeline.py            # Interactive CLI pipeline tester
│   ├── test_email.py               # 4-step SMTP integration test
│   ├── debug_env.py                # Low-level SMTP credential debugger
│   ├── .env.example                # Environment variable template
│   │
│   ├── api/                        # Route modules (versioned + auth + notifications)
│   │   ├── audio_analysis_routes.py    # /api/v1/* — analyze, batch, history, report, chat
│   │   ├── google_drive_routes.py      # /api/v1/google-drive/* — OAuth, files, import, watcher
│   │   ├── auth_routes.py             # /auth/* — login, logout, me
│   │   ├── notification_routes.py     # /api/v1/notify/* — alert + summary emails
│   │   └── analytics_routes.py        # /api/v1/analytics/* — cross-report aggregation
│   │
│   ├── tasks/                      # Celery task definitions
│   │   ├── analysis_tasks.py       # Audio, video, transcript, Drive import pipelines
│   │   └── maintenance_tasks.py    # Cleanup, watcher polling, stuck-job recovery
│   │
│   ├── services/
│   │   ├── audio_safety_service.py     # Async pipeline orchestration (sync /api/v1 path)
│   │   └── google_drive_service.py     # Google OAuth2 + Drive/Docs file access
│   │
│   ├── schemas/
│   │   └── audio_analysis_schemas.py   # Pydantic request/response models
│   │
│   ├── middleware/
│   │   ├── rate_limiter.py         # Per-IP rate limiting middleware
│   │   └── __init__.py
│   │
│   ├── modules/
│   │   ├── patterns.py             # 20-category compiled regex library
│   │   ├── context_analyzer.py     # ContextType enum + multipliers
│   │   ├── confidence.py           # Confidence scoring engine
│   │   ├── filters.py              # NegationFilter + JokeFilter
│   │   ├── ml_classifier.py        # Zero-shot NLI (DistilBERT-MNLI)
│   │   ├── grooming_detector.py    # Main pipeline orchestrator
│   │   ├── evidence_grouping.py    # Deduplication + category merging
│   │   ├── risk_scorer.py          # Weighted risk scoring (0–100)
│   │   ├── severity_classifier.py  # Score → Safe/Low/Moderate/High/Critical
│   │   ├── temporal_weighting.py   # Position-based + clustering + escalation scoring
│   │   ├── leetspeak_normalizer.py # Obfuscation normalization (leetspeak, separators)
│   │   ├── analysis_pipeline.py    # Unified analysis pipeline (Celery entry point)
│   │   ├── summarizer.py           # Rule-based summary
│   │   ├── llm_summarizer.py       # Ollama Llama 3.1 summary
│   │   ├── llm_output_validator.py # LLM output validation
│   │   ├── report_generator.py     # PDF report generation
│   │   ├── transcriber.py          # Faster-Whisper transcription + PyAV video extraction
│   │   ├── evidence_extractor.py   # Evidence list extraction
│   │   ├── stats.py                # Statistics + timeline + ML agreement
│   │   ├── chatbot.py              # RAG chatbot (ChromaDB + Ollama)
│   │   ├── email_notifier.py       # SMTP alert + summary HTML emails
│   │   ├── s3_storage.py           # AWS S3 upload / presign / delete
│   │   ├── drive_watcher.py        # Google Drive background auto-import watcher
│   │   ├── cache.py                # Redis-backed TTL cache with in-memory fallback
│   │   ├── circuit_breaker.py      # Circuit breaker for Ollama + S3
│   │   ├── credential_encryption.py # Fernet encryption for OAuth credentials at rest
│   │   ├── virus_scanner.py        # ClamAV virus scanning for uploads
│   │   ├── disk_space_checker.py   # Pre-upload disk space validation
│   │   ├── websocket_manager.py    # Real-time WebSocket progress updates
│   │   └── file_cleanup.py         # Upload file cleanup daemon
│   │
│   ├── database/
│   │   ├── mongo.py                # MongoDB client — 7-collection schema + read helpers
│   │   └── migrations.py           # Versioned database migration system
│   │
│   ├── models/
│   │   └── grooming-nli-finetuned/ # Fine-tuned DistilBERT model checkpoints
│   │
│   └── examples/
│       ├── test_script_bad.txt     # CRITICAL — all categories triggered
│       ├── test_script_medium.txt  # MODERATE — ambiguous online chat
│       ├── test_script_good.txt    # LOW — safe classroom exchange
│       └── run_test_scripts.py     # Pipeline test runner
│
└── frontend/                       # React 19 + Vite 8 dashboard
    ├── src/
    │   ├── pages/
    │   │   ├── Dashboard.jsx       # History table — search, sort, stat cards, delete
    │   │   ├── Report.jsx          # 6-tab report — Overview, Findings, Evidence,
    │   │   │                       #   Timeline, Analytics, Raw Data + Chatbot sidebar
    │   │   ├── Upload.jsx          # Drag-and-drop upload (audio + video + transcript)
    │   │   ├── Login.jsx           # JWT login page — username/password form
    │   │   └── GoogleDrive.jsx     # Google Drive OAuth2 connect + file browser + watcher
    │   ├── components/
    │   │   ├── Chatbot.jsx         # AI chatbot sidebar (RAG)
    │   │   └── ErrorBoundary.jsx   # React error boundary
    │   ├── api.js                  # Axios client — all API calls + JWT token helpers
    │   └── App.jsx                 # Router + navigation + auth guard
    └── vite.config.js              # Dev proxy /api/v1/* → :8000
```

---

## Detection Categories

The pipeline detects **20 categories** across the full grooming lifecycle — from initial contact and trust-building through to escalation, coercion, and explicit harm.

### Core Grooming Tactics

| Category | Severity | Weight | Description |
|---|---|---|---|
| `explicit_content` | **Critical** | 25 | Sexual solicitation, nude requests, sexting, CSAM references |
| `threats_coercion` | **Critical** | 22 | Blackmail, photo threats, reputation threats, "do it or else" |
| `meeting` | **Critical** | 20 | Arranging in-person contact, "sneak out", "come to my place" |
| `address` | **Critical** | 20 | Requesting physical location, home address, zip code |
| `emotional_exploitation` | **Critical** | 18 | Guilt-tripping, "you're all I have", self-harm threats as control |
| `isolation` | **Critical** | 16 | Discrediting friends/family, "you only need me", encouraging withdrawal |
| `secrecy` | **Critical** | 15 | "Don't tell anyone", "delete these messages", "our secret" |
| `manipulation` | **Critical** | 10 | Coercion, conditional threats, peer pressure, proof demands |

### Information Gathering

| Category | Severity | Weight | Description |
|---|---|---|---|
| `personal_information` | **High** | 18 | Phone numbers, email, social handles, real name, age, passwords |
| `parent_monitoring` | **High** | 15 | Questions about parental supervision of messages/phone |
| `age_deception` | **High** | 14 | "I'm the same age", "age is just a number", "you're mature for your age" |
| `desensitization` | **High** | 14 | "It's normal", "everyone does it", minimising inappropriate behaviour |
| `gift_bribery` | **High** | 12 | Gift offers, money, gaming currency, "I'll buy you anything" |
| `school` | **High** | 10 | School name, grade, dismissal time, teacher names |
| `routine` | **High** | 10 | Daily schedule, walk-home route, when alone at home |
| `video_call` | **High** | 10 | Video call requests, camera requests, selfie demands |

### Relationship & Trust Building

| Category | Severity | Weight | Description |
|---|---|---|---|
| `relationship_building` | **High** | 5 | Building personal dependency, "you're special to me" |
| `gaming_luring` | **Medium** | 10 | Roblox/Fortnite contact, "join my private server", moving to DMs |
| `bad_language` | **Medium** | 8 | Profanity, slurs, hate speech, aggressive/threatening language |
| `trust_building` | **Medium** | 5 | "Trust me", "I'm here for you", "you can tell me anything" |

---

## Risk Scoring

Risk scores are calculated on a **0–100 scale** using a weighted, diminishing-returns formula with temporal weighting:

```
effective_score = weight × confidence × temporal_multiplier    (1st occurrence)
effective_score = weight × confidence × temporal_multiplier × DR  (repeated)
total_score     = Σ effective_scores, capped at 100
```

**Temporal weighting** — findings in the last 25% of a conversation receive a 1.2x multiplier (escalation phase). Findings in the first 25% receive 0.8x (exploratory phase). Clustering bonus (+0.15) applies when 3+ findings appear within 10% of the conversation. Escalation bonus (+0.20) applies when severity increases over time.

**Diminishing returns** — repeated occurrences of the same category are progressively down-weighted (100% → 50% → 25% → 12.5% → …).

| Risk Level | Score Range | Meaning |
|---|---|---|
| Safe | 0–20 | No significant indicators |
| Low | 21–40 | Minor concerns, may warrant monitoring |
| Moderate | 41–60 | Multiple indicators, increased monitoring recommended |
| High | 61–80 | Significant patterns, immediate review recommended |
| Critical | 81–100 | Severe behaviour, urgent intervention required |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI 0.136 + Uvicorn 0.47 |
| Task Queue | Celery 5.4 + Redis (threading fallback for local dev) |
| Transcription | Faster-Whisper 1.2 (base model, CPU, int8) |
| Video Audio Extraction | PyAV (streamed, 1 MB chunks) |
| Pattern Detection | Python `re` — compiled regex, 20 categories |
| Text Normalization | Leetspeak normalizer (character substitution, separator removal) |
| ML Classifier | `typeform/distilbert-base-uncased-mnli` — Zero-Shot NLI |
| LLM Summary | Ollama — Llama 3.1 (with output validation) |
| Vector Store | ChromaDB (persistent) |
| Embeddings | SentenceTransformers `all-MiniLM-L6-v2` |
| Primary Database | MongoDB Atlas — 7 collections + versioned migrations |
| Caching | Redis-backed TTL cache (in-memory fallback) |
| File Storage | AWS S3 — 5 storage types, AES-256 encrypted |
| Virus Scanning | ClamAV via pyclamd |
| Email | SMTP (Gmail / any provider) — HTML alert + summary templates |
| PDF | ReportLab |
| Google Drive | Google Drive API + Google Docs API (OAuth2, encrypted credentials) |
| Real-time Updates | WebSocket (/ws/progress) |
| Rate Limiting | Custom middleware (per-IP, configurable) |
| Circuit Breaker | Custom implementation for Ollama + S3 |
| Authentication | JWT (HS256) + bcrypt + httpOnly cookies |
| Frontend | React 19 + Vite 8 |
| Charts | Recharts 3 |
| Icons | Lucide React |
| Notifications | react-hot-toast |

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Redis *(optional — for Celery task queue and caching; falls back to threading + in-memory)*
- [Ollama](https://ollama.com) *(optional — for LLM summaries and chatbot)*

### 1. Clone

```bash
git clone https://github.com/umangjzx/transcript-Analysis.git
cd transcript-Analysis
```

### 2. Backend

```bash
cd backend

python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env

# Create the admin user (required for JWT auth)
python create_admin.py

# Start the server
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

On Windows you can also use the included batch script:

```bash
start.bat
```

Backend runs at **http://localhost:8000**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 3. Celery Workers (optional, recommended)

```bash
# Start a Celery worker (processes analysis tasks in background)
celery -A celery_app worker --loglevel=info --pool=solo

# Start Celery Beat (periodic tasks: cleanup, watcher)
celery -A celery_app beat --loglevel=info
```

If Redis is not available, set `USE_CELERY=false` in `.env` — tasks will run synchronously via threading.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173**

### 5. Ollama (optional)

```bash
ollama pull llama3.1
```

If Ollama is not running, the system falls back to the rule-based summary. All other features work without it.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. All integrations are optional — the core analysis pipeline runs without them.

```env
# ── Authentication ────────────────────────────────────────────────────────────
JWT_SECRET=<generate: python -c "import secrets; print(secrets.token_hex(32))">
JWT_EXPIRE_MINUTES=480
ENV=development                   # Set to "production" for strict startup checks

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
MONGO_DB_NAME=audio_safety_db
MONGO_POOL_MIN_SIZE=5
MONGO_POOL_MAX_SIZE=50

# ── Redis / Celery ────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
USE_CELERY=true                   # false = threading fallback (no Redis needed)

# ── AWS S3 ────────────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

# ── SMTP Email ────────────────────────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_NAME=Melody Wings Safety
ALERT_RECIPIENTS=analyst@yourorg.com,supervisor@yourorg.com
ALERT_SEVERITY=High
APP_URL=http://localhost:5173

# ── Feature Flags ─────────────────────────────────────────────────────────────
ENABLE_ML_CLASSIFIER=false        # true after ~400 MB model is cached
ENABLE_LLM_SUMMARY=true           # false to skip Ollama entirely
MAX_UPLOAD_MB=200
MAX_VIDEO_UPLOAD_MB=500
UPLOAD_TTL_HOURS=24

# ── Security ──────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
API_KEY=                          # leave blank to disable in dev
COOKIE_SECURE=false               # true in production (requires HTTPS)
CREDENTIAL_ENCRYPTION_KEY=        # encrypts Google OAuth tokens at rest

# ── Virus Scanning ────────────────────────────────────────────────────────────
ENABLE_VIRUS_SCAN=false
CLAMAV_HOST=localhost
CLAMAV_PORT=3310
VIRUS_SCAN_FAIL_CLOSED=false

# ── Circuit Breaker ───────────────────────────────────────────────────────────
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2

# ── Google Drive ──────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/google-drive/callback
DRIVE_AUTO_WATCH=false
DRIVE_POLL_INTERVAL_SECONDS=120
DRIVE_WATCH_FOLDER_ID=

# ── Disk Space ────────────────────────────────────────────────────────────────
MIN_DISK_SPACE_MB=500

# ── Log Rotation ──────────────────────────────────────────────────────────────
LOG_MAX_SIZE_MB=50
LOG_BACKUP_COUNT=5

# ── TTL Indexes ───────────────────────────────────────────────────────────────
AUDIT_LOG_TTL_DAYS=90
PROCESSING_STATUS_TTL_DAYS=30
```

> **Gmail tip:** Generate a 16-character App Password at https://myaccount.google.com/apppasswords — 2FA must be enabled first.

---

## Authentication

Melody Wings Safety uses **JWT (JSON Web Token)** authentication for the frontend and an optional **X-API-Key** header for direct API/script access.

### How it works

- Admin credentials stored in MongoDB (`users` collection), passwords bcrypt-hashed (12 rounds)
- On login, the server issues a signed HS256 JWT valid for `JWT_EXPIRE_MINUTES` (default 8 hours)
- The frontend stores the token in `localStorage` and attaches it as a `Bearer` token on every request
- The `get_current_user` FastAPI dependency validates the JWT on protected routes
- JWT is also set in an httpOnly cookie for additional security
- If `JWT_SECRET` is not set, auth is disabled entirely (dev mode)
- Server refuses to start without `JWT_SECRET` when `ENV=production`

### Setup

```bash
# 1. Add to backend/.env:
JWT_SECRET=<run: python -c "import secrets; print(secrets.token_hex(32))">
JWT_EXPIRE_MINUTES=480

# 2. Create the admin user:
cd backend
python create_admin.py
```

### Auth endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | `{"username": "...", "password": "..."}` → JWT + user info |
| `POST` | `/auth/logout` | Clears httpOnly cookie; logged to audit |
| `GET` | `/auth/me` | Returns current user from Bearer JWT |

---

## Storage

### MongoDB — Primary Store (7 core collections)

| Collection | Contents |
|---|---|
| `meeting_metadata` | Filename, date, duration, S3 URL, status, pdf_path |
| `transcripts` | Full transcript, speaker segments, timestamps, word count |
| `analysis_results` | Risk score, severity, LLM summary, rule summary, stats, evidence, temporal data |
| `safety_findings` | Per-finding category, evidence, confidence, context type, ML fields |
| `action_items` | High/critical findings requiring action |
| `processing_status` | Pipeline stage, started_at, completed_at, errors |
| `audit_logs` | All events — uploads, completions, failures, emails sent |

**Supporting collections:** `users` (admin accounts), `counters` (atomic auto-increment IDs), `_migrations` (migration tracking)

### AWS S3 (5 storage types, AES-256 encrypted)

| Type | S3 Prefix | Description |
|---|---|---|
| Original recordings | `recordings/YYYY/MM/` | Uploaded audio files |
| Extracted audio | `recordings/YYYY/MM/` | Audio from video uploads |
| PDF reports | `reports/YYYY/MM/` | Generated analysis PDFs |
| Exports | `exports/YYYY/MM/` | CSV / JSON / XLSX exports |
| Backups | `backups/YYYY/MM/` | Long-term archives |

---

## API Reference

### Core Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Full health check — MongoDB, S3, Redis, Ollama, Whisper, ChromaDB, disk |
| `POST` | `/analyze` | Upload audio — background pipeline via Celery |
| `POST` | `/analyze/video` | Upload video — audio extracted, then analyzed |
| `POST` | `/analyze/transcript` | Submit plain-text transcript (JSON or multipart) |
| `GET` | `/report/{id}/status` | Poll: `PROCESSING` / `COMPLETED` / `FAILED` |
| `GET` | `/history` | Paginated history with TTL cache |
| `GET` | `/report/{id}` | Full report — transcript, findings, evidence, stats, summaries |
| `GET` | `/report/{id}/evidence` | Evidence list with severity, risk_score, context_type |
| `GET` | `/report/{id}/stats` | Statistics — categories, confidence, ML stats, timeline |
| `GET` | `/report/{id}/pdf` | Download PDF report |
| `DELETE` | `/report/{id}` | Delete from MongoDB + S3 + local PDF + ChromaDB |
| `POST` | `/chat` | RAG chatbot — `{answer, sources, confidence}` |
| `GET` | `/analytics/summary` | Cross-report aggregation |
| `WS` | `/ws/progress` | Real-time analysis progress updates |

### Versioned Routes (/api/v1)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/analyze` | Synchronous analysis (Pydantic response) |
| `POST` | `/api/v1/analyze/batch` | Batch upload — multiple files in one request |
| `GET` | `/api/v1/history` | Paginated history (JWT required) |
| `GET` | `/api/v1/report/{id}` | Full report (JWT required) |
| `GET` | `/api/v1/report/{id}/evidence` | Evidence (JWT required) |
| `GET` | `/api/v1/report/{id}/stats` | Statistics |
| `GET` | `/api/v1/report/{id}/pdf` | Download PDF |
| `POST` | `/api/v1/chat` | RAG chatbot |

### Notifications

| Method | Path | Description |
|---|---|---|
| `POST` | `/notify/alert/{id}` | Send/re-send alert email (accepts `recipients` override) |
| `POST` | `/notify/summary/{id}` | Send full analysis summary email |

### Google Drive

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/google-drive/auth-url` | OAuth2 consent URL |
| `GET` | `/api/v1/google-drive/callback` | OAuth2 redirect handler |
| `GET` | `/api/v1/google-drive/status` | Authentication status |
| `DELETE` | `/api/v1/google-drive/logout` | Revoke credentials |
| `GET` | `/api/v1/google-drive/files` | List importable files |
| `POST` | `/api/v1/google-drive/import` | Import file as transcript |
| `GET` | `/api/v1/google-drive/watcher/status` | Watcher state |
| `POST` | `/api/v1/google-drive/watcher/start` | Start auto-import |
| `POST` | `/api/v1/google-drive/watcher/stop` | Stop auto-import |

### Examples

```bash
# Upload and analyze audio
curl -X POST http://localhost:8000/analyze -F "file=@conversation.mp3"

# Upload video
curl -X POST http://localhost:8000/analyze/video -F "file=@recording.mp4"

# Submit transcript
curl -X POST http://localhost:8000/analyze/transcript \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Speaker A: keep this between us...", "filename": "chat.txt"}'

# Poll status
curl http://localhost:8000/report/12/status

# Get full report
curl http://localhost:8000/report/12

# Ask chatbot
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"report_id": 12, "question": "What secrecy phrases were used?"}'

# Send alert email
curl -X POST http://localhost:8000/notify/alert/12

# Google Drive import
curl -X POST http://localhost:8000/api/v1/google-drive/import \
  -H "Content-Type: application/json" \
  -d '{"file_id": "1A2B3C...", "file_name": "chat.txt", "mime_type": "text/plain"}'
```

---

## How the Pipeline Works

```
Audio/Video/Transcript/Google Drive
  └─► Faster-Whisper transcription (audio/video only)
        └─► Leetspeak normalization (obfuscation removal)
              └─► Sentence splitting + speaker label parsing
                    └─► Regex pattern matching (20 categories)
                          └─► Context classification (ContextType multiplier)
                                └─► Negation filter (token-scoped ±5 tokens)
                                      └─► Joke filter (±2 sentence window)
                                            └─► Confidence scoring
                                                  └─► ML zero-shot NLI (25% fusion weight)
                                                        └─► Evidence grouping + deduplication
                                                              └─► Weighted risk scoring (0–100)
                                                                    └─► Temporal weighting (position + clustering)
                                                                          └─► Severity classification
                                                                                └─► Rule summary + LLM summary (validated)
                                                                                      └─► PDF + MongoDB + S3 + ChromaDB
                                                                                            └─► Auto email alert (if High/Critical)
                                                                                                  └─► WebSocket progress notification
```

### Key design decisions

- **No role-based assumptions** — speaker labels stored for audit only; same sentence scores identically regardless of speaker
- **Leetspeak normalization** — catches obfuscated bypass attempts (m33t, s3cr3t, separator insertion) before pattern matching
- **Token-scoped negation** — "I did not ask for your address" is negated; "I never lie but I want your address" is not
- **Temporal weighting** — late-conversation findings score higher (escalation phase); clustering bonus for concentrated findings
- **Diminishing returns** — repeated category occurrences progressively down-weighted
- **Circuit breaker** — Ollama and S3 failures don't cascade; automatic recovery after cooldown
- **Graceful degradation** — MongoDB, S3, SMTP, Ollama, Redis all optional; core analysis always runs
- **Background processing** — all analysis runs via Celery tasks; client polls status or receives WebSocket updates
- **Video privacy** — video files streamed in 1 MB chunks, deleted immediately after audio extraction

---

## Frontend

The React 19 dashboard has five routes:

| Route | Page | Description |
|---|---|---|
| `/login` | Login | JWT login form with show/hide toggle; public route |
| `/` | Dashboard | History table with live search, sortable columns, 4 stat cards, delete action |
| `/upload` | Analyze Audio | Drag-and-drop upload (audio/video/transcript) with progress bar |
| `/report/:id` | Report | Full analysis — 6 tabs + chatbot sidebar |
| `/google-drive` | Google Drive | OAuth2 connect, file browser, import, watcher controls |

### Report Page Tabs

| Tab | Contents |
|---|---|
| **Overview** | Risk ring (animated 0–100), severity badge, LLM summary, rule summary, category breakdown |
| **Findings** | Grouped findings with confidence bars, matched text, context type, filter flags, ML agreement |
| **Evidence Log** | Flat evidence list — timestamp, category, severity, speaker, confidence |
| **Timeline** | Scatter chart — findings over time, colour-coded by category |
| **Analytics** | Per-report charts — category, severity, confidence, context type, speaker, ML agreement |
| **Raw Data** | Full JSON dump of the report object |

---

## Google Drive Integration

### Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Drive API** and **Google Docs API**
3. Create OAuth 2.0 credentials (type: Web application)
4. Add `http://localhost:8000/api/v1/google-drive/callback` as an Authorized Redirect URI
5. Copy Client ID and Client Secret to `backend/.env`
6. (Optional) Set `CREDENTIAL_ENCRYPTION_KEY` to encrypt stored tokens

### Auto-Watcher

Set `DRIVE_AUTO_WATCH=true` to automatically poll Drive for new files every `DRIVE_POLL_INTERVAL_SECONDS` (default 120s). Restrict to a folder with `DRIVE_WATCH_FOLDER_ID`.

---

## Security Features

- **JWT authentication** with bcrypt-hashed passwords and httpOnly cookies
- **Rate limiting** middleware (per-IP, configurable thresholds)
- **Security headers** — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- **CORS** locked to configured origins
- **Virus scanning** via ClamAV (configurable fail-open/fail-closed)
- **Credential encryption** — Google OAuth tokens encrypted at rest with Fernet
- **Disk space pre-check** before accepting uploads
- **Circuit breaker** prevents cascading failures from external services
- **Request correlation IDs** (X-Request-ID header) for tracing
- **Audit logging** — all actions tracked in MongoDB with TTL expiry
- **Secure file handling** — UUID disk names, streaming uploads, size limits
- **Database migrations** — versioned schema changes with JSON Schema validation

---

## Utility Scripts

| Script | Description |
|---|---|
| `python test_pipeline.py` | Interactive CLI — run any text through the full detection pipeline |
| `python test_email.py` | 4-step SMTP integration test (config → connect → alert → summary) |
| `python debug_env.py` | Low-level SMTP credential debugger |
| `python examples/run_test_scripts.py` | Run test scripts (bad/medium/good) through the pipeline |
| `python create_admin.py` | Create or reset the admin user in MongoDB |
| `python finetune_model.py` | Fine-tune the NLI model on custom grooming data |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "add: your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a pull request

---

## License

MIT License — see [LICENSE](LICENSE) for details.
