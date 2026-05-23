# Audio Safety Analyzer

A production-grade backend system for detecting grooming behaviour, explicit content, and harmful language in audio conversations. Supports Discord voice chats, WhatsApp calls, Zoom meetings, gaming voice chats, podcasts, workplace calls, and any general audio source.

---

## Architecture

```mermaid
flowchart TD
    subgraph INPUT["① INPUT"]
        A([🎙️ Audio File\n.mp3 / .wav / .m4a / .aac / .ogg])
    end

    subgraph TRANSCRIPTION["② TRANSCRIPTION"]
        B[faster-whisper\nWhisper Base Model]
        B1[(Transcript Text)]
        B2[(Timeline\nstart/end/text)]
    end

    subgraph DETECTION["③ GROOMING DETECTION PIPELINE"]
        direction TB
        C[Sentence Splitter\nSpeaker Label Parser]
        subgraph PATTERNS["Pattern Detection — patterns.py"]
            P1[parent_monitoring] P2[secrecy] P3[trust_building]
            P4[relationship_building] P5[manipulation] P6[video_call]
            P7[meeting] P8[address] P9[school] P10[routine]
            P11[explicit_content] P12[bad_language]
        end
        subgraph CONTEXT["Context Classification — context_analyzer.py"]
            CT1[ADMINISTRATIVE -0.40] CT2[SECRECY +0.40]
            CT3[EXPLICIT_CONTENT +0.50] CT4[MANIPULATION +0.30]
            CT5[MEETING +0.35] CT6[ESCALATION +0.35]
        end
        subgraph FILTERS["Filters — filters.py"]
            F1[NegationFilter token-scoped ±5]
            F2[JokeFilter ±2 sentence window]
        end
        subgraph CONFIDENCE["Confidence Scoring — confidence.py"]
            CS1[Base + Exact Phrase +0.15 + Keyword +0.10]
            CS2[± Context Multiplier]
            CS3[- Negation -0.40 / Joke -0.50]
            CS4[Clamp 0.0 – 1.0]
        end
        subgraph ML["ML Classifier — ml_classifier.py"]
            ML1[distilbert-base-uncased-mnli Zero-Shot NLI]
            ML2[13 Labels · fuse_with_regex 25% weight]
        end
        EG[Evidence Grouping\nDeduplication + Category Merge]
    end

    subgraph SCORING["④ RISK SCORING"]
        RS1[WeightedRiskScorer\nDiminishing Returns · cap 100]
        RS2{Risk Level}
    end

    subgraph STORAGE["⑤ STORAGE"]
        DB[(SQLite\nanalysis.db)]
        MDB[(MongoDB\n7 collections)]
        S3[(AWS S3\n5 storage types)]
        VEC[(ChromaDB\nVector Store)]
    end

    subgraph OUTPUT["⑥ OUTPUT"]
        SV[Severity Classifier]
        ST[Stats Generator]
        SUM[Rule Summary]
        LLM[LLM Summary\nOllama llama3.1]
        PDF[PDF Report]
        BOT[RAG Chatbot]
        EMAIL[Email Notifier\nAlert + Summary]
    end

    subgraph API["⑦ API — FastAPI"]
        EP1[POST /analyze]
        EP2[GET /history]
        EP3[GET /report/id]
        EP4[GET /report/id/pdf]
        EP5[POST /chat]
        EP6[POST /notify/alert/id]
        EP7[POST /notify/summary/id]
        EP8[GET /analytics/summary]
    end

    A --> B --> B1 & B2
    B1 --> C --> PATTERNS --> CONTEXT --> FILTERS --> CONFIDENCE --> EG
    CONFIDENCE --> ML --> EG
    EG --> RS1 --> RS2
    RS1 --> SV & ST & SUM & LLM & PDF
    B1 --> VEC --> BOT
    SV & ST & SUM & LLM & PDF --> DB & MDB
    A --> S3
    PDF --> S3
    DB --> EP2 & EP3 & EP4
    BOT --> EP5
    EMAIL --> EP6 & EP7
    DB --> EP8
```

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Detection Categories](#detection-categories)
- [Context Classification](#context-classification)
- [Confidence Scoring](#confidence-scoring)
- [ML Classifier](#ml-classifier)
- [Risk Scoring](#risk-scoring)
- [Filters](#filters)
- [Evidence Grouping](#evidence-grouping)
- [Storage — SQLite + MongoDB + S3](#storage--sqlite--mongodb--s3)
- [Email Notifications](#email-notifications)
- [Modules Reference](#modules-reference)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Running the Server](#running-the-server)
- [Test Scripts](#test-scripts)
- [Interactive Pipeline Tester](#interactive-pipeline-tester)
- [Design Principles](#design-principles)

---

## Overview

The Audio Safety Analyzer processes audio files through a multi-stage pipeline:

1. **Transcribe** audio using Faster-Whisper
2. **Detect** harmful patterns across 12 categories using compiled regex
3. **Classify** the semantic context of each sentence
4. **Filter** false positives caused by negation or jokes
5. **Score** confidence per finding using context multipliers
6. **Classify (ML)** each finding with a zero-shot NLI model — 13 labels, confidence fusion
7. **Group** duplicate evidence across categories
8. **Score** overall risk on a 0–100 weighted scale
9. **Summarize** findings with both rule-based and LLM (Llama 3.1) summaries
10. **Persist** results to SQLite, MongoDB (7 collections), and AWS S3
11. **Generate** a PDF report (also uploaded to S3)
12. **Notify** via email — automatic alert on High/Critical, on-demand summary
13. **Serve** everything through a FastAPI REST API with a RAG chatbot

> **No role-based assumptions.** The system never adjusts scores based on speaker labels. It evaluates *what is said*, not *who says it*.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| Audio Transcription | Faster-Whisper (Whisper Base, CPU, int8) |
| Pattern Detection | Python `re` — compiled regex |
| ML Classifier | `typeform/distilbert-base-uncased-mnli` — Zero-Shot NLI |
| LLM Summary | Ollama — Llama 3.1 |
| Vector Store | ChromaDB (persistent) |
| Embeddings | SentenceTransformers `all-MiniLM-L6-v2` |
| Primary Database | SQLite via SQLAlchemy ORM |
| Analytics Database | MongoDB Atlas (7 collections) |
| File Storage | AWS S3 (5 storage types, AES-256 encrypted) |
| Email | SMTP (Gmail / any provider) — HTML alert + summary templates |
| PDF Generation | ReportLab via `report_generator.py` |
| Runtime | Python 3.10+ |

---

## Project Structure

```
backend/
│
├── app.py                          # FastAPI application entry point
├── config.py                       # All config — paths, DB URL, SMTP, S3, MongoDB
├── requirements.txt                # Python dependencies
├── test_pipeline.py                # Interactive CLI pipeline tester
│
├── api/
│   └── audio_analysis_routes.py   # Versioned route definitions (/api/v1/*)
│
├── services/
│   └── audio_safety_service.py    # Async pipeline orchestration service
│
├── schemas/
│   └── audio_analysis_schemas.py  # Pydantic request/response models
│
├── modules/
│   ├── patterns.py                # Compiled regex pattern library (12 categories)
│   ├── context_analyzer.py        # ContextType enum + multipliers
│   ├── confidence.py              # Confidence scoring engine
│   ├── filters.py                 # NegationFilter + JokeFilter
│   ├── ml_classifier.py           # Zero-shot NLI classifier
│   ├── evidence_grouping.py       # Deduplication + category merging
│   ├── grooming_detector.py       # Main detection pipeline orchestrator
│   ├── risk_scorer.py             # Weighted risk scoring + diminishing returns
│   ├── severity_classifier.py     # Score → Safe/Low/Moderate/High/Critical
│   ├── summarizer.py              # Rule-based summary generator
│   ├── llm_summarizer.py          # Ollama Llama 3.1 summary
│   ├── report_generator.py        # PDF report generation
│   ├── transcriber.py             # Faster-Whisper transcription
│   ├── evidence_extractor.py      # Evidence list extraction
│   ├── stats.py                   # Statistics generation
│   ├── chatbot.py                 # RAG chatbot (ChromaDB + Ollama)
│   ├── email_notifier.py          # SMTP alert + summary email sender
│   └── s3_storage.py              # AWS S3 upload/download/presign/delete
│
├── database/
│   ├── db.py                      # SQLAlchemy engine + session
│   ├── models.py                  # AudioAnalysis ORM model
│   └── mongo.py                   # MongoDB client — 7-collection schema
│
├── examples/
│   ├── test_script_bad.txt        # High-risk grooming transcript (CRITICAL)
│   ├── test_script_medium.txt     # Ambiguous online chat transcript (MODERATE)
│   ├── test_script_good.txt       # Safe classroom transcript (LOW)
│   └── run_test_scripts.py        # Pipeline test runner
│
└── (runtime — auto-created, git-ignored)
    ├── uploads/                   # Uploaded audio files
    ├── reports/                   # Generated PDF reports
    ├── vectors/                   # ChromaDB persistent vector store
    ├── analysis.db                # SQLite database
    └── logs/app.log               # Application logs
```

---

## Detection Categories

| Category | Severity | Base Confidence | Risk Weight | Description |
|---|---|---|---|---|
| `explicit_content` | Critical | 0.98 | 25 | Sexual solicitation, nude requests, explicit language |
| `meeting` | Critical | 0.95 | 20 | Arranging in-person contact |
| `address` | Critical | 0.90 | 20 | Requesting physical location or address |
| `secrecy` | Critical | 0.95 | 15 | Demands to hide, delete, or not disclose |
| `parent_monitoring` | High | 0.85 | 15 | Questions about parental supervision |
| `school` | High | 0.75 | 10 | School name, grade, dismissal time |
| `routine` | High | 0.80 | 10 | Daily schedule, walk home, route |
| `video_call` | High | 0.80 | 10 | Video call requests, camera requests |
| `manipulation` | Critical | 0.90 | 10 | Coercion, conditional threats, peer pressure |
| `bad_language` | Medium | 0.85 | 8 | Profanity, slurs, threats, harassment |
| `trust_building` | Medium | 0.80 | 5 | Emotional trust establishment |
| `relationship_building` | High | 0.75 | 5 | Deepening personal dependency |

---

## Context Classification

Every sentence is classified into one or more `ContextType` values. The type drives a **confidence multiplier** — no speaker identity is ever consulted.

```
ContextType              Multiplier   Meaning
──────────────────────────────────────────────────────────────────
ADMINISTRATIVE             -0.40      Event logistics, forms, schedules → suppresses FPs
INFORMATION_GATHERING      +0.15      Collecting personal details
TRUST_BUILDING             +0.20      "I care about you", "trust me"
RELATIONSHIP_BUILDING      +0.15      "special connection", "best friends"
MANIPULATION               +0.30      "they won't understand", coercion
SECRECY                    +0.40      "don't tell anyone", "our secret"
ESCALATION                 +0.35      Private call, move to another platform
MEETING                    +0.35      Meet up, in person, hang out
PERSONAL_INFORMATION       +0.30      Address, phone, email, route
VIDEO_CALL                 +0.25      Video chat, FaceTime, camera requests
EXPLICIT_CONTENT           +0.50      Sexual language (highest multiplier)
BAD_LANGUAGE               +0.20      Profanity, slurs, threats
NEUTRAL                     0.00      No strong signal
```

---

## Confidence Scoring

```
score = pattern_strength
      + exact_phrase_bonus      (+0.15 if matched text is a known exact phrase)
      + keyword_bonus           (+0.10 if ≥2 supporting keywords present)
      + context_multiplier      (from ContextType, -0.40 to +0.50)
      - negation_penalty        (up to -0.40, token-scoped within 5 tokens)
      - joke_penalty            (up to -0.50, ±2 sentence window)

regex_confidence = clamp(score, 0.0, 1.0)

# ML fusion (25% weight)
fused_confidence = 0.75 × regex_confidence + 0.25 × ml_category_score
```

---

## ML Classifier

- Model: `typeform/distilbert-base-uncased-mnli` (Zero-Shot NLI via HuggingFace)
- 13 labels mapped to detection categories
- Temperature calibration T=1.3 for better-calibrated probabilities
- Multi-label detection threshold: ≥0.15
- Agreement/disagreement signal surfaced in finding output
- LRU cache: 512 entries — repeated sentences are free
- Fused at 25% weight into the final confidence score
- Disabled by default (`enable_ml_classifier=False`) — enable once model is cached (~400 MB)

---

## Risk Scoring

```
effective_score = weight × confidence × diminishing_return_factor
total           = Σ effective_scores
final           = min(total, 100)
```

**Diminishing returns (same category, repeated occurrences):**

| Occurrence | Factor |
|---|---|
| 1st | 1.000 |
| 2nd | 0.500 |
| 3rd | 0.250 |
| 4th+ | continues halving |

**Risk levels:**

| Level | Score Range |
|---|---|
| Safe | 0 – 20 |
| Low | 21 – 40 |
| Moderate | 41 – 60 |
| High | 61 – 80 |
| Critical | 81 – 100 |

---

## Filters

**NegationFilter** — token-scoped: negation only suppresses a finding if the negation word is within 5 tokens of the matched phrase. Secrecy phrases like "nobody needs to know" are exempt.

**JokeFilter** — ±2 sentence window. Joke indicators (`lol`, `jk`, `just kidding`, `😂`, etc.) in the current or neighbouring sentence apply up to −0.50 confidence penalty.

---

## Evidence Grouping

When a single sentence matches multiple categories, `EvidenceGroupingEngine` merges them into one grouped finding with aggregate confidence and severity — preventing the same quote from inflating the score across categories.

---

## Storage — SQLite + MongoDB + S3

### SQLite (`analysis.db`)

Primary operational store. Every analysis result is written here.

```sql
CREATE TABLE audio_analysis (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT,
    transcript  TEXT,
    findings    TEXT,   -- JSON array
    evidence    TEXT,   -- JSON array
    stats       TEXT,   -- JSON object
    summary     TEXT,
    llm_summary TEXT,
    severity    TEXT,
    risk_score  REAL,
    pdf_path    TEXT,
    status      TEXT,
    error_message TEXT
);
```

### MongoDB (`database/mongo.py`)

Analytics and audit store — 7 collections written on every completed analysis:

| Collection | Contents |
|---|---|
| `meeting_metadata` | Filename, date, duration, participants, S3 URL, status |
| `transcripts` | Full transcript, speaker segments, timestamps, word count |
| `analysis_results` | Risk score, severity, LLM summary, rule summary, stats |
| `safety_findings` | Per-finding category, evidence, confidence, context type, ML fields |
| `action_items` | High/critical findings requiring action, topics, keywords |
| `processing_status` | Pipeline stage, started_at, completed_at, errors |
| `audit_logs` | All events — uploads, completions, failures, emails sent |

All 7 collections are written atomically via `save_full_analysis()`. Individual helpers (`save_meeting_metadata`, `save_transcript`, etc.) are also available.

### AWS S3 (`modules/s3_storage.py`)

Five storage types, all AES-256 server-side encrypted:

| Type | S3 Prefix | Description |
|---|---|---|
| Audio recordings | `recordings/YYYY/MM/` | Original uploaded audio files |
| Extracted audio | `recordings/YYYY/MM/` | Converted/extracted audio |
| PDF reports | `reports/YYYY/MM/` | Generated analysis PDFs |
| Exports | `exports/YYYY/MM/` | CSV / JSON / XLSX exports |
| Backups | `backups/YYYY/MM/` | Long-term archives |

Presigned URLs and deletion are also supported. S3 is non-blocking — a failure does not abort the analysis pipeline.

---

## Email Notifications

`modules/email_notifier.py` sends two types of HTML emails via SMTP.

### Automatic Alert (High / Critical)

Triggered automatically at the end of every analysis where severity meets or exceeds `ALERT_SEVERITY` (default: `High`). Contains:
- Risk score circle, severity badge, report ID
- AI executive summary
- Top 5 findings with confidence bars
- "View Full Report" button linking to `APP_URL`
- PDF attached if available

### On-Demand Summary

Triggered via `POST /notify/summary/{report_id}`. Contains:
- Full LLM summary + rule-based summary
- Category breakdown table
- Stat row: word count, finding count, average confidence

### Manual Re-send Alert

Triggered via `POST /notify/alert/{report_id}`. Sends the alert email regardless of severity. Accepts an optional `recipients` override in the request body.

Both endpoints log to MongoDB `audit_logs` and return `{"success": bool, "message": str, "recipients": [...]}`.

---

## Modules Reference

| Module | Purpose |
|---|---|
| `patterns.py` | Compiled regex library — 12 categories, `CATEGORY_METADATA`, `match_patterns()` |
| `context_analyzer.py` | `ContextType` enum, `CONTEXT_MULTIPLIERS`, `ContextAnalyzer.classify()` |
| `confidence.py` | `ConfidenceCalculator` — full scoring breakdown per finding |
| `filters.py` | `NegationFilter`, `JokeFilter`, `CombinedFilter` |
| `ml_classifier.py` | Zero-shot NLI, 13 labels, temperature calibration, LRU cache, `fuse_with_regex()` |
| `evidence_grouping.py` | `EvidenceGroupingEngine` — dedup + category merge + aggregate confidence |
| `grooming_detector.py` | `GroomingDetector` — main pipeline orchestrator |
| `risk_scorer.py` | `WeightedRiskScorer` — weighted scoring with diminishing returns |
| `severity_classifier.py` | Score → Safe / Low / Moderate / High / Critical |
| `summarizer.py` | Rule-based summary from findings + risk score |
| `llm_summarizer.py` | Ollama Llama 3.1 executive summary — fails gracefully |
| `report_generator.py` | PDF report with findings, score, severity, LLM summary |
| `transcriber.py` | Faster-Whisper — returns `(transcript, timeline)` |
| `evidence_extractor.py` | Clean evidence list from grouped findings |
| `stats.py` | Statistics dict — categories, confidence histogram, ML stats, context distribution |
| `chatbot.py` | RAG chatbot — ChromaDB + SentenceTransformers + Ollama |
| `email_notifier.py` | SMTP alert + summary emails, `should_auto_alert()`, `send_alert_email()`, `send_summary_email()` |
| `s3_storage.py` | `upload_audio()`, `upload_pdf_report()`, `upload_export_*()`, `get_presigned_url()`, `delete_file()`, `ping()` |

---

## API Endpoints

### Core

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Service name |
| `GET` | `/health` | S3 + MongoDB + service health |
| `POST` | `/analyze` | Upload audio, run full pipeline (background task) |
| `GET` | `/report/{id}/status` | Poll processing status |
| `GET` | `/history` | All reports — id, filename, severity, risk_score |
| `GET` | `/report/{id}` | Full report — transcript, findings, evidence, stats, summaries |
| `GET` | `/report/{id}/evidence` | Evidence list only |
| `GET` | `/report/{id}/stats` | Statistics only |
| `GET` | `/report/{id}/pdf` | Download PDF |
| `POST` | `/chat` | RAG chatbot — ask a question about a report |

### Notifications

| Method | Path | Description |
|---|---|---|
| `POST` | `/notify/alert/{id}` | Send (or re-send) a red-alert email for any report |
| `POST` | `/notify/summary/{id}` | Send a full analysis summary email |

Both accept an optional body `{"recipients": ["email@example.com"]}` to override `ALERT_RECIPIENTS`.

### Analytics

| Method | Path | Description |
|---|---|---|
| `GET` | `/analytics/summary` | Cross-report aggregation — severity distribution, risk histogram, top categories, ML agreement, confidence histogram |

### Versioned Routes (`/api/v1/`)

A second router at `/api/v1/` mirrors the core endpoints with Pydantic response models, pagination on `/history`, and a `DELETE /report/{id}` endpoint.

### POST `/analyze` — example

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@conversation.mp3"
```

Response:
```json
{
  "id": 16,
  "filename": "conversation.mp3",
  "status": "PROCESSING",
  "message": "Analysis started in background"
}
```

Poll status at `GET /report/16/status` until `"status": "COMPLETED"`, then fetch the full report at `GET /report/16`.

### POST `/chat` — example

```json
{ "report_id": 16, "question": "What secrecy phrases were used?" }
```

### POST `/notify/alert/{id}` — example

```bash
curl -X POST http://localhost:8000/notify/alert/16 \
  -H "Content-Type: application/json" \
  -d '{"recipients": ["analyst@example.com"]}'
```

---

## Configuration

```python
# config.py — key settings

UPLOAD_FOLDER      = "uploads"
DATABASE_URL       = "sqlite:///analysis.db"
ALLOWED_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".ogg"]
APP_URL            = "http://localhost:5173"   # used in email links
```

```python
# grooming_detector.py — constructor defaults

GroomingDetector(
    min_confidence_threshold = 0.15,   # findings below this are dropped
    enable_context_analysis  = True,
    enable_filters           = True,
    enable_grouping          = True,
    enable_ml_classifier     = False,  # set True once model is cached (~400 MB)
)
```

```python
# risk_scorer.py — weight overrides

scorer = WeightedRiskScorer(
    custom_weights = {"explicit_content": 30},
    enable_diminishing_returns = True,
)
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values. The `.env` file is git-ignored.

```env
# SMTP — email alerts and summaries
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_NAME=AuraSafety
ALERT_RECIPIENTS=analyst@yourorg.com,supervisor@yourorg.com
ALERT_SEVERITY=High          # High or Critical
APP_URL=http://localhost:5173

# MongoDB — analytics store
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
MONGO_DB_NAME=audio_safety_db

# AWS S3 — file storage
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
```

All three integrations (MongoDB, S3, SMTP) are **optional** — the analysis pipeline runs fully without them. Missing credentials are logged as warnings and the relevant step is skipped gracefully.

---

## Running the Server

### Prerequisites

```bash
pip install -r requirements.txt

# Ollama (optional — for LLM summary and chatbot)
# Install from https://ollama.com then:
ollama pull llama3.1
```

### Start

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Supported audio formats

`.mp3` `.wav` `.m4a` `.aac` `.ogg`

---

## Test Scripts

```bash
python examples/run_test_scripts.py
```

| Script | Expected Score | Severity | Description |
|---|---|---|---|
| `test_script_bad.txt` | 100 | CRITICAL | All 12 categories triggered |
| `test_script_medium.txt` | ~53 | MODERATE | Trust-building, routine probing, video call |
| `test_script_good.txt` | 0 | LOW | Safe classroom exchange — zero findings |

Set `ENABLE_ML = True` in `run_test_scripts.py` to include the ML classifier layer (requires model cache, ~400 MB).

---

## Interactive Pipeline Tester

```bash
python test_pipeline.py
```

```
pipeline> keep this between us, nobody needs to know
pipeline> what time does the science exhibition finish?
pipeline> send me your nudes right now
pipeline> haha just kidding, lets meet up lol
pipeline> multi        ← enter multi-line transcript mode
```

Each input shows context classification, filter penalties, per-category confidence breakdown, and the final risk score bar.

---

## Design Principles

**No role-based assumptions** — speaker labels are stored for audit only. The same sentence scores identically regardless of who said it.

**Content-based context** — risk adjustment is driven entirely by what is said. Administrative language reduces confidence; secrecy, manipulation, and explicit language increase it.

**Token-scoped negation** — negation only suppresses a finding when the negation word is within 5 tokens of the matched phrase. Secrecy phrases containing negation words are explicitly exempt.

**Diminishing returns** — the first occurrence of any category always receives full weight. Repeated occurrences are progressively down-weighted (50%, 25%, 12.5%, …) to prevent a single repeated phrase from dominating the score.

**Graceful degradation** — MongoDB, S3, SMTP, and Ollama are all optional. A failure in any of them is logged as a warning and the pipeline continues. The core analysis (transcription → detection → scoring → SQLite) always runs.

**Background processing** — audio analysis runs in a FastAPI `BackgroundTask`. The `/analyze` endpoint returns immediately with a record ID; the client polls `/report/{id}/status` until completion.
