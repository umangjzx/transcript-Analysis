# Melody Wings Safety — Backend (v2.1.0)

Production-grade FastAPI backend for detecting grooming behaviour, explicit content, and harmful language in audio conversations. Supports audio files, video files, plain-text transcripts, and Google Drive imports.

---

## Architecture

```mermaid
flowchart TD
    subgraph INPUT["① INPUT"]
        A1([🎙️ Audio File\n.mp3 / .wav / .m4a / .aac / .ogg])
        A2([🎬 Video File\n.mp4 / .mkv / .avi / .mov / .webm])
        A3([📄 Plain-Text Transcript])
        A4([☁️ Google Drive\n.txt / Google Docs])
    end

    subgraph TRANSCRIPTION["② TRANSCRIPTION"]
        B[faster-whisper\nWhisper Base Model · CPU · int8]
        B1[(Transcript Text)]
        B2[(Timeline\nstart / end / text / speaker)]
    end

    subgraph DETECTION["③ GROOMING DETECTION PIPELINE"]
        LEET[Leetspeak Normalizer]
        C[Sentence Splitter + Speaker Parser]
        PAT[20 compiled regex categories]
        CTX[Context Classifier · 13 ContextTypes]
        FIL[Negation + Joke Filters]
        CONF[Confidence Scorer]
        ML[ML Classifier · DistilBERT-MNLI · 25% fusion]
        EG[Evidence Grouping + Dedup]
    end

    subgraph SCORING["④ RISK SCORING"]
        RS[Weighted Scorer · Diminishing Returns · Cap 100]
        TW[Temporal Weighting · Position + Clustering + Escalation]
    end

    subgraph OUTPUT["⑤ OUTPUT"]
        SV[Severity Classifier]
        SUM[Rule-Based Summary]
        LLM[LLM Summary · Ollama Llama 3.1]
        PDF[PDF Report · ReportLab]
        BOT[RAG Chatbot · ChromaDB + Ollama]
        EMAIL[Email Alert · HTML + PDF attachment]
    end

    subgraph STORAGE["⑥ STORAGE"]
        MDB[(MongoDB · 7 collections)]
        S3[(AWS S3 · 5 storage types)]
        VEC[(ChromaDB · vectors/)]
        REDIS[(Redis · cache + broker)]
    end

    A1 & A2 --> B --> B1 & B2
    A3 & A4 --> B1
    B1 --> LEET --> C --> PAT --> CTX --> FIL --> CONF --> EG
    CONF --> ML --> EG
    EG --> RS --> TW --> SV & SUM & LLM
    SV & SUM & LLM --> PDF --> MDB & S3
    B1 --> VEC --> BOT
    EG --> MDB
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.136 + Uvicorn 0.47 |
| Task Queue | Celery 5.4 + Redis (threading fallback when `USE_CELERY=false`) |
| Audio Transcription | faster-whisper 1.2 (Whisper Base, CPU, int8) |
| Video Audio Extraction | PyAV (streamed, 1 MB chunks) |
| Text Normalization | Leetspeak normalizer (character substitution, separator removal) |
| Pattern Detection | Python `re` — 20 compiled regex categories |
| ML Classifier | `typeform/distilbert-base-uncased-mnli` — Zero-Shot NLI |
| LLM Summary | Ollama — Llama 3.1 (optional, graceful fallback) |
| Vector Store | ChromaDB (persistent) |
| Embeddings | SentenceTransformers `all-MiniLM-L6-v2` |
| Primary Database | MongoDB Atlas — 7 collections + versioned migrations |
| Caching | Redis-backed TTL cache (in-memory fallback) |
| File Storage | AWS S3 — 5 storage types, AES-256 encrypted |
| Virus Scanning | ClamAV via pyclamd |
| Email | SMTP — HTML alert + summary templates |
| PDF Generation | ReportLab |
| Google Drive | Google Drive API + Docs API (OAuth2, encrypted credentials) |
| Real-time Updates | WebSocket (/ws/progress) |
| Rate Limiting | Custom middleware (per-IP, configurable) |
| Circuit Breaker | Custom implementation for Ollama + S3 |
| Authentication | JWT (HS256) + bcrypt + httpOnly cookies |
| Runtime | Python 3.10+ |

---

## Authentication

### Strategy

- Admin credentials stored in MongoDB (`users` collection), passwords bcrypt-hashed (12 rounds)
- Login issues a signed JWT valid for `JWT_EXPIRE_MINUTES` (default 8 hours)
- `get_current_user` FastAPI dependency validates the Bearer JWT on protected routes
- JWT also set in httpOnly cookie (secure, not accessible via JavaScript)
- If `JWT_SECRET` is not set, auth is disabled (dev mode)
- Server refuses to start without `JWT_SECRET` when `ENV=production`
- X-API-Key middleware kept for backward-compat with direct script access
- Account lockout after configurable failed attempts (`LOCKOUT_MAX_ATTEMPTS`)

### Auth endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | `{"username": "...", "password": "..."}` → JWT + user info |
| `POST` | `/auth/logout` | Clears httpOnly cookie; audit logged |
| `GET` | `/auth/me` | Current user from Bearer JWT |

### First-time setup

```bash
# 1. Add to .env:
JWT_SECRET=<python -c "import secrets; print(secrets.token_hex(32))">
JWT_EXPIRE_MINUTES=480

