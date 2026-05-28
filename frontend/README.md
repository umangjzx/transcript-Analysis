# Melody Wings Safety — Frontend

React 19 + Vite 8 dashboard for the Melody Wings Safety audio grooming detection system.

---

## Pages

| Route | Page | Description |
|---|---|---|
| `/login` | Login | JWT login form — username + password with show/hide toggle; auto-redirects if authenticated; public route |
| `/` | Dashboard | Analysis history table with live search, sortable columns, 4 stat cards, and delete action |
| `/upload` | Analyze Audio | Drag-and-drop or click-to-upload (audio, video, or `.txt` transcript) with real-time progress bar; polls status until complete then redirects to report |
| `/report/:id` | Report | Full analysis view — 6 tabs + chatbot sidebar (see below) |
| `/google-drive` | Google Drive | Connect Google Drive via OAuth2, browse importable `.txt` and Google Docs files, trigger imports, and manage the auto-watcher |

### Report Page Tabs

| Tab | Contents |
|---|---|
| **Overview** | Risk ring (animated 0–100 gauge), severity badge, LLM summary, rule-based summary, category breakdown |
| **Findings** | Grouped findings with confidence bars, matched text, context type, filter flags (negated / joke), ML label and agreement signal, scoring breakdown |
| **Evidence Log** | Flat evidence list — timestamp, category badge, severity, speaker label, confidence, context type |
| **Timeline** | Scatter chart of findings over time — x-axis: timestamp, y-axis: confidence, colour-coded by category |
| **Analytics** | Per-report charts — category distribution (bar), severity distribution (pie), confidence histogram (bar), context type distribution (bar), speaker distribution (bar), ML agreement rate |
| **Raw Data** | Full JSON dump of the report object — useful for debugging |

---

## Components

| Component | Description |
|---|---|
| `Chatbot.jsx` | AI chatbot sidebar on the Report page — sends questions to `POST /chat`, displays answer with source excerpts |
| `ErrorBoundary.jsx` | React error boundary wrapping all routes — catches render errors, shows fallback UI |

---

## Setup

```bash
npm install
npm run dev       # dev server at http://localhost:5173
npm run build     # production build → dist/
npm run preview   # preview production build
npm run lint      # ESLint
```

The backend must be running at `http://localhost:8000`. API traffic is proxied automatically (see below).

---

## Authentication

The frontend uses **JWT Bearer tokens** stored in `localStorage` (`auth_token`, `auth_user`).

### Flow

1. Unauthenticated users are redirected to `/login` by the `ProtectedRoute` guard in `App.jsx`
2. On successful login, the JWT and `{ username, role }` are stored; user is redirected to `/`
3. Every Axios request on the `/api/v1` client attaches `Authorization: Bearer <token>`
4. A global **401 interceptor** clears auth and redirects to `/login`
5. On logout, `POST /auth/logout` is called (fire-and-forget), then storage is cleared

### Protected routes

All routes except `/login` require a token in `localStorage`. If `JWT_SECRET` is unset on the backend, the API allows unauthenticated access in dev mode.

### Navbar

Shows the logged-in username, logout button, and avatar initials.

---

## Stack

| Package | Version | Purpose |
|---|---|---|
| React | 19 | UI framework |
| Vite | 8 | Build tool + dev server |
| React Router | 7 | Client-side routing |
| Axios | 1.x | HTTP client — `src/api.js` |
| Recharts | 3.x | Bar, pie, scatter charts |
| Lucide React | 1.x | Icons (Home, UploadCloud, HardDrive, LogOut, Shield) |
| react-hot-toast | 2.x | Toast notifications (Dashboard, Report, Google Drive) |

---

## API Client (`src/api.js`)

Two Axios patterns:

- **`/api/v1` client** — `baseURL: '/api/v1'` for analysis, reports, Drive (proxied; see below)
- **Root auth** — `POST /auth/login` uses a direct `axios.post('/auth/login')` (no `/api/v1` prefix)

### Functions

