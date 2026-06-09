# MELODYWINGS SAFETY PLATFORM — COMPLETE SYSTEM AUDIT REPORT

**Audit Date:** June 9, 2026  
**Auditor:** Kiro AI (Senior Architect / Security / DevOps / QA / Performance)  
**Project:** Melody Wings Safety — Audio Grooming Detection Platform  
**Version Audited:** 2.1.0  
**Scope:** Full codebase — backend, frontend, database, DevOps, security, performance

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Project Structure Analysis](#2-project-structure-analysis)
3. [Code Quality Review](#3-code-quality-review)
4. [Backend Analysis](#4-backend-analysis)
5. [Database Analysis](#5-database-analysis)
6. [Frontend Analysis](#6-frontend-analysis)
7. [Security Audit](#7-security-audit)
8. [Performance Analysis](#8-performance-analysis)
9. [Dependency Audit](#9-dependency-audit)
10. [Testing Analysis](#10-testing-analysis)
11. [DevOps Review](#11-devops-review)
12. [Error Detection (All Issues)](#12-error-detection)
13. [Fix Recommendations](#13-fix-recommendations)
14. [Final Scores](#14-final-scores)
15. [Action Plan & Roadmap](#15-action-plan--roadmap)

---

## 1. EXECUTIVE SUMMARY

The MelodyWings Safety Platform is a child safeguarding application that analyzes audio recordings and transcripts to detect grooming patterns using ML (DistilBERT/NLI), rule-based pattern matching, and an LLM (Ollama) for summarization. The stack is FastAPI (Python) + React + MongoDB + Redis + Celery + Google Drive integration.

**Overall Assessment:** The project is architecturally mature for its stage, with many production-quality patterns already in place (circuit breakers, TTL caches, JWT + bcrypt auth, account lockout, structured logging, Celery task queues, WebSocket progress updates, virus scanning). However, several **critical security vulnerabilities and reliability issues** must be resolved before production deployment.

| Category | Score | Grade |
|---|---|---|
| Architecture | 74/100 | B |
| Security | 61/100 | C+ |
| Performance | 72/100 | B |
| Maintainability | 70/100 | B |
| Production Readiness | 58/100 | C |

---

## 2. PROJECT STRUCTURE ANALYSIS

### 2.1 Directory Layout

```
New-Rmsi-Latest/
├── backend/
│   ├── api/                  ✅ Versioned routers (good)
│   ├── database/             ✅ Mongo client + migrations
│   ├── middleware/           ✅ Rate limiter
│   ├── models/               ✅ Fine-tuned model checkpoint
│   ├── modules/              ✅ 30 modules (well-organized)
│   ├── examples/             ⚠️  Test fixtures — should be in tests/
│   ├── tasks/                ❌  Missing from tree (Celery tasks referenced but not visible)
│   ├── schemas/              ❌  Missing from tree (referenced in audio_analysis_routes.py)
│   ├── services/             ❌  Missing from tree (referenced in audio_analysis_routes.py)
│   ├── app.py                ⚠️  1135 lines — too large, should be split
│   ├── auth.py               ✅
│   ├── config.py             ✅
│   ├── celery_app.py         ✅
│   ├── .env                  ❌  CRITICAL: committed with real secrets
│   ├── .google_credentials.json ❌ CRITICAL: credentials file in repo
│   └── requirements.txt      ✅ Pinned versions (good)
├── frontend/
│   ├── src/
│   │   ├── pages/            ✅ 7 pages
│   │   ├── components/       ✅ 4 components
│   │   ├── hooks/            ✅ 2 hooks
│   │   ├── store/            ✅ Central DataStore
│   │   └── api.js            ✅ Clean API layer
│   └── package.json          ⚠️  Unpinned deps (^semver ranges)
└── docker-compose.yml        ✅ Multi-service compose
```

### 2.2 Structural Issues

| Issue | Severity | Location |
|---|---|---|
| `.env` file committed to repo | **Critical** | `backend/.env` |
| `.google_credentials.json` in repo | **Critical** | `backend/.google_credentials.json` |
| `tasks/`, `schemas/`, `services/` directories not visible in tree | **High** | `backend/` |
| `app.py` is 1135 lines (God file) | **Medium** | `backend/app.py` |
| Test examples mixed with production code | **Low** | `backend/examples/` |
| No `tests/` directory | **High** | `backend/` |
| `finetune_model.py` at root level | **Low** | `backend/finetune_model.py` |
| Frontend deps use `^` ranges (not locked) | **Medium** | `frontend/package.json` |

### 2.3 Missing Files / Directories

- `backend/tasks/` — Celery tasks (referenced in `app.py`, `audio_analysis_routes.py`, `google_drive_routes.py`) — not visible, may be missing
- `backend/schemas/audio_analysis_schemas.py` — referenced in `audio_analysis_routes.py`
- `backend/services/audio_safety_service.py` — referenced in `audio_analysis_routes.py`
- `backend/services/google_drive_service.py` — referenced in `google_drive_routes.py`
- `backend/tests/` — no test suite found
- `backend/static/logo.png` — referenced in `email_notifier.py`, may be absent
- `frontend/Dockerfile` — listed in directory but not read; should be verified

---

## 3. CODE QUALITY REVIEW

### 3.1 app.py — God File Problem

`app.py` contains 1135 lines with route handlers, startup logic, background functions, middleware, and business logic all mixed together. This violates the Single Responsibility Principle.

**Routes duplicated between `app.py` and `api/audio_analysis_routes.py`:**

| Route | In app.py | In audio_analysis_routes.py |
|---|---|---|
| `POST /analyze` | ✅ Lines ~350–430 | ✅ Lines ~60–160 |
| `POST /analyze/video` | ✅ Lines ~430–540 | Not present |

This creates an **ambiguous routing situation** where two different handlers can serve the same path.

### 3.2 Syntax / Logic Errors

| File | Line | Issue | Severity |
|---|---|---|---|
| `app.py` | ~540 | Truncated line: `status="PROCESSING",\n    background_tasks.add_task(process_video_background, record_id, audio_filepath, filename)` — variable `fi` used instead of `file_size` | **High** |
| `summarizer.py` | ~290 | Dead loop: `for step in rec_text.split(". ("):` iterates but does nothing (`pass` body) | **Medium** |
| `analytics_routes.py` | ~30 | `pct = lambda n: ...` — lambda defined inside a function body; Python closure issue if used in list comprehension | **Low** |
| `auth.py` | ~210 | `locked_until` compared as `datetime` but MongoDB may return naive/aware datetime mismatch | **Medium** |

### 3.3 Dead / Unused Code

| File | Issue |
|---|---|
| `app.py` lines ~350 and `audio_analysis_routes.py` | Duplicate `/analyze` implementation — one is dead |
| `summarizer.py` line ~290 | `for step in rec_text.split(". ("):` loop body is `pass` — does nothing |
| `app.py` `NotifyRequest` model (~line 470) | Defined in `app.py` but also defined in `notification_routes.py` |
| `app.py` `ChatRequest` model (~line 467) | Defined in `app.py` and again in `audio_analysis_routes.py` (via schemas) |

### 3.4 Code Style Issues

| File | Issue |
|---|---|
| `api.js` | `console.log` / `console.error` left in `deleteReport()` (lines ~297–303) — should use a logger |
| `analytics_routes.py` | Inline lambda `pct = lambda n: ...` on line ~88 — use a named function |
| Multiple files | `import os` inside functions (e.g., `google_drive_routes.py` `google_oauth_callback`) — should be at module level |
| `app.py` | Two `@app.on_event("startup")` decorators (for `startup_event` and `_start_ws_queue`) — only one startup hook should be used |
| `app.py` | `import threading as _threading_chatbot` — second aliased import of threading after `import threading as _threading` — redundant |

---

## 4. BACKEND ANALYSIS

### 4.1 API Routes Overview

| Router | Prefix | Auth | Issues |
|---|---|---|---|
| `audio_analysis_routes.py` | `/api/v1` | JWT required on history/report/evidence | Missing auth on `/analyze`, `/analyze/batch`, `/report/{id}/stats`, `/report/{id}/pdf`, `/chat` |
| `analytics_routes.py` | `/api/v1` | JWT required | None found |
| `auth_routes.py` | `/auth` | Public login, protected `/me` | None found |
| `notification_routes.py` | `/api/v1` | JWT required | None found |
| `google_drive_routes.py` | `/api/v1/google-drive` | No JWT, only Drive auth check | Missing platform JWT auth on Drive endpoints |
| `app.py` direct routes | `/` | Mixed | `/analyze`, `/analyze/video` unprotected |

### 4.2 Authentication / Authorization Gaps

| Endpoint | Issue | Severity |
|---|---|---|
| `POST /api/v1/analyze` | No JWT auth — any unauthenticated user can upload files | **Critical** |
| `POST /api/v1/analyze/batch` | No JWT auth | **Critical** |
| `GET /api/v1/report/{id}/stats` | No `Depends(get_current_user)` | **High** |
| `GET /api/v1/report/{id}/pdf` | No `Depends(get_current_user)` | **High** |
| `POST /api/v1/chat` | No `Depends(get_current_user)` | **High** |
| All `/api/v1/google-drive/*` | No platform JWT — only Google credential check | **High** |
| `GET /api/v1/health` | Public — leaks version/infra info | **Medium** |

### 4.3 Request Validation

| Issue | File | Severity |
|---|---|---|
| `report_id: int` in WebSocket (line ~476 app.py) defaults to `None` — type inconsistency | `app.py` | **Medium** |
| Google Drive `search` query param not length-capped — potential for very long queries | `google_drive_routes.py` | **Low** |
| No input sanitization on `question` in `ChatRequest` — can send arbitrary text to LLM | `audio_analysis_routes.py` | **Medium** |
| `LoginRequest` has no min-length validation on username/password | `auth_routes.py` | **Low** |

### 4.4 Error Handling

- ✅ Global exception handler in `app.py` — catches all unhandled exceptions
- ✅ Circuit breakers on Ollama and S3 calls
- ✅ Graceful MongoDB fallback (returns `None`)
- ⚠️ Virus scan errors fall-open by default (`VIRUS_SCAN_FAIL_CLOSED=false`) — production should be fail-closed
- ⚠️ `bulkDeleteReports` in `api.js` silently swallows errors per-ID — no aggregate error surfacing to the user
- ❌ `run_transcript_pipeline()` in Google Drive routes has no error handling wrapper

### 4.5 Middleware Order Issue

Middleware is added in this order in `app.py`:
1. `RequestIDMiddleware`
2. `SecurityHeadersMiddleware`
3. `APIKeyMiddleware`
4. `CORSMiddleware`
5. `RateLimitMiddleware`

**Issue:** Starlette/FastAPI middleware is executed in LIFO (last-added = first-executed) order. This means `RateLimitMiddleware` runs first (before CORS), which can cause rate-limited responses to lack CORS headers and be blocked by the browser before the 429 is visible.

---

## 5. DATABASE ANALYSIS

### 5.1 Schema Design

The MongoDB 7-collection schema is well-designed:

| Collection | Purpose | Issues |
|---|---|---|
| `meeting_metadata` | Session records | `created_at` set twice (lines ~195 in `save_meeting_metadata`) |
| `transcripts` | Full text + segments | None found |
| `analysis_results` | Risk/severity/summary | `evidence` array duplicated here and in `safety_findings` |
| `safety_findings` | Individual findings | `delete_many` + `insert_many` not atomic in non-transaction path |
| `action_items` | High-severity summaries | Derived data — redundant with `safety_findings` |
| `processing_status` | Pipeline state | None found |
| `audit_logs` | All events | No user ID field — cannot attribute actions to specific users |

### 5.2 Indexing

| Index | Status | Notes |
|---|---|---|
| `meeting_metadata.meeting_id` (unique) | ✅ Created | |
| `analysis_results.risk_score DESC` | ✅ Created | |
| `safety_findings.category` | ✅ Created | |
| `audit_logs TTL on timestamp` | ✅ Created | |
| `meeting_metadata.status` | ✅ In migration 001 | |
| `meeting_metadata` compound index on `(status, created_at)` | ❌ Missing | Would help dashboard queries |
| `analysis_results.severity` | ✅ In migration 001 | |
| `users.username` (unique) | ✅ Created | |
| `audit_logs.event` (for event-type queries) | ⚠️ Uses `event_type` in migration but field is `event` | Field name mismatch |

### 5.3 Data Integrity Issues

| Issue | Location | Severity |
|---|---|---|
| `evidence` field stored in both `analysis_results.evidence` and `safety_findings` collection | `mongo.py` | **Medium** — data duplication |
| `save_meeting_metadata` uses two `_now()` calls for `date` and `created_at` — microsecond difference possible | `mongo.py` line ~195 | **Low** |
| No foreign key equivalent — `meeting_id` references not enforced | MongoDB (schemaless) | **Low** |
| `save_safety_findings` does `delete_many` then `insert_many` outside a transaction — window for inconsistent state | `mongo.py` ~line 290 | **High** |
| Audit log has no `user_id` — cannot attribute who performed actions in multi-user scenarios | `mongo.py` | **Medium** |

### 5.4 Query Efficiency

- ✅ TTL indexes on `audit_logs` and `processing_status` — prevents unbounded growth
- ✅ Unique indexes prevent duplicate meeting IDs
- ⚠️ `get_analytics_summary` likely runs multiple aggregation pipelines — not visible in this audit but should use `$facet` for a single round trip
- ⚠️ `list_meetings` fetches up to 200 records into the DataStore — no server-side filtering; all filtering is client-side

---

## 6. FRONTEND ANALYSIS

### 6.1 Component Review

| Component | Issues |
|---|---|
| `App.jsx` | ✅ Clean — lazy loading, error boundaries, protected routes |
| `Dashboard.jsx` | ⚠️ 632 lines — getting large; delete confirm dialog uses inline portal instead of component |
| `Analytics.jsx` | ⚠️ 771+ lines — extremely large; chart data computation done inline in component |
| `Login.jsx` | ✅ Clean, accessible, handles errors well |
| `dataStore.jsx` | ✅ Well-designed global store with optimistic updates |
| `api.js` | ⚠️ `console.log`/`console.error` in `deleteReport`; no request deduplication |

### 6.2 Routing

| Route | Status | Notes |
|---|---|---|
| `/` | ✅ Protected → Dashboard | |
| `/upload` | ✅ Protected → Upload | |
| `/report/:id` | ✅ Protected → Report | |
| `/google-drive` | ✅ Protected → GoogleDrive | |
| `/compare` | ✅ Protected → Compare | |
| `/analytics` | ✅ Protected → Analytics | |
| `/login` | ✅ Public | |
| Catch-all 404 | ❌ Missing — unknown routes silently redirect | |

### 6.3 Security Issues

| Issue | Severity |
|---|---|
| JWT stored in `sessionStorage` — vulnerable to XSS (any injected script can steal it) | **High** |
| `localStorage` used for `auth_user` — persists across browser sessions unnecessarily | **Medium** |
| `VITE_API_KEY` read from `import.meta.env` and sent in every request header — API key exposed in browser | **High** |
| No CSRF protection on state-changing requests (relies only on JWT) | **Medium** |
| Inline `<style>` in Login.jsx for `@keyframes spin` — minor CSP concern | **Low** |

### 6.4 Accessibility

| Issue | Severity |
|---|---|
| Dashboard table rows use `role="button"` on `<tr>` — not semantically correct | **Medium** |
| No `aria-live` region for toast notifications — screen readers miss them | **Medium** |
| Filter `<select>` elements have no visible label — only placeholder text | **Medium** |
| Color-only severity indicators (red/green badges) — WCAG 1.4.1 violation | **High** |
| Custom checkbox buttons (`<button>` wrapping `<Square>/<CheckSquare>`) lack proper `aria-checked` | **Medium** |

### 6.5 State Management

- ✅ Single `DataStoreProvider` — no prop drilling
- ✅ Optimistic updates for delete
- ✅ Background polling for PROCESSING jobs
- ⚠️ Analytics page still has independent `insights` state that doesn't synchronize with the store
- ⚠️ `hiddenCharts` state stored in `localStorage` without versioning — stale keys accumulate

### 6.6 Performance

| Issue | Severity |
|---|---|
| `Analytics.jsx` has 12 `useMemo` calls computing chart data on every render | **Medium** |
| `bulkDeleteReports` in `api.js` deletes sequentially (one request per ID) — N serial requests for N deletions | **Medium** |
| No virtualization on the Dashboard history table — 200 DOM rows rendered at once | **Medium** |
| `exportReportsCSV` builds CSV string via string concatenation in a `.map()` — fine at current scale, but brittle | **Low** |

### 6.7 Vite Proxy Inconsistency

The Vite proxy config strips `/api/v1` for most routes:
```js
'/api/v1': { rewrite: (path) => path.replace(/^\/api\/v1/, '') }
```
But Google Drive, Analytics, and Chat routes are listed **before** this catch-all and do NOT strip the prefix. This means:
- `GET /api/v1/analytics/summary` → forwarded to backend as `/api/v1/analytics/summary` ✅
- `GET /api/v1/history` → forwarded as `/history` ✅ (stripped)
- `DELETE /api/v1/report/:id` → forwarded as `/report/:id` ✅

But in Nginx (production config), the same strip happens at `location /api/v1/`. The routes that bypass the strip in Vite (google-drive, analytics, chat) are also NOT stripped in nginx, so they reach the backend with their full `/api/v1/...` prefix — matching the backend router prefix `/api/v1`. This is **consistent** but the asymmetry is confusing and a maintenance trap.

---

## 7. SECURITY AUDIT

### 7.1 Critical Findings

| # | Issue | File | Severity |
|---|---|---|---|
| S1 | `.env` file committed to version control | `backend/.env` | **🔴 CRITICAL** |
| S2 | `.google_credentials.json` committed to version control | `backend/.google_credentials.json` | **🔴 CRITICAL** |
| S3 | `POST /api/v1/analyze` and `/analyze/batch` have no authentication | `audio_analysis_routes.py` | **🔴 CRITICAL** |
| S4 | JWT stored in `sessionStorage` — XSS-stealable | `frontend/src/api.js` | **🔴 HIGH** |
| S5 | `VITE_API_KEY` exposed in browser bundle | `frontend/src/api.js` | **🔴 HIGH** |

### 7.2 High Findings

| # | Issue | File | Severity |
|---|---|---|---|
| S6 | No JWT auth on `/report/{id}/pdf`, `/report/{id}/stats`, `/chat` endpoints | `audio_analysis_routes.py` | **🟠 HIGH** |
| S7 | Google Drive endpoints lack platform JWT auth | `google_drive_routes.py` | **🟠 HIGH** |
| S8 | `COOKIE_SECURE=false` in `.env.example` — sets insecure cookie in production if not changed | `backend/.env.example` | **🟠 HIGH** |
| S9 | `ENV=development` in `.env.example` default — if deployed as-is, JWT_SECRET check is bypassed | `backend/.env.example` | **🟠 HIGH** |
| S10 | `CSP: script-src 'self' 'unsafe-inline'` — allows inline scripts, weakens XSS protection | `app.py` line ~120 | **🟠 HIGH** |

### 7.3 Medium Findings

| # | Issue | File | Severity |
|---|---|---|---|
| S11 | No rate limiting on `GET` endpoints — analytics/history can be scraped rapidly | `middleware/rate_limiter.py` | **🟡 MEDIUM** |
| S12 | No CSRF token on state-changing API calls (only JWT Bearer — acceptable for API-only, but cookie fallback creates CSRF risk) | `auth_routes.py` | **🟡 MEDIUM** |
| S13 | `X-Forwarded-For` used directly for rate limiting without validation — can be spoofed | `middleware/rate_limiter.py` | **🟡 MEDIUM** |
| S14 | `audit_log` has no `user_id` — cannot audit who performed actions | `database/mongo.py` | **🟡 MEDIUM** |
| S15 | LLM prompt in analytics uses raw analytics data without sanitization — potential prompt injection if data is malicious | `api/analytics_routes.py` | **🟡 MEDIUM** |
| S16 | Google Drive search query escaped manually (not using official Drive API safe quoting) | `google_drive_routes.py` | **🟡 MEDIUM** |
| S17 | No `SameSite=Strict` on JWT cookie — `lax` used, allows cross-site GET requests | `api/auth_routes.py` | **🟡 MEDIUM** |

### 7.4 Low Findings

| # | Issue | File | Severity |
|---|---|---|---|
| S18 | Nginx config lacks `X-Content-Type-Options`, `X-Frame-Options` headers at proxy level | `frontend/nginx.conf` | **🟢 LOW** |
| S19 | Nginx config has no `client_max_body_size` limit | `frontend/nginx.conf` | **🟢 LOW** |
| S20 | `VIRUS_SCAN_FAIL_CLOSED=false` by default — scan errors allow files through | `virus_scanner.py` | **🟢 LOW** |
| S21 | Footer links in email templates use `href="#"` — placeholder, not real | `email_notifier.py` | **🟢 LOW** |
| S22 | `support@melodywings.com` hardcoded in email footer | `email_notifier.py` | **🟢 LOW** |

### 7.5 SQL/NoSQL Injection

- ✅ MongoDB queries use parameterized dict-style (`{"meeting_id": value}`) throughout — no string concatenation in queries
- ✅ Google Drive search term is manually escaped (`replace("'", "\\'")`) — adequate for Drive API queries
- ✅ No raw MongoDB command strings constructed from user input

### 7.6 XSS

- ⚠️ Email HTML templates build HTML strings via f-strings with user data (filename, summary). If a filename contains `<script>`, it would be embedded in the email. Email clients typically strip scripts, but this is still a concern for HTML injection in emails.
- ✅ React frontend uses JSX which auto-escapes values
- ✅ No `dangerouslySetInnerHTML` found

---

## 8. PERFORMANCE ANALYSIS

### 8.1 Backend Performance

| Issue | Impact | Severity |
|---|---|---|
| `app.py` has two `@app.on_event("startup")` handlers — duplicate startup overhead | Low | **Low** |
| `list_meetings` fetches up to `limit` records but the DataStore always requests 200 — large payloads | Medium | **Medium** |
| No `$facet` aggregation for `get_analytics_summary` — likely multiple round trips | High | **Medium** |
| `save_safety_findings` does `delete_many` + `insert_many` sequentially — window where findings are absent | Medium | **Medium** |
| ML warm-up runs in a daemon thread — if it crashes, no retry | Low | **Low** |
| Celery `concurrency=2` in docker-compose — may bottleneck on multi-core hosts | Medium | **Medium** |
| Chatbot warm-up spawns its own thread (`_threading_chatbot`) — redundant with `_threading` alias | Low | **Low** |

### 8.2 Caching

| Cache | TTL | Status |
|---|---|---|
| `/history` Redis-backed TTL | 60s | ✅ Good |
| `/report/{id}` Redis-backed TTL | 120s | ✅ Good |
| `/evidence/{id}` Redis-backed TTL | 120s | ✅ Good |
| `/analytics/summary` Redis-backed TTL | 60s | ✅ Good |
| `/analytics/insights` Redis-backed TTL | 300s | ✅ Good |
| Delete invalidation | Immediate | ✅ Good |
| POST `/analyze` cache invalidation | On completion | ✅ Good |

### 8.3 Frontend Performance

| Issue | Impact | Severity |
|---|---|---|
| 200 table rows rendered without virtualization | Visible jank on scroll | **Medium** |
| `Analytics.jsx` has 12 `useMemo` + 2 `useCallback` — memo overhead may exceed the savings for small datasets | Low | **Low** |
| `bulkDeleteReports` sends N sequential HTTP requests — should use a batch delete endpoint | User-visible delay | **Medium** |
| DataStore re-fetches 200 records every 30s if any job is PROCESSING — large polling payload | Network/server load | **Medium** |
| No `React.memo` on Analytics chart panels — all re-render when parent refreshes | Medium | **Medium** |

### 8.4 Memory / Resource

| Issue | Severity |
|---|---|
| In-memory fallback cache (`_memory_store` in rate limiter) is a `defaultdict(list)` with no eviction — grows unboundedly if Redis is down | **High** |
| `_memory_store` in `rate_limiter.py` is module-level — shared across all workers in multi-process mode, causing inconsistent rate limiting | **High** |
| Audio files are streamed in 1 MB chunks ✅ — no full-file in-memory loading | N/A |

---

## 9. DEPENDENCY AUDIT

### 9.1 Backend Dependencies

| Package | Pinned Version | Status | Notes |
|---|---|---|---|
| `fastapi` | 0.136.1 | ✅ Recent | |
| `starlette` | 1.0.1 | ⚠️ **Check** | Starlette 1.x is very new; verify FastAPI 0.136.1 compatibility |
| `uvicorn` | 0.47.0 | ✅ Recent | |
| `pydantic` | 2.13.4 | ✅ Pydantic v2 | |
| `python-jose[cryptography]` | 3.3.0 | ⚠️ **Stale** | Last release 2021; consider `PyJWT` instead |
| `bcrypt` | 4.2.1 | ✅ Good | |
| `cryptography` | 44.0.0 | ✅ Recent | |
| `faster-whisper` | 1.2.1 | ✅ Good | |
| `transformers` | 4.46.3 | ⚠️ **Stale** | Latest is 4.47+; security patches may be missing |
| `torch` | 2.6.0 | ✅ Recent | CPU-only install in Dockerfile ✅ |
| `chromadb` | 1.5.9 | ✅ Recent | |
| `ollama` | 0.6.2 | ✅ Good | |
| `pymongo` | 4.10.1 | ✅ Good | |
| `redis` | 5.2.1 | ✅ Good | |
| `boto3` | 1.35.99 | ✅ Good | |
| `celery` | 5.4.0 | ✅ Good | |
| `pyclamd` | 0.4.0 | ⚠️ **Stale** | Last release 2015; minimal maintenance |
| `google-api-python-client` | 2.131.0 | ✅ Good | |
| `sentence-transformers` | 3.3.1 | ✅ Good | |
| `reportlab` | 4.5.1 | ✅ Good | |
| `requests` | 2.34.2 | ✅ Good | |

### 9.2 Frontend Dependencies

| Package | Version Range | Status | Notes |
|---|---|---|---|
| `react` | ^19.2.6 | ✅ Latest major | |
| `react-router-dom` | ^7.15.1 | ✅ Latest | |
| `axios` | ^1.16.1 | ✅ Good | |
| `recharts` | ^3.8.1 | ✅ Good | |
| `lucide-react` | ^1.16.0 | ✅ Good | |
| `react-hot-toast` | ^2.6.0 | ✅ Good | |
| `vite` | ^8.0.12 | ✅ Latest | |
| All deps use `^` ranges | | ⚠️ Not locked | Should use `package-lock.json` (present) or `--exact` |

### 9.3 Vulnerable / Problematic Packages

| Package | Issue |
|---|---|
| `python-jose[cryptography]` | Last updated 2021; known CVE exposure in older cryptography backends. Consider migrating to `PyJWT` |
| `pyclamd` | Unmaintained since 2015. Works but any future Python incompatibility will not be fixed |
| `starlette==1.0.1` | Verify this is the intended version — `starlette` 1.0 is unusual relative to the FastAPI 0.x series which typically bundles starlette 0.x |

---

## 10. TESTING ANALYSIS

### 10.1 Test Coverage Summary

| Category | Status |
|---|---|
| Unit tests | ❌ No `tests/` directory found |
| Integration tests | ❌ Not found |
| End-to-end tests | ❌ Not found |
| Example transcript files | ✅ 30+ `.txt` files in `backend/examples/` |
| `test_email_redesign.py` | ⚠️ Ad-hoc test script in root — not pytest-structured |
| `examples/run_test_scripts.py` | ⚠️ Manual test runner — not automated |

### 10.2 Test Gaps

| Missing Test | Severity |
|---|---|
| Auth tests (login, logout, lockout, JWT expiry) | **Critical** |
| File upload validation (size limits, extension checks) | **High** |
| Rate limiter behavior | **High** |
| MongoDB operation failures (connection loss) | **High** |
| Virus scanner fallback behavior | **Medium** |
| Cache invalidation correctness | **Medium** |
| Analytics aggregation correctness | **Medium** |
| Frontend component rendering (React Testing Library) | **Medium** |
| Email template generation | **Low** |

### 10.3 `pytest` is in requirements.txt — but no tests exist

`pytest==8.3.4` is declared as a dependency, indicating intent. No actual test files exist. This is a major gap for a child safeguarding system where false positives/negatives have real-world impact.

---

## 11. DEVOPS REVIEW

### 11.1 Docker Configuration

**`backend/Dockerfile`:**
- ✅ Multi-stage build (base → deps → app)
- ✅ CPU-only PyTorch install saves ~1.5 GB
- ✅ `--no-cache-dir` used
- ✅ Required directories created
- ⚠️ No non-root user — container runs as root (security risk)
- ⚠️ No `HEALTHCHECK` instruction in Dockerfile (healthcheck is in compose only)
- ❌ `CMD ["uvicorn", ..., "--workers", "2"]` — Uvicorn multi-worker mode is not safe with FastAPI startup events (each worker runs its own `startup_event`, leading to double ML warm-up and double Drive watcher threads)

**`docker-compose.yml`:**
- ✅ Health checks on Redis and backend
- ✅ Named volumes for persistence
- ✅ Google/Cloudflare DNS for external hostname resolution
- ✅ ClamAV and Ollama behind `--profile full` (optional)
- ✅ `unless-stopped` restart policy
- ⚠️ `backend` health check uses `http://localhost:8000/api/v1/health` but the route is `/api/v1/health` which is registered under `v1_router` with prefix `/api/v1` — this should work, but verify
- ⚠️ `env_file: ./backend/.env` — loads the committed `.env` into production containers (CRITICAL with secret exposure issue)
- ❌ No resource limits (`mem_limit`, `cpus`) — a runaway ML job can OOM the host

### 11.2 CI/CD

- ❌ No CI/CD pipeline found (no `.github/workflows/`, `.gitlab-ci.yml`, etc.)
- ❌ No automated build/test on push
- ❌ No container image scanning
- ❌ No secrets scanning (would have caught the `.env` commit)

### 11.3 Logging & Monitoring

- ✅ Structured JSON logging in production (`modules/structured_logging.py`)
- ✅ Request ID middleware (`X-Request-ID` header)
- ✅ Audit logging to MongoDB
- ✅ Log rotation configured via env vars
- ⚠️ No centralized log shipping (ELK, CloudWatch, etc.)
- ⚠️ No APM / tracing (no Sentry, Datadog, OpenTelemetry)
- ⚠️ `/health` endpoint leaks internal service topology (Redis, ChromaDB, Ollama, S3 status)
- ❌ No alerting on failed jobs, high error rates, or disk space

### 11.4 Environment Configuration

| Env Var | Default | Production-Safe? |
|---|---|---|
| `JWT_SECRET` | `""` | ⚠️ Server refuses to start in prod only — dev mode bypasses auth entirely |
| `ENV` | `development` | ❌ Must be set to `production` in prod |
| `COOKIE_SECURE` | `false` | ❌ Must be `true` in prod (HTTPS required) |
| `ENABLE_VIRUS_SCAN` | `false` | ⚠️ Should be `true` in prod |
| `VIRUS_SCAN_FAIL_CLOSED` | `false` | ⚠️ Should be `true` in prod |
| `API_KEY` | `""` | ⚠️ Blank disables key auth — acceptable if JWT covers all routes |
| `MONGO_URI` | `""` | ❌ Must be set |
| `DRIVE_AUTO_WATCH` | `false` | ✅ Safe default |

---

## 12. ERROR DETECTION

### Complete Issue Registry

| # | File | Line(s) | Type | Description | Severity |
|---|---|---|---|---|---|
| E01 | `backend/.env` | ALL | Security | Real credentials committed to repository | 🔴 CRITICAL |
| E02 | `backend/.google_credentials.json` | ALL | Security | OAuth credentials file in repository | 🔴 CRITICAL |
| E03 | `backend/api/audio_analysis_routes.py` | ~60 | Auth | `POST /api/v1/analyze` missing `Depends(get_current_user)` | 🔴 CRITICAL |
| E04 | `backend/api/audio_analysis_routes.py` | ~120 | Auth | `POST /api/v1/analyze/batch` missing auth | 🔴 CRITICAL |
| E05 | `backend/app.py` | ~540 | Syntax/Logic | Truncated expression — `fi` used instead of `file_size` | 🔴 HIGH |
| E06 | `backend/app.py` | ~350 | Logic | Duplicate `/analyze` route — conflicts with `/api/v1/analyze` in router | 🟠 HIGH |
| E07 | `backend/api/audio_analysis_routes.py` | ~280 | Auth | `GET /report/{id}/stats` missing auth | 🟠 HIGH |
| E08 | `backend/api/audio_analysis_routes.py` | ~310 | Auth | `GET /report/{id}/pdf` missing auth | 🟠 HIGH |
| E09 | `backend/api/audio_analysis_routes.py` | ~340 | Auth | `POST /chat` missing auth | 🟠 HIGH |
| E10 | `backend/api/google_drive_routes.py` | ALL | Auth | No platform JWT on any Drive endpoint | 🟠 HIGH |
| E11 | `frontend/src/api.js` | ~55 | Security | JWT in sessionStorage — XSS vulnerable | 🟠 HIGH |
| E12 | `frontend/src/api.js` | ~100 | Security | `VITE_API_KEY` exposed in browser | 🟠 HIGH |
| E13 | `backend/app.py` | ~120 | Security | CSP allows `unsafe-inline` scripts | 🟠 HIGH |
| E14 | `backend/middleware/rate_limiter.py` | ~150 | Performance | In-memory `_memory_store` grows unboundedly | 🟠 HIGH |
| E15 | `backend/middleware/rate_limiter.py` | ~150 | Correctness | In-memory store not process-safe (multi-worker) | 🟠 HIGH |
| E16 | `backend/app.py` | ~270 | DevOps | Multiple workers (`--workers 2`) with startup events = duplicate warm-up threads | 🟠 HIGH |
| E17 | `backend/database/mongo.py` | ~290 | Integrity | `delete_many` + `insert_many` for findings — non-atomic outside transaction | 🟠 HIGH |
| E18 | `docker-compose.yml` | ~30 | DevOps | No resource limits on containers | 🟡 MEDIUM |
| E19 | `backend/modules/summarizer.py` | ~290 | Dead Code | `for step in rec_text.split(". ("):` — empty loop body | 🟡 MEDIUM |
| E20 | `backend/auth.py` | ~210 | Logic | Timezone-aware vs naive datetime comparison for lockout | 🟡 MEDIUM |
| E21 | `backend/app.py` | ~476 | Type | `report_id: int = None` — should be `Optional[int] = None` | 🟡 MEDIUM |
| E22 | `frontend/src/pages/Analytics.jsx` | ~771+ | Performance | No chart memoization — all 12 charts re-render together | 🟡 MEDIUM |
| E23 | `frontend/src/api.js` | ~297 | Code Quality | `console.log`/`console.error` in production code | 🟡 MEDIUM |
| E24 | `backend/database/migrations.py` | ~180 | Bug | `create_index([("event_type", ASCENDING)])` — field is `event`, not `event_type` | 🟡 MEDIUM |
| E25 | `backend/app.py` | ~460–475 | Dead Code | `ChatRequest` and `NotifyRequest` duplicated in app.py and routes | 🟢 LOW |
| E26 | `backend/api/analytics_routes.py` | ~88 | Style | Lambda `pct` defined inside function — use named function | 🟢 LOW |
| E27 | `frontend/nginx.conf` | ALL | Security | No `client_max_body_size` limit | 🟢 LOW |
| E28 | `backend/database/mongo.py` | ~195 | Logic | `date` and `created_at` both set with separate `_now()` calls — microsecond skew | 🟢 LOW |
| E29 | `backend/.env.example` | ~70 | Config | `COOKIE_SECURE=false` default — dangerous if copied for production | 🟠 HIGH |
| E30 | ❌ No `tests/` directory | — | Testing | Zero automated test coverage | 🟠 HIGH |

---

## 13. FIX RECOMMENDATIONS

### FIX-01: Remove Committed Secrets (E01, E02)
**Severity:** 🔴 CRITICAL  
**Root Cause:** `.env` and `.google_credentials.json` added to git without `.gitignore` protection.

```bash
# Immediate actions:
git rm --cached backend/.env backend/.google_credentials.json
echo "backend/.env" >> .gitignore
echo "backend/.google_credentials.json" >> .gitignore
git commit -m "fix: remove secrets from version control"

# Rotate ALL secrets immediately:
# - JWT_SECRET
# - SMTP_PASSWORD
# - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# - Google Client Secret
# - MongoDB password
# - Any API keys
```

---

### FIX-02: Add Auth to Unauthenticated Endpoints (E03, E04, E07, E08, E09, E10)
**Severity:** 🔴 CRITICAL / 🟠 HIGH  
**Root Cause:** `Depends(get_current_user)` omitted in route signatures.

```python
# backend/api/audio_analysis_routes.py

# BEFORE:
async def analyze_audio(
    file: UploadFile = File(...),
    service: AudioSafetyService = Depends(get_service)
):

# AFTER:
async def analyze_audio(
    file: UploadFile = File(...),
    service: AudioSafetyService = Depends(get_service),
    _user: dict = Depends(get_current_user),  # ADD THIS
):

# Apply same pattern to analyze_audio_batch, get_report_stats,
# download_pdf, chatbot_ask, and all google_drive_routes.py endpoints.
```

---

### FIX-03: Fix Truncated Code in app.py (E05)
**Severity:** 🔴 HIGH  
**Root Cause:** Variable `fi` used instead of `file_size` in video analysis route.

```python
# backend/app.py — video analysis route, near line 540
# BEFORE (broken):
_save_meta(
    meeting_id=record_id,
    filename=original_filename,
    file_size_bytes=fi  # ← BROKEN

# AFTER:
_save_meta(
    meeting_id=record_id,
    filename=original_filename,
    file_size_bytes=file_size,  # ← FIXED
```

---

### FIX-04: Fix In-Memory Rate Limiter Memory Leak (E14, E15)
**Severity:** 🟠 HIGH  
**Root Cause:** `defaultdict(list)` grows unboundedly; not safe for multi-process.

```python
# backend/middleware/rate_limiter.py

# Replace unbounded defaultdict with a bounded LRU-style dict
import threading
from collections import OrderedDict

_MAX_MEMORY_KEYS = 10_000  # cap memory usage
_memory_store: OrderedDict = OrderedDict()
_memory_lock = threading.Lock()

def _check_rate_limit_memory(key: str, max_requests: int, window: int):
    now = time.time()
    with _memory_lock:
        # Evict oldest entry if at capacity
        while len(_memory_store) >= _MAX_MEMORY_KEYS:
            _memory_store.popitem(last=False)
        
        timestamps = _memory_store.get(key, [])
        timestamps = [t for t in timestamps if now - t < window]
        
        if len(timestamps) >= max_requests:
            _memory_store[key] = timestamps
            return False, 0
        
        timestamps.append(now)
        _memory_store[key] = timestamps
        return True, max_requests - len(timestamps)
```

---

### FIX-05: Fix Duplicate Startup Event (E16)
**Severity:** 🟠 HIGH  
**Root Cause:** Two `@app.on_event("startup")` decorators; multi-worker spawns duplicate threads.

```python
# backend/app.py — merge into single startup handler

@app.on_event("startup")
async def startup_event():
    # ... all existing startup_event code ...
    
    # Add WebSocket queue initialization HERE (merged from _start_ws_queue):
    import asyncio
    init_progress_queue(asyncio.get_event_loop())
    asyncio.create_task(process_progress_queue())

# DELETE the separate @app.on_event("startup") async def _start_ws_queue()

# For multi-worker safety, wrap ML warm-up with a Redis lock:
async def startup_event():
    import asyncio
    redis_lock_key = "startup:ml_warmup_done"
    r = _get_redis()
    if r and not r.exists(redis_lock_key):
        r.setex(redis_lock_key, 300, "1")
        # Only run warm-up once across all workers
        _threading.Thread(target=_warmup, daemon=True).start()
```

---

### FIX-06: Fix Middleware Ordering (CORS + Rate Limiting)
**Severity:** 🟡 MEDIUM  
**Root Cause:** Starlette middleware LIFO order causes rate-limited responses to miss CORS headers.

```python
# backend/app.py — correct order (last added = first executed)
# Desired execution order: CORS → RateLimit → APIKey → Security → RequestID

# Add in REVERSE of desired execution:
app.add_middleware(RequestIDMiddleware)          # executes last
app.add_middleware(SecurityHeadersMiddleware)    # executes 5th
app.add_middleware(APIKeyMiddleware)             # executes 4th
app.add_middleware(RateLimitMiddleware)          # executes 3rd
app.add_middleware(                             # executes 2nd (CORS first for preflight)
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    ...
)
# CORSMiddleware should be added LAST so it executes FIRST
```

---

### FIX-07: Fix Migration Field Name Mismatch (E24)
**Severity:** 🟡 MEDIUM  
**Root Cause:** Migration creates index on `event_type` but the field is named `event`.

```python
# backend/database/migrations.py — migration 001

# BEFORE:
db["audit_logs"].create_index([("event_type", ASCENDING)])

# AFTER:
db["audit_logs"].create_index([("event", ASCENDING)])
```

---

### FIX-08: Fix Dead Loop in Summarizer (E19)
**Severity:** 🟡 MEDIUM  
**Root Cause:** Loop iterates over split parts but body is `pass`.

```python
# backend/modules/summarizer.py — around line 290

# BEFORE (does nothing):
for step in rec_text.split(". ("):
    if step:
        pass

# AFTER (remove the dead loop entirely — it was vestigial):
# Simply delete the 4 lines above. The rec_text is passed directly to
# _wrap_text() on the next line which handles it correctly.
```

---

### FIX-09: Move JWT to httpOnly Cookie Only (E11)
**Severity:** 🟠 HIGH  
**Root Cause:** JWT in sessionStorage is accessible to JavaScript — XSS vulnerability.

```javascript
// frontend/src/api.js

// RECOMMENDED APPROACH:
// 1. Remove all sessionStorage/localStorage token storage
// 2. Rely ENTIRELY on the httpOnly cookie already set by the server
// 3. Remove the Bearer token from the request interceptor
// 4. Set SameSite=Strict on the cookie (server-side)

// BEFORE:
export const saveAuth = (token, user) => {
  if (token) sessionStorage.setItem('access_token', token);
  localStorage.setItem('auth_user', JSON.stringify(user));
};

// AFTER (store only non-sensitive user info):
export const saveAuth = (token, user) => {
  // Don't store the token — it's in the httpOnly cookie
  localStorage.setItem('auth_user', JSON.stringify(user));
};

// Remove token from Authorization header interceptor
// The httpOnly cookie is sent automatically by withCredentials: true
```

---

### FIX-10: Add Resource Limits to Docker Compose (E18)
**Severity:** 🟡 MEDIUM

```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'
        reservations:
          memory: 1G
  
  celery-worker:
    deploy:
      resources:
        limits:
          memory: 6G   # ML inference needs more memory
          cpus: '2'
```

---

### FIX-11: Add nginx Security Headers and Body Size Limit (E27)
**Severity:** 🟢 LOW

```nginx
# frontend/nginx.conf — add to server block
client_max_body_size 512M;

add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

---

### FIX-12: Add Minimal Test Suite
**Severity:** 🟠 HIGH

```python
# backend/tests/test_auth.py — example
import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_login_valid_credentials():
    response = client.post("/auth/login", json={"username": "admin", "password": "correct"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_invalid_credentials():
    response = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401

def test_analyze_requires_auth():
    response = client.post("/api/v1/analyze")
    assert response.status_code == 401

def test_rate_limit_login():
    for _ in range(6):
        client.post("/auth/login", json={"username": "x", "password": "x"})
    response = client.post("/auth/login", json={"username": "x", "password": "x"})
    assert response.status_code == 429
```

---

## 14. FINAL SCORES

### Architecture Score: **74/100**

| Sub-category | Score | Notes |
|---|---|---|
| Separation of concerns | 65 | `app.py` is too large; duplicate routes |
| Scalability design | 80 | Celery, Redis, MongoDB horizontal scaling |
| Module organization | 80 | 30 well-named modules |
| API design | 72 | Good versioning; some auth gaps |
| Database design | 75 | Good schema; some redundancy |

### Security Score: **61/100**

| Sub-category | Score | Notes |
|---|---|---|
| Secrets management | 20 | `.env` committed — catastrophic |
| Authentication | 70 | JWT + bcrypt + lockout is solid |
| Authorization | 55 | Multiple endpoints lack auth |
| Input validation | 75 | Good file validation; some gaps |
| Transport security | 70 | HTTPS expected; CSP has `unsafe-inline` |
| Logging/Audit | 72 | Good audit logging; no user_id |

### Performance Score: **72/100**

| Sub-category | Score | Notes |
|---|---|---|
| Caching | 85 | Redis-backed TTL cache well-implemented |
| Database efficiency | 68 | Good indexes; missing compound index |
| Backend throughput | 70 | Celery async; some sync blocking paths |
| Frontend rendering | 65 | No virtualization; no chart memoization |
| Resource management | 72 | Good streaming; memory leak in rate limiter |

### Maintainability Score: **70/100**

| Sub-category | Score | Notes |
|---|---|---|
| Code organization | 68 | God file; good module structure elsewhere |
| Documentation | 75 | Good docstrings and comments |
| Test coverage | 20 | Essentially zero — critical gap |
| Dead code | 72 | Minor dead code found |
| Dependency management | 80 | Pinned versions; one stale package |

### Production Readiness Score: **58/100**

| Sub-category | Score | Notes |
|---|---|---|
| Security hardening | 40 | Secrets in repo; auth gaps |
| CI/CD pipeline | 10 | None exists |
| Monitoring/Alerting | 55 | Good logging; no APM/alerting |
| Error handling | 78 | Good global handler; some gaps |
| Configuration management | 60 | Good env vars; dangerous defaults |
| Disaster recovery | 55 | MongoDB Atlas provides backup; no DR plan |

---

## 15. ACTION PLAN & ROADMAP

### 🔴 IMMEDIATE FIXES (Do Today — Block Deployment)

| Priority | Action | Files Affected | Effort |
|---|---|---|---|
| P0 | Remove `.env` and `.google_credentials.json` from git history; rotate ALL secrets | `.gitignore`, git history | 2h |
| P0 | Add `Depends(get_current_user)` to all unprotected endpoints | `audio_analysis_routes.py`, `google_drive_routes.py` | 1h |
| P0 | Fix truncated `file_size` bug in `app.py` video route | `app.py` ~line 540 | 30m |
| P1 | Set `ENV=production` and `COOKIE_SECURE=true` in production `.env` | Production config | 15m |
| P1 | Fix in-memory rate limiter memory leak (bounded dict + lock) | `middleware/rate_limiter.py` | 1h |
| P1 | Merge duplicate `@app.on_event("startup")` handlers | `app.py` | 30m |
| P1 | Fix migration field mismatch (`event` vs `event_type`) | `database/migrations.py` | 15m |

### 🟠 SHORT-TERM IMPROVEMENTS (This Sprint — 1–2 Weeks)

| Priority | Action | Effort |
|---|---|---|
| P2 | Add minimal test suite (auth, upload validation, rate limiting) | 3–4 days |
| P2 | Move JWT to httpOnly-only (remove sessionStorage) | 1 day |
| P2 | Fix middleware execution order (CORS before rate limiter) | 2h |
| P2 | Add `client_max_body_size` and security headers to nginx | 1h |
| P2 | Add Docker resource limits to compose | 1h |
| P2 | Replace `python-jose` with `PyJWT` | 2h |
| P2 | Add `user_id` to audit log entries | 2h |
| P3 | Remove dead loop in `summarizer.py` | 30m |
| P3 | Remove `console.log`/`console.error` from `api.js` | 30m |
| P3 | Fix 404 catch-all route in React Router | 1h |
| P3 | Add aria labels and fix accessibility violations in Dashboard | 1 day |

### 🟡 LONG-TERM IMPROVEMENTS (Next Quarter)

| Priority | Action | Effort |
|---|---|---|
| P4 | Split `app.py` into focused route files — move `/analyze`, `/analyze/video`, `/delete`, `/chatbot` into `api/` | 2 days |
| P4 | Set up CI/CD pipeline (GitHub Actions) with lint, test, Docker build | 2 days |
| P4 | Add APM / error tracking (Sentry) | 1 day |
| P4 | Add server-side filtering to `list_meetings` — move 200-record client-side filter to MongoDB | 2 days |
| P4 | Implement `$facet` aggregation in `get_analytics_summary` | 1 day |
| P4 | Add table virtualization in Dashboard (react-window or tanstack-virtual) | 2 days |
| P4 | Implement batch delete endpoint on backend | 1 day |
| P4 | Add `VIRUS_SCAN_FAIL_CLOSED=true` to production config | 1h |
| P5 | Multi-role authorization (viewer/analyst/admin) | 3 days |
| P5 | Full E2E test suite (Playwright) for critical user flows | 1 week |
| P5 | Centralized log aggregation (CloudWatch / ELK) | 2 days |

### Prioritized Roadmap

```
Week 1: SECURITY FOUNDATION
  - Remove secrets from repo (P0)
  - Add missing auth (P0)  
  - Fix critical bugs (P0, P1)
  - JWT cookie-only (P2)

Week 2: RELIABILITY
  - Fix rate limiter leak (P1)
  - Fix middleware order (P2)
  - Write test suite (P2)
  - Fix migration bug (P1)

Week 3–4: HARDENING
  - nginx improvements (P2)
  - Replace python-jose (P2)
  - Accessibility fixes (P3)
  - Docker resource limits (P2)

Month 2: SCALE & OBSERVABILITY
  - Split app.py (P4)
  - CI/CD pipeline (P4)
  - Sentry integration (P4)
  - Server-side filtering (P4)

Month 3+: MATURITY
  - E2E tests (P5)
  - Multi-role auth (P5)
  - Batch delete API (P4)
  - Log aggregation (P5)
```

---

*This audit was generated by Kiro AI on June 9, 2026. It covers all readable source files in the repository. Issues marked Critical or High should be resolved before any production deployment. This report does not constitute a formal penetration test — a dedicated security engagement is recommended before handling real child safeguarding data in production.*