# 2. Create the admin user:
python create_admin.py
```

---

## Project Structure

```
backend/
├── app.py                          # FastAPI application — routes, middleware, startup/shutdown
├── config.py                       # Paths, SMTP, S3, MongoDB, Google Drive config
├── auth.py                         # JWT + bcrypt authentication helpers
├── celery_app.py                   # Celery configuration — Redis broker, threading fallback
├── celery_beat_schedule.py         # Periodic task schedule (cleanup, watcher)
├── create_admin.py                 # CLI script to create/reset admin user
├── finetune_model.py               # Fine-tune the NLI model on custom data
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Multi-stage Docker build (Python 3.11-slim)
├── start.bat                       # Windows one-click server start
├── .env.example                    # Environment variable template
│
├── api/                            # Route modules
│   ├── audio_analysis_routes.py    # /api/v1/* — analyze, batch, history, report, chat
│   ├── google_drive_routes.py      # /api/v1/google-drive/* — OAuth, files, import, watcher
│   ├── auth_routes.py              # /auth/* — login, logout, me
│   ├── notification_routes.py      # /api/v1/notify/* — alert + summary emails
│   └── analytics_routes.py         # /api/v1/analytics/* — cross-report aggregation
│
├── tasks/                          # Celery task definitions
│   ├── analysis_tasks.py           # Audio, video, transcript, Drive import pipelines
│   └── maintenance_tasks.py        # Cleanup, watcher polling, stuck-job recovery
│
├── services/
│   ├── audio_safety_service.py     # Async pipeline orchestration
│   └── google_drive_service.py     # Google OAuth2 + Drive/Docs file access
│
├── schemas/
│   └── audio_analysis_schemas.py   # Pydantic request/response models
│
├── middleware/
│   └── rate_limiter.py             # Per-IP rate limiting middleware
│
├── modules/                        # Core detection + infrastructure (31 files)
│   ├── patterns.py                 # 20-category compiled regex library
│   ├── context_analyzer.py         # ContextType enum + multipliers
│   ├── confidence.py               # Confidence scoring engine
│   ├── filters.py                  # NegationFilter + JokeFilter
│   ├── ml_classifier.py            # Zero-shot NLI (distilbert-mnli), LRU cache
│   ├── grooming_detector.py        # Main pipeline orchestrator
│   ├── evidence_grouping.py        # Deduplication + category merging
│   ├── risk_scorer.py              # Weighted risk scoring (0–100)
│   ├── severity_classifier.py      # Score → Safe/Low/Moderate/High/Critical
│   ├── temporal_weighting.py       # Position + clustering + escalation scoring
│   ├── leetspeak_normalizer.py     # Obfuscation normalization
│   ├── analysis_pipeline.py        # Unified pipeline (Celery entry point)
│   ├── summarizer.py               # Rule-based summary generator
│   ├── llm_summarizer.py           # Ollama Llama 3.1 summary
│   ├── llm_output_validator.py     # LLM output validation
│   ├── report_generator.py         # PDF report generation
│   ├── transcriber.py              # faster-whisper + PyAV video extraction
│   ├── evidence_extractor.py       # Evidence list extraction
│   ├── stats.py                    # Statistics + timeline + ML agreement
│   ├── chatbot.py                  # RAG chatbot (ChromaDB + Ollama)
│   ├── email_notifier.py           # SMTP alert + summary HTML emails
│   ├── s3_storage.py               # AWS S3 upload / presign / delete
│   ├── drive_watcher.py            # Google Drive background auto-import
│   ├── cache.py                    # Redis-backed TTL cache with in-memory fallback
│   ├── circuit_breaker.py          # Circuit breaker for Ollama + S3
│   ├── credential_encryption.py    # Fernet encryption for OAuth credentials
│   ├── virus_scanner.py            # ClamAV virus scanning
│   ├── disk_space_checker.py       # Pre-upload disk space validation
│   ├── websocket_manager.py        # Real-time WebSocket progress updates
│   ├── structured_logging.py       # JSON structured logging setup
│   └── file_cleanup.py             # Upload file cleanup daemon
│
├── database/
│   ├── mongo.py                    # MongoDB client — 7-collection schema + read helpers
│   └── migrations.py               # Versioned database migration system
│
├── models/
│   └── grooming-nli-finetuned/     # Fine-tuned DistilBERT model checkpoints
│
└── examples/                       # Test scripts for pipeline validation
    ├── test_script_bad.txt         # CRITICAL — all categories triggered
    ├── test_script_medium.txt      # MODERATE — ambiguous online chat
    ├── test_script_good.txt        # LOW — safe classroom exchange
    └── run_test_scripts.py         # Pipeline test runner
