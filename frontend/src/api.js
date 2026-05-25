import axios from 'axios';

// All API calls go through the Vite proxy: /api/v1 → http://localhost:8000
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000, // 30 s default timeout for regular requests
});

// Attach X-API-Key header if VITE_API_KEY is set in the frontend .env
// (create frontend/.env with VITE_API_KEY=your-key to enable)
const _apiKey = import.meta.env?.VITE_API_KEY;
if (_apiKey) {
  api.defaults.headers.common['X-API-Key'] = _apiKey;
}

// ── History ───────────────────────────────────────────────────────────────────

/**
 * Fetch paginated analysis history.
 * Returns { reports: [...], total, skip, limit }
 * Falls back gracefully if the server returns a plain array (legacy).
 */
export const getHistory = async (skip = 0, limit = 100) => {
  const response = await api.get('/history', { params: { skip, limit } });
  const data = response.data;
  // Handle both new paginated shape { reports, total } and legacy plain array
  if (Array.isArray(data)) return data;
  return data.reports ?? data;
};

// ── Report ────────────────────────────────────────────────────────────────────

export const getReport = async (id) => {
  const response = await api.get(`/report/${id}`);
  return response.data;
};

export const getReportStatus = async (id) => {
  const response = await api.get(`/report/${id}/status`);
  return response.data;
};

// ── Upload & analyze ──────────────────────────────────────────────────────────

/**
 * Upload an audio file for analysis.
 * Uses a longer timeout (10 min) since large files can take time to upload.
 */
export const uploadAudio = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/analyze', formData, {
    timeout: 600_000, // 10 minutes — large files on slow connections
    onUploadProgress,
  });

  return response.data;
};

// ── Chatbot ───────────────────────────────────────────────────────────────────

/**
 * Ask the RAG chatbot a question about a specific report.
 * Uses a longer timeout since Ollama can be slow on CPU.
 */
export const getChatbotAnswer = async (reportId, question) => {
  const response = await api.post(
    '/chat',
    { report_id: reportId, question },
    { timeout: 120_000 }, // 2 minutes for LLM response
  );
  return response.data;
};

// ── Analytics ─────────────────────────────────────────────────────────────────

export const getAnalyticsSummary = async () => {
  const response = await api.get('/analytics/summary');
  return response.data;
};

// ── Email notifications ───────────────────────────────────────────────────────

export const sendAlertEmail = async (reportId, recipients = []) => {
  const response = await api.post(`/notify/alert/${reportId}`, {
    recipients: recipients.length ? recipients : null,
  });
  return response.data;
};

export const sendSummaryEmail = async (reportId, recipients = []) => {
  const response = await api.post(`/notify/summary/${reportId}`, {
    recipients: recipients.length ? recipients : null,
  });
  return response.data;
};

// ── Delete report ─────────────────────────────────────────────────────────────

export const deleteReport = async (id) => {
  await api.delete(`/report/${id}`);
};

// ── PDF download ──────────────────────────────────────────────────────────────

export const downloadPdfUrl = (reportId) => `/api/v1/report/${reportId}/pdf`;
