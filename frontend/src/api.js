import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
});

export const getHistory = async (skip = 0, limit = 100) => {
  const response = await api.get('/history', { params: { skip, limit } });
  return response.data;
};

export const getReport = async (id) => {
  const response = await api.get(`/report/${id}`);
  return response.data;
};

export const getReportStatus = async (id) => {
  const response = await api.get(`/report/${id}/status`);
  return response.data;
};

export const uploadAudio = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post('/analyze', formData, {
    onUploadProgress,
  });
  
  return response.data;
};

export const getChatbotAnswer = async (reportId, question) => {
  const response = await api.post('/chat', {
    report_id: reportId,
    question,
  });
  return response.data;
};

export const getAnalyticsSummary = async () => {
  const response = await api.get('/analytics/summary');
  return response.data;
};

export const sendAlertEmail = async (reportId, recipients = []) => {
  const response = await api.post(`/notify/alert/${reportId}`, { recipients: recipients.length ? recipients : null });
  return response.data;
};

export const sendSummaryEmail = async (reportId, recipients = []) => {
  const response = await api.post(`/notify/summary/${reportId}`, { recipients: recipients.length ? recipients : null });
  return response.data;
};

export const downloadPdfUrl = (reportId) => `/api/v1/report/${reportId}/pdf`;