```

---

## Detection Categories

The pipeline detects **20 categories** across the full grooming lifecycle.

### Critical Severity

| Category | Weight | Description |
|---|---|---|
| `explicit_content` | 25 | Sexual solicitation, nude requests, sexting, CSAM references |
| `threats_coercion` | 22 | Blackmail, photo threats, reputation threats |
| `meeting` | 20 | Arranging in-person contact, "sneak out", "come to my place" |
| `address` | 20 | Requesting physical location, home address, zip code |
| `emotional_exploitation` | 18 | Guilt-tripping, self-harm threats as control |
| `isolation` | 16 | Discrediting friends/family, encouraging withdrawal |
| `secrecy` | 15 | "Don't tell anyone", "delete these messages" |
| `manipulation` | 10 | Coercion, conditional threats, peer pressure |

### High Severity

| Category | Weight | Description |
|---|---|---|
| `personal_information` | 18 | Phone, email, social handles, passwords |
| `parent_monitoring` | 15 | Questions about parental supervision |
| `age_deception` | 14 | "Age is just a number", "you're mature" |
| `desensitization` | 14 | "It's normal", "everyone does it" |
| `gift_bribery` | 12 | Gift offers, money, gaming currency |
| `video_call` | 10 | Camera requests, selfie demands |
| `school` | 10 | School name, grade, dismissal time |
| `routine` | 10 | Daily schedule, when alone at home |
| `relationship_building` | 5 | "You're special to me" |

### Medium Severity

| Category | Weight | Description |
|---|---|---|
| `gaming_luring` | 10 | "Join my private server", moving to DMs |
| `bad_language` | 8 | Profanity, slurs, hate speech |
| `trust_building` | 5 | "Trust me", "I'm here for you" |

---

## Risk Scoring

```
effective_score = weight × confidence × temporal_multiplier    (1st occurrence)
effective_score = weight × confidence × temporal_multiplier × DR  (repeated)
total_score     = Σ effective_scores, capped at 100
```

Diminishing returns: 100% → 50% → 25% → 12.5% → …

| Risk Level | Score Range |
|---|---|
| Safe | 0–20 |
| Low | 21–40 |
| Moderate | 41–60 |
| High | 61–80 |
| Critical | 81–100 |

---

## Temporal Weighting

| Phase | Position | Multiplier | Rationale |
|---|---|---|---|
| Early | First 25% | 0.8x | Exploratory, testing boundaries |
| Middle | 25–75% | 1.0x | Baseline |
| Late | Last 25% | 1.2x | Escalation phase |

**Bonuses:**
- **Clustering** (+0.15): 3+ findings within 10% of conversation length
- **Escalation** (+0.20): Severity increases over time
- **Progression detection**: Known grooming chains (trust → secrecy → meeting)

---

## Context Classification

| ContextType | Multiplier | Meaning |
|---|---|---|
| `ADMINISTRATIVE` | −0.40 | Event logistics, forms, schedules |
| `EXPLICIT_CONTENT` | +0.50 | Sexual language — highest multiplier |
| `SECRECY` | +0.40 | "Don't tell anyone", "our secret" |
| `ESCALATION` | +0.35 | Private call, move to another platform |
| `MEETING` | +0.35 | Meet up, in person, hang out |
| `MANIPULATION` | +0.30 | "They won't understand", coercion |
| `PERSONAL_INFORMATION` | +0.30 | Address, phone, email, route |
| `VIDEO_CALL` | +0.25 | Video chat, FaceTime, camera |
| `TRUST_BUILDING` | +0.20 | "I care about you", "trust me" |
| `BAD_LANGUAGE` | +0.20 | Profanity, slurs, threats |
| `INFORMATION_GATHERING` | +0.15 | Collecting personal details |
| `RELATIONSHIP_BUILDING` | +0.15 | "Special connection", "best friends" |
| `NEUTRAL` | 0.00 | No strong signal |

---

## ML Classifier

- Model: `typeform/distilbert-base-uncased-mnli` (Zero-Shot NLI)
- 13 labels mapped to detection categories
- Temperature calibration T=1.3 for better-calibrated probabilities
- Multi-label detection threshold: ≥0.15
- LRU cache: 512 entries — repeated sentences are free after first inference
- Fused at 25% weight into the final confidence score
- **Disabled by default** (`ENABLE_ML_CLASSIFIER=false`) — enable once model is cached (~400 MB)
- Fine-tuned model support via `FINETUNED_MODEL_PATH` env var

---

## Circuit Breaker

External service calls (Ollama, S3) are wrapped in circuit breakers:

| State | Behavior |
|---|---|
| **CLOSED** | Normal operation, requests pass through |
| **OPEN** | Service is down, requests fail immediately |
| **HALF_OPEN** | After cooldown, one test request allowed |

Configuration:
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD=5` — failures before opening
- `CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60` — seconds before half-open
- `CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2` — successes to close again

