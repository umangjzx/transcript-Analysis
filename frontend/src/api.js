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

/**
 * Upload a video file for analysis.
 * Audio is extracted server-side; uses a longer timeout for large video files.
 */
export const uploadVideo = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/analyze/video', formData, {
    timeout: 1_800_000, // 30 minutes — 500 MB video on slow connections
    onUploadProgress,
  });

  return response.data;
};

/**
 * Submit a plain-text transcript directly for analysis (skips transcription).
 * @param {string} transcript - The transcript text
 * @param {string} filename   - Optional display name (e.g. "interview.txt")
 */
export const analyzeTranscript = async (transcript, filename = 'transcript_input.txt') => {
  const response = await api.post(
    '/analyze/transcript',
    { transcript, filename },
    { timeout: 600_000 },
  );
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
  console.log(`[deleteReport] Sending DELETE /api/v1/report/${id}`);
  try {
    const res = await api.delete(`/report/${id}`);
    console.log(`[deleteReport] Success, status=${res.status}`);
  } catch (err) {
    console.error(`[deleteReport] Failed:`, err?.response?.status, err?.response?.data, err?.message);
    throw err;
  }
};

// ── PDF download ──────────────────────────────────────────────────────────────

export const downloadPdfUrl = (reportId) => `/api/v1/report/${reportId}/pdf`;
