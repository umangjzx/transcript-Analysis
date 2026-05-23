# AuraSafety — Frontend

React 19 + Vite 8 dashboard for the AuraSafety audio grooming detection system.

---

## Pages

| Page | Route | Description |
|---|---|---|
| Dashboard | `/` | Upload audio files, view analysis history |
| Report | `/report/:id` | Full analysis — risk score, findings debugger, evidence log, timeline, analytics, raw JSON |

## Report Tabs

- **Overview** — risk ring, AI executive summary (LLaMA 3.1), rule-based summary, category bar chart
- **Findings Debugger** — per-finding ML breakdown, confidence scoring, context type, negation/joke flags
- **Evidence Log** — categorised evidence cards with confidence bars and detail fields
- **Timeline** — timestamped transcript segments with flagged sentence highlighting
- **Analytics** — radar chart, severity pie chart, full stats object
- **Raw Data** — full report JSON with copy button

## Components

- `Chatbot.jsx` — AI chatbot sidebar powered by the backend RAG endpoint (`POST /chat`)

---

## Setup

```bash
npm install
npm run dev       # dev server at http://localhost:5173
npm run build     # production build → dist/
npm run preview   # preview production build
```

The Vite dev server proxies all `/api/v1/*` requests to `http://localhost:8000` — the backend must be running.

## Stack

| Package | Version | Purpose |
|---|---|---|
| React | 19 | UI framework |
| Vite | 8 | Build tool + dev server |
| React Router | 7 | Client-side routing |
| Axios | 1.x | HTTP client |
| Recharts | 3.x | Bar, radar, pie charts |
| Lucide React | 1.x | Icons |

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