---

## Celery Task Queue

Background processing uses Celery with Redis as broker and result backend. Falls back to threading when `USE_CELERY=false`.

### Task Modules

| Module | Tasks |
|---|---|
| `tasks/analysis_tasks.py` | `run_audio_analysis`, `run_video_analysis`, `run_transcript_analysis`, `run_drive_import_analysis` |
| `tasks/maintenance_tasks.py` | `cleanup_old_uploads`, `drive_watcher_poll`, `recover_stuck_jobs` |

### Running Workers

```bash
celery -A celery_app worker --loglevel=info --pool=solo
celery -A celery_app beat --loglevel=info
```

---

## WebSocket Progress

Real-time analysis progress pushed to clients:

```
WS /ws/progress?report_id=12
```

Events: `analysis:started`, `analysis:progress`, `analysis:completed`, `analysis:failed`

---

## Database Migrations

Versioned, tracked MongoDB schema changes run automatically on startup:

| Migration | Description |
|---|---|
| `001_initial_indexes` | Create indexes for all collections |
| `002_schema_validation` | Add JSON Schema validation rules |
| `003_ttl_indexes` | TTL indexes for audit logs and processing status |
| `004_add_temporal_fields` | Temporal weighting fields in analysis_results |
| `005_connection_pool_config` | Document connection pool settings |

