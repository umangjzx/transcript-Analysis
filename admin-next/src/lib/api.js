import axios from 'axios';

// ─────────────────────────────────────────────────────────────────────────────
// API client (Next.js port of the original Vite api.js)
//
// Changes from the Vite version:
//   - baseURL is env-driven (NEXT_PUBLIC_API_BASE, default '/api/v1') and the
//     HTTP proxying is handled by next.config.js rewrites instead of vite proxy.
//   - import.meta.env.VITE_API_KEY  ->  process.env.NEXT_PUBLIC_API_KEY
//   - All window/sessionStorage/localStorage access is guarded with
//     `typeof window` so the module is safe to import during SSR.
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';
const isBrowser = typeof window !== 'undefined';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  withCredentials: true, // Send httpOnly cookies with every request
});

// ── AbortController management ────────────────────────────────────────────────

const _activeControllers = new Map();

export const createCancellable = (key) => {
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

export const cancelAllRequests = () => {
  for (const [, controller] of _activeControllers) {
    controller.abort();
  }
  _activeControllers.clear();
};

// ── Auth token helpers ────────────────────────────────────────────────────────

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

const _isTokenValid = (token) => {
  if (!token) return false;
  const payload = _decodeJwtPayload(token);
  if (!payload || !payload.exp) return false;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp > nowSeconds + 60;
};

export const getToken = () => {
  if (!isBrowser) return null;
  const token = localStorage.getItem('auth_token');
  if (token && _isTokenValid(token)) return token;
  // Token expired or missing — clear auth
  if (token) clearAuth();
  return null;
};

export const getStoredUser = () => {
  if (!isBrowser) return null;
  try { return JSON.parse(localStorage.getItem('auth_user') || 'null'); }
  catch { return null; }
};

export const saveAuth = (token, user) => {
  if (!isBrowser) return;
  localStorage.setItem('auth_token', token);
  localStorage.setItem('auth_user', JSON.stringify(user));
};

export const clearAuth = () => {
  if (!isBrowser) return;
  localStorage.removeItem('auth_user');
  localStorage.removeItem('auth_token');
  localStorage.removeItem('isAuthenticated');
};

// ── Cross-tab auth synchronization ───────────────────────────────────────────

if (isBrowser) {
  window.addEventListener('storage', (event) => {
    if (event.key === 'auth_user' && event.newValue === null) {
      sessionStorage.removeItem('access_token');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    if (event.key === 'auth_user' && event.newValue && !getToken()) {
      window.location.reload();
    }
  });
}

// ── Attach credentials to every request ───────────────────────────────────────

api.interceptors.request.use((config) => {
  // Send JWT as Bearer token in Authorization header.
  // This works through Vercel rewrites (unlike httpOnly cookies which get stripped).
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Global 401 handler — redirect to login ────────────────────────────────────

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && isBrowser) {
      clearAuth();
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  },
);

// ── Auth ──────────────────────────────────────────────────────────────────────

export const login = async (username, password) => {
  // Auth routes are on the root backend, not under /api/v1
  const response = await axios.post('/auth/login', { username, password }, {
    withCredentials: true,
  });
  const { access_token, username: user, role } = response.data;
  saveAuth(access_token, { username: user, role });
  return response.data;
};

export const logout = async () => {
  cancelAllRequests();
  try { await axios.post('/auth/logout', {}, { withCredentials: true }); } catch { /* ignore */ }
  clearAuth();
};

// ── History ───────────────────────────────────────────────────────────────────

export const getHistory = async (skip = 0, limit = 20, signal = null) => {
  const config = { params: { skip, limit } };
  if (signal) config.signal = signal;
  const response = await api.get('/history', config);
  const data = response.data;
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

export const uploadAudio = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/analyze', formData, {
    timeout: 600_000,
    onUploadProgress,
  });
  return response.data;
};

export const uploadVideo = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/analyze/video', formData, {
    timeout: 1_800_000,
    onUploadProgress,
  });
  return response.data;
};

export const analyzeTranscript = async (transcript, filename = 'transcript_input.txt') => {
  const response = await api.post(
    '/analyze/transcript',
    { transcript, filename },
    { timeout: 600_000 },
  );
  return response.data;
};

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

export const getChatbotAnswer = async (reportId, question) => {
  const response = await api.post(
    '/chat',
    { report_id: reportId, question },
    { timeout: 120_000 },
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
  await api.delete(`/report/${id}`);
};

export const bulkDeleteReports = async (ids) => {
  const response = await api.post('/reports/bulk-delete', { ids });
  return response.data;
};

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

export const downloadPdfUrl = (reportId) => `${API_BASE}/report/${reportId}/pdf`;

// ── Google Drive ──────────────────────────────────────────────────────────────

export const getDriveAuthUrl = async () => {
  const response = await api.get('/google-drive/auth-url');
  return response.data;
};

export const getDriveStatus = async () => {
  const response = await api.get('/google-drive/status');
  return response.data;
};

export const getDriveFiles = async (pageSize = 50, search = undefined) => {
  const params = { page_size: pageSize };
  if (search) params.search = search;
  const response = await api.get('/google-drive/files', { params });
  return response.data;
};

export const importDriveFile = async (fileId, fileName, mimeType) => {
  const response = await api.post(
    '/google-drive/import',
    { file_id: fileId, file_name: fileName, mime_type: mimeType },
    { timeout: 60_000 },
  );
  return response.data;
};

export const disconnectDrive = async () => {
  const response = await api.delete('/google-drive/logout');
  return response.data;
};

// ── Google Drive Watcher ──────────────────────────────────────────────────────

export const getDriveWatcherStatus = async () => {
  const response = await api.get('/google-drive/watcher/status');
  return response.data;
};

export const startDriveWatcher = async () => {
  const response = await api.post('/google-drive/watcher/start');
  return response.data;
};

export const stopDriveWatcher = async () => {
  const response = await api.post('/google-drive/watcher/stop');
  return response.data;
};

export default api;
