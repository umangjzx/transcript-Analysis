import axios from 'axios';

// All API calls go through the Vite proxy: /api/v1 → http://localhost:8000
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

// ── Auth token helpers ────────────────────────────────────────────────────────

export const getToken = () => localStorage.getItem('auth_token');
export const getStoredUser = () => {
  try { return JSON.parse(localStorage.getItem('auth_user') || 'null'); }
  catch { return null; }
};

export const saveAuth = (token, user) => {
  localStorage.setItem('auth_token', token);
  localStorage.setItem('auth_user', JSON.stringify(user));
};

export const clearAuth = () => {
  localStorage.removeItem('auth_token');
  localStorage.removeItem('auth_user');
  // Legacy key cleanup
  localStorage.removeItem('isAuthenticated');
};

// ── Attach JWT to every request ───────────────────────────────────────────────

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers['Authorization'] = `Bearer ${token}`;

  // Legacy X-API-Key support (if set in frontend .env)
  const apiKey = import.meta.env?.VITE_API_KEY;
  if (apiKey) config.headers['X-API-Key'] = apiKey;

  return config;
});

// ── Global 401 handler — redirect to login ────────────────────────────────────

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      clearAuth();
      // Only redirect if not already on the login page
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  },
);

// ── Auth ──────────────────────────────────────────────────────────────────────

/**
 * Log in with username + password.
 * Stores the JWT and user info in localStorage on success.
 */
export const login = async (username, password) => {
  // Auth routes are on the root backend, not under /api/v1
  const response = await axios.post('/auth/login', { username, password });
  const { access_token, username: user, role } = response.data;
  saveAuth(access_token, { username: user, role });
  return response.data;
};

/**
 * Log out — clears local storage and notifies the server (fire-and-forget).
 */
export const logout = async () => {
  try { await api.post('/auth/logout'); } catch { /* ignore */ }
  clearAuth();
};

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

/**
 * Upload a .txt transcript file directly for analysis (skips transcription).
 * @param {File} file - A .txt File object
 */
export const uploadTranscriptFile = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/analyze/transcript', formData, {
    timeout: 600_000,
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

// ── Google Drive ──────────────────────────────────────────────────────────────

/**
 * Get the Google OAuth2 consent URL.
 * Returns { auth_url: string }
 */
export const getDriveAuthUrl = async () => {
  const response = await api.get('/google-drive/auth-url');
  return response.data;
};

/**
 * Check whether the backend is authenticated with Google Drive.
 * Returns { authenticated: boolean, message: string }
 */
export const getDriveStatus = async () => {
  const response = await api.get('/google-drive/status');
  return response.data;
};

/**
 * List importable files from Google Drive (.txt + Google Docs).
 * @param {number} pageSize  - Max files to return (1–100, default 50)
 * @param {string} search    - Optional filename search term
 */
export const getDriveFiles = async (pageSize = 50, search = undefined) => {
  const params = { page_size: pageSize };
  if (search) params.search = search;
  const response = await api.get('/google-drive/files', { params });
  return response.data;
};

/**
 * Import a Google Drive file as a transcript and start the analysis pipeline.
 * Returns { id, filename, status, message, source }
 * @param {string} fileId    - Google Drive file ID
 * @param {string} fileName  - Display name
 * @param {string} mimeType  - 'text/plain' or 'application/vnd.google-apps.document'
 */
export const importDriveFile = async (fileId, fileName, mimeType) => {
  const response = await api.post(
    '/google-drive/import',
    { file_id: fileId, file_name: fileName, mime_type: mimeType },
    { timeout: 60_000 },
  );
  return response.data;
};

/**
 * Revoke Google Drive credentials (disconnect).
 */
export const disconnectDrive = async () => {
  const response = await api.delete('/google-drive/logout');
  return response.data;
};

// ── Google Drive Watcher ──────────────────────────────────────────────────────

/**
 * Get the current auto-watcher status.
 * Returns { running, last_checked, files_processed, errors, poll_interval_seconds }
 */
export const getDriveWatcherStatus = async () => {
  const response = await api.get('/google-drive/watcher/status');
  return response.data;
};

/**
 * Start the background Drive polling watcher.
 */
export const startDriveWatcher = async () => {
  const response = await api.post('/google-drive/watcher/start');
  return response.data;
};

/**
 * Stop the background Drive polling watcher.
 */
export const stopDriveWatcher = async () => {
  const response = await api.post('/google-drive/watcher/stop');
  return response.data;
};