---

## Storage

### MongoDB (7 core collections)

| Collection | Contents |
|---|---|
| `meeting_metadata` | Filename, date, duration, S3 URL, pdf_path, status |
| `transcripts` | Full transcript, speaker segments, timestamps, word count |
| `analysis_results` | Risk score, severity, summaries, stats, evidence, temporal data |
| `safety_findings` | Per-finding category, evidence, confidence, context type, ML fields |
| `action_items` | High/critical findings requiring action |
| `processing_status` | Pipeline stage, started_at, completed_at, errors |
| `audit_logs` | All events — uploads, completions, failures, emails sent |

**Supporting:** `users`, `counters`, `_migrations`

### AWS S3 (5 storage types, AES-256)

| Type | S3 Prefix |
|---|---|
| Audio recordings | `recordings/YYYY/MM/` |
| Extracted audio | `recordings/YYYY/MM/` |
| PDF reports | `reports/YYYY/MM/` |
| Exports | `exports/YYYY/MM/` |
| Backups | `backups/YYYY/MM/` |

---

## API Endpoints

### Core Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Full health — MongoDB, S3, Redis, Ollama, Whisper, ChromaDB, disk |
| `POST` | `/analyze` | Upload audio — background pipeline via Celery |
| `POST` | `/analyze/video` | Upload video — audio extracted, then analyzed |
| `POST` | `/analyze/transcript` | Submit transcript (JSON or multipart .txt) |
| `GET` | `/report/{id}/status` | Poll: PROCESSING / COMPLETED / FAILED |
| `GET` | `/history` | Paginated history with TTL cache |
| `GET` | `/report/{id}` | Full report |
| `GET` | `/report/{id}/evidence` | Evidence list |
| `GET` | `/report/{id}/stats` | Statistics |
| `GET` | `/report/{id}/pdf` | Download PDF |
| `DELETE` | `/report/{id}` | Delete from MongoDB + S3 + local + ChromaDB |
| `POST` | `/chat` | RAG chatbot |
| `GET` | `/analytics/summary` | Cross-report aggregation |
| `WS` | `/ws/progress` | Real-time progress updates |

### Versioned Routes (/api/v1)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/analyze` | Synchronous analysis (Pydantic response) |
| `POST` | `/api/v1/analyze/batch` | Batch upload (up to 20 files) |
| `GET` | `/api/v1/history` | Paginated history (JWT required) |
| `GET` | `/api/v1/report/{id}` | Full report (JWT required) |
| `GET` | `/api/v1/report/{id}/evidence` | Evidence (JWT required) |
| `GET` | `/api/v1/report/{id}/stats` | Statistics |
| `GET` | `/api/v1/report/{id}/pdf` | Download PDF |
| `POST` | `/api/v1/chat` | RAG chatbot |

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

