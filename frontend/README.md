# AuraSafety — Frontend

React 19 + Vite 8 dashboard for the AuraSafety audio grooming detection system.

---

## Pages

| Route | Page | Description |
|---|---|---|
| `/` | Dashboard | Analysis history table with live search, sortable columns, 4 stat cards, and delete action |
| `/upload` | Analyze Audio | Drag-and-drop or click-to-upload (audio or video) with real-time progress bar; polls status until complete then redirects to the report |
| `/report/:id` | Report | Full analysis view — 6 tabs + chatbot sidebar (see below) |

### Report Page Tabs

| Tab | Contents |
|---|---|
| **Overview** | Risk ring (animated 0–100 gauge), severity badge, LLM summary, rule-based summary, category breakdown |
| **Findings** | Grouped findings with confidence bars, matched text, context type, filter flags (negated / joke), ML label and agreement signal, scoring breakdown |
| **Evidence Log** | Flat evidence list — timestamp, category badge, severity, speaker label, confidence, context type, base confidence, context multiplier |
| **Timeline** | Scatter chart of findings over time — x-axis: timestamp, y-axis: confidence, colour-coded by category |
| **Analytics** | Per-report charts — category distribution (bar), severity distribution (pie), confidence histogram (bar), context type distribution (bar), speaker distribution (bar), ML agreement rate |
| **Raw Data** | Full JSON dump of the report object — useful for debugging |

---

## Components

| Component | Description |
|---|---|
| `Chatbot.jsx` | AI chatbot sidebar on the Report page — sends questions to `POST /chat` and displays the answer with source excerpts |
| `ErrorBoundary.jsx` | React error boundary wrapping all routes — catches render errors and shows a fallback UI |

---

## Setup

```bash
npm install
npm run dev       # dev server at http://localhost:5173
npm run build     # production build → dist/
npm run preview   # preview production build
npm run lint      # ESLint
```

The Vite dev server proxies all `/api/v1/*` requests to `http://localhost:8000` — the backend must be running.

---

## Stack

| Package | Version | Purpose |
|---|---|---|
| React | 19 | UI framework |
| Vite | 8 | Build tool + dev server |
| React Router | 7 | Client-side routing (`/`, `/upload`, `/report/:id`) |
| Axios | 1.x | HTTP client — all API calls via `src/api.js` |
| Recharts | 3.x | Bar, pie, scatter charts |
| Lucide React | 1.x | Icons |

---

## API Client (`src/api.js`)

All backend calls go through a single Axios instance with `baseURL: '/api/v1'` and a 30 s default timeout. The following functions are exported:

| Function | Method | Description |
|---|---|---|
| `getHistory(skip, limit)` | `GET /history` | Paginated analysis history |
| `getReport(id)` | `GET /report/:id` | Full report object |
| `getReportStatus(id)` | `GET /report/:id/status` | Poll PROCESSING / COMPLETED / FAILED |
| `uploadAudio(file, onProgress)` | `POST /analyze` | Upload audio file (10 min timeout) |
| `uploadVideo(file, onProgress)` | `POST /analyze/video` | Upload video file (30 min timeout) |
| `analyzeTranscript(transcript, filename)` | `POST /analyze/transcript` | Submit plain-text transcript (10 min timeout) |
| `getChatbotAnswer(reportId, question)` | `POST /chat` | RAG chatbot (2 min timeout) |
| `getAnalyticsSummary()` | `GET /analytics/summary` | Cross-report aggregation |
| `sendAlertEmail(reportId, recipients)` | `POST /notify/alert/:id` | Send / re-send alert email |
| `sendSummaryEmail(reportId, recipients)` | `POST /notify/summary/:id` | Send summary email |
| `deleteReport(id)` | `DELETE /report/:id` | Delete report record + PDF + S3 files |
| `downloadPdfUrl(reportId)` | — | Returns the PDF download URL string |

Set `VITE_API_KEY` in `frontend/.env` to attach an `X-API-Key` header to every request (required when `API_KEY` is set in the backend `.env`).

---

## Proxy Config

```js
// vite.config.js
server: {
  proxy: {
    '/api/v1': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api\/v1/, '')
    }
  }
}
```

All `/api/v1/*` requests from the browser are transparently forwarded to the FastAPI backend at `:8000`, with the `/api/v1` prefix stripped before forwarding.

---

## Environment Variables

Create `frontend/.env` to override defaults:

```env
VITE_API_KEY=your-api-key   # optional — must match API_KEY in backend/.env
```