| Function | Method | Description |
|---|---|---|
| `login(username, password)` | `POST /auth/login` | Authenticates; stores JWT + user info |
| `logout()` | `POST /auth/logout` | Clears localStorage after server call |
| `getToken()` | — | Returns stored JWT or `null` |
| `getStoredUser()` | — | Returns `{ username, role }` or `null` |
| `getHistory(skip, limit)` | `GET /history` | Paginated analysis history |
| `getReport(id)` | `GET /report/:id` | Full report object |
| `getReportStatus(id)` | `GET /report/:id/status` | Poll PROCESSING / COMPLETED / FAILED |
| `uploadAudio(file, onProgress)` | `POST /analyze` | Upload audio (10 min timeout) |
| `uploadVideo(file, onProgress)` | `POST /analyze/video` | Upload video (30 min timeout) |
| `analyzeTranscript(transcript, filename)` | `POST /analyze/transcript` | JSON body transcript |
| `uploadTranscriptFile(file, onProgress)` | `POST /analyze/transcript` | Multipart .txt upload |
| `getChatbotAnswer(reportId, question)` | `POST /chat` | RAG chatbot (2 min timeout) |
| `getAnalyticsSummary()` | `GET /analytics/summary` | Cross-report aggregation |
| `sendAlertEmail(reportId, recipients)` | `POST /notify/alert/:id` | Send alert email |
| `sendSummaryEmail(reportId, recipients)` | `POST /notify/summary/:id` | Send summary email |
| `deleteReport(id)` | `DELETE /report/:id` | Delete report + PDF + S3 |
| `downloadPdfUrl(reportId)` | — | Returns PDF download URL |
| `getDriveAuthUrl()` | `GET /google-drive/auth-url` | Google OAuth consent URL |
| `getDriveStatus()` | `GET /google-drive/status` | Drive connection status |
| `getDriveFiles(pageSize, search)` | `GET /google-drive/files` | List importable files |
| `importDriveFile(fileId, fileName, mimeType)` | `POST /google-drive/import` | Import and analyze |
| `disconnectDrive()` | `DELETE /google-drive/logout` | Revoke Drive credentials |
| `getDriveWatcherStatus()` | `GET /google-drive/watcher/status` | Watcher state |
| `startDriveWatcher()` | `POST /google-drive/watcher/start` | Start auto-import |
| `stopDriveWatcher()` | `POST /google-drive/watcher/stop` | Stop auto-import |

Set `VITE_API_KEY` in `frontend/.env` to attach an `X-API-Key` header on every request.

---

## Proxy Config

```js
// vite.config.js
server: {
  proxy: {
    // Google Drive — full /api/v1/google-drive prefix preserved
    '/api/v1/google-drive': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
    // All other /api/v1/* — strip prefix (e.g. /api/v1/analyze → /analyze)
    '/api/v1': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api\/v1/, ''),
    },
    // Auth — root backend paths
    '/auth': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
},
```

Upload flows call proxied `/api/v1/analyze` (→ backend `/analyze`, **background**), then poll `/api/v1/report/{id}/status` until complete.

---

## Key Features

- **Lazy-loaded pages** — Dashboard, Upload, Report, and GoogleDrive are loaded on demand via `React.lazy()`
- **Error boundary** — catches render errors and shows a fallback UI
- **Protected routes** — `ProtectedRoute` component checks for JWT before rendering
- **Toast notifications** — success/error feedback via react-hot-toast
- **Responsive navigation** — brand logo, nav links, username badge, logout button, avatar
- **Real-time progress** — Upload page polls `/report/{id}/status` until analysis completes
- **Chatbot sidebar** — available on Report page for per-report Q&A
- **Google Drive integration** — OAuth2 connect flow, file browser with search, import trigger, watcher controls
- **Delete action** — Dashboard supports report deletion with confirmation

---

## Environment Variables

Create `frontend/.env` to override defaults:

```env
VITE_API_KEY=your-api-key   # optional — must match API_KEY in backend/.env
```

For JWT login, set `JWT_SECRET` in `backend/.env` and run `python create_admin.py` once.

---

## Build

```bash
npm run build     # outputs to dist/
npm run preview   # serve the production build locally
```

The production build can be served by any static file server (nginx, Vercel, Netlify, S3+CloudFront). Configure the reverse proxy to forward `/api/v1/*` and `/auth/*` to the backend.