### Notifications

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/notify/alert/{id}` | Send/re-send alert email |
| `POST` | `/api/v1/notify/summary/{id}` | Send full analysis summary email |

---

## Security Features

- **JWT authentication** — bcrypt-hashed passwords, HS256 signing, httpOnly cookies
- **Account lockout** — configurable max attempts and lockout duration
- **Rate limiting** — per-IP middleware with configurable thresholds
- **Security headers** — CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- **CORS** — locked to configured origins only
- **Virus scanning** — ClamAV integration (configurable fail-open/fail-closed)
- **Credential encryption** — Google OAuth tokens encrypted at rest with Fernet (AES-128-CBC)
- **Disk space pre-check** — rejects uploads when disk is below threshold
- **Circuit breaker** — prevents cascading failures from Ollama/S3
- **Request correlation IDs** — X-Request-ID header for tracing
- **Audit logging** — all actions tracked in MongoDB with TTL expiry
- **Secure file handling** — UUID disk names, streaming uploads (1 MB chunks), size limits
- **Stuck-job recovery** — PROCESSING jobs older than 30 min marked FAILED on startup
- **Graceful shutdown** — closes MongoDB pool, Redis connections, resets circuit breakers
- **Structured logging** — JSON format in production with configurable log rotation

---

## Running the Server

### Prerequisites

```bash
pip install -r requirements.txt

# Redis (optional — for Celery + caching)
# Install from https://redis.io or use Docker: docker run -p 6379:6379 redis

# Ollama (optional — for LLM summaries and chatbot)
ollama pull llama3.1
```

### Start

```bash
# Server
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# Celery worker (optional, recommended)
celery -A celery_app worker --loglevel=info --pool=solo

# Celery Beat (optional — periodic tasks)
celery -A celery_app beat --loglevel=info
```

Or on Windows: `start.bat`

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker

```bash
# Build and run via docker-compose (from project root)
docker compose up backend
```

The Dockerfile uses a multi-stage build with Python 3.11-slim, installs ffmpeg and system deps, then PyTorch CPU-only + requirements.txt. Runs with 2 Uvicorn workers.

### Supported input formats

**Audio:** `.mp3` `.wav` `.m4a` `.aac` `.ogg`
**Video:** `.mp4` `.mkv` `.avi` `.mov` `.webm` `.flv` `.wmv`
**Text:** Plain-text transcript via `POST /analyze/transcript` or Google Drive import

---

## Environment Variables

See `.env.example` for the full documented list. Key sections:

- **Authentication** — JWT_SECRET, JWT_EXPIRE_MINUTES, API_KEY, COOKIE_SECURE, LOCKOUT_MAX_ATTEMPTS, LOCKOUT_DURATION_MINUTES
- **MongoDB** — MONGO_URI, MONGO_DB_NAME, pool settings (min/max size, idle time, wait queue timeout)
- **Redis/Celery** — REDIS_URL, CELERY_BROKER_URL, USE_CELERY
- **AWS S3** — credentials, region, bucket name
- **SMTP** — host, port, user, password, recipients, severity threshold
- **Feature flags** — ENABLE_ML_CLASSIFIER, ENABLE_LLM_SUMMARY, upload limits
- **Google Drive** — OAuth credentials, watcher settings, encryption key
- **Security** — ALLOWED_ORIGINS, virus scanning, credential encryption, circuit breaker
- **Operations** — disk space, log rotation, TTL indexes, structured logging

---

## Test Scripts

```bash
python examples/run_test_scripts.py
```

| Script | Expected Score | Severity |
|---|---|---|
| `test_script_bad.txt` | 100 | CRITICAL |
| `test_script_medium.txt` | ~53 | MODERATE |
| `test_script_good.txt` | 0 | LOW |

### Interactive Pipeline Tester

```bash
python test_pipeline.py
```

Runs any text through the full detection pipeline interactively with a lower confidence threshold (0.15).

---

## Design Principles

- **No role-based assumptions** — speaker labels stored for audit only
- **Token-scoped negation** — negation only suppresses within ±5 tokens
- **Leetspeak normalization** — catches obfuscated bypass attempts before pattern matching
- **Temporal weighting** — late-conversation findings score higher (escalation phase)
- **Diminishing returns** — repeated categories progressively down-weighted
- **Circuit breaker** — external service failures don't cascade
- **Graceful degradation** — MongoDB, S3, SMTP, Ollama, Redis all optional
- **Background processing** — all analysis via Celery tasks with WebSocket progress
- **Video privacy** — video files streamed, deleted immediately after audio extraction
