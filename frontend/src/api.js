import axios from 'axios';

// All API calls go through the Vite proxy: /api/v1 → http://localhost:8000
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  withCredentials: true, // Send httpOnly cookies with every request
});

// ── AbortController management ────────────────────────────────────────────────
// Track active requests so they can be cancelled on unmount or navigation.

const _activeControllers = new Map();

/**
 * Create a cancellable request config with AbortController.
 * @param {string} key - Unique key for this request (used to cancel previous)
 * @returns {{ signal: AbortSignal, cancel: () => void }}
 */
export const createCancellable = (key) => {
  // Cancel any existing request with the same key
  if (_activeControllers.has(key)) {
    _activeControllers.get(key).abort();
  }
  const controller = new AbortController();
  _activeControllers.set(key, controller);
  return {
    signal: controller.signal,
    cancel: () => {
      controller.abort();
      _activeControllers.delete(key);
    },
  };
};

/**
 * Cancel all active requests (e.g., on logout or navigation).
 */
export const cancelAllRequests = () => {
  for (const [key, controller] of _activeControllers) {
    controller.abort();
  }
  _activeControllers.clear();
};

// ── Auth token helpers ────────────────────────────────────────────────────────
// JWT is stored in sessionStorage and sent as a Bearer header.
// The httpOnly cookie is also set by the server as a fallback.

/**
 * Decode a JWT payload without verification (client-side expiry check only).
 * Returns null if the token is malformed.
 */
const _decodeJwtPayload = (token) => {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload;
  } catch {
    return null;
  }
};

/**
 * Check if a JWT token is expired or about to expire (within 60s buffer).
 * Returns true if the token is still valid.
 */
const _isTokenValid = (token) => {
  if (!token) return false;
  const payload = _decodeJwtPayload(token);
  if (!payload || !payload.exp) return false;
  // Add 60-second buffer to prevent edge-case 401s
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp > nowSeconds + 60;
};

export const getToken = () => {
  const token = sessionStorage.getItem('access_token') || null;
  if (token && !_isTokenValid(token)) {
    // Token expired — clear auth proactively to prevent 401 redirect loops
    clearAuth();
    return null;
  }
  return token;
};

export const getStoredUser = () => {
  try { return JSON.parse(localStorage.getItem('auth_user') || 'null'); }
  catch { return null; }
};

export const saveAuth = (token, user) => {
  if (token) sessionStorage.setItem('access_token', token);
  localStorage.setItem('auth_user', JSON.stringify(user));
};

export const clearAuth = () => {
  sessionStorage.removeItem('access_token');
  localStorage.removeItem('auth_user');
  // Legacy key cleanup
  localStorage.removeItem('auth_token');
  localStorage.removeItem('isAuthenticated');
};

// ── Cross-tab auth synchronization ───────────────────────────────────────────
// Listen for auth changes in other tabs via localStorage events.
// When one tab logs out, all tabs redirect to login.

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === 'auth_user' && event.newValue === null) {
      // Another tab logged out — clear local state and redirect
      sessionStorage.removeItem('access_token');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    if (event.key === 'auth_user' && event.newValue && !getToken()) {
      // Another tab logged in — reload to pick up the session
      window.location.reload();
    }
  });
}

// ── Attach credentials to every request ───────────────────────────────────────
// JWT is sent as a Bearer token in the Authorization header.
// The httpOnly cookie is also sent as a fallback (withCredentials: true).

api.interceptors.request.use((config) => {
  // Attach JWT Bearer token
  const token = getToken();
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }

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
 * The server returns a JWT in the response body and also sets an httpOnly cookie.
 * We store the token in sessionStorage for Bearer header auth.
 */
export const login = async (username, password) => {
  // Auth routes are on the root backend, not under /api/v1
  const response = await axios.post('/auth/login', { username, password }, {
    withCredentials: true, // Receive the httpOnly cookie
  });
  const { access_token, username: user, role } = response.data;
  saveAuth(access_token, { username: user, role });
  return response.data;
};

/**
 * Log out — server clears the httpOnly cookie, we clear localStorage.
 */
export const logout = async () => {
  cancelAllRequests(); // Cancel all in-flight API requests
  try { await axios.post('/auth/logout', {}, { withCredentials: true }); } catch { /* ignore */ }
  clearAuth();
};

// ── History ───────────────────────────────────────────────────────────────────

/**
 * Fetch paginated analysis history.
 * Returns { reports: [...], total, skip, limit }
 * Falls back gracefully if the server returns a plain array (legacy).
 */
export const getHistory = async (skip = 0, limit = 20, signal = null) => {
  const config = { params: { skip, limit } };
  if (signal) config.signal = signal;
  const response = await api.get('/history', config);
  const data = response.data;
  // Return full paginated shape for server-side pagination
  if (Array.isArray(data)) return { reports: data, total: data.length };
  return data;
};

// ── Report ────────────────────────────────────────────────────────────────────

export const getReport = async (id, signal = null) => {
  const config = {};
  if (signal) config.signal = signal;
  const response = await api.get(`/report/${id}`, config);
  return response.data;
};

export const getReportStatus = async (id, signal = null) => {
  const config = {};
  if (signal) config.signal = signal;
  const response = await api.get(`/report/${id}/status`, config);
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

export const getAnalyticsSummary = async (signal = null) => {
  const config = {};
  if (signal) config.signal = signal;
  const response = await api.get('/analytics/summary', config);
  return response.data;
};

/**
 * Get LLM-generated insights explaining the analytics data.
 * Uses Ollama on the backend — may take 10-30s on first call.
 */
export const getAnalyticsInsights = async () => {
  const response = await api.post('/analytics/insights', {}, { timeout: 120_000 });
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

/**
 * Bulk delete multiple reports.
 * @param {number[]} ids - Array of report IDs to delete
 * @returns {Promise<{deleted: number[], failed: number[]}>}
 */
export const bulkDeleteReports = async (ids) => {
  const results = { deleted: [], failed: [] };
  // Delete sequentially to avoid overwhelming the server
  for (const id of ids) {
    try {
      await api.delete(`/report/${id}`);
      results.deleted.push(id);
    } catch {
      results.failed.push(id);
    }
  }
  return results;
};

/**
 * Export reports data as CSV.
 * @param {Array} reports - Array of report objects
 * @returns {string} CSV content
 */
export const exportReportsCSV = (reports) => {
  const headers = ['ID', 'Filename', 'Risk Score', 'Severity', 'Status', 'Date'];
  const rows = reports.map((r) => [
    r.id,
    `"${(r.filename || '').replace(/"/g, '""')}"`,
    r.risk_score?.toFixed(1) || '0',
    r.severity || 'Unknown',
    r.status || 'Unknown',
    r.created_at || '',
  ]);
  return [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
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
