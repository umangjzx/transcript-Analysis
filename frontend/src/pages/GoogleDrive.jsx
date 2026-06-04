import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  HardDrive, Link2, Link2Off, RefreshCw, FileText, FileCode,
  Download, AlertCircle, CheckCircle, Loader2, Search,
  ExternalLink, Clock, ChevronRight, Wifi, WifiOff,
  Play, Square, Activity, FileCheck,
} from 'lucide-react';
import {
  getDriveAuthUrl,
  getDriveStatus,
  getDriveFiles,
  importDriveFile,
  getReportStatus,
  getDriveWatcherStatus,
  startDriveWatcher,
  stopDriveWatcher,
} from '../api';
import { useDataStore } from '../store/dataStore';

// ── Constants ─────────────────────────────────────────────────────────────────

const POLL_INITIAL_INTERVAL_MS = 2000;
const POLL_MAX_INTERVAL_MS = 30000;
const POLL_BACKOFF_FACTOR = 1.5;
const POLL_TIMEOUT_MS  = 10 * 60 * 1000;

// ── Helpers ───────────────────────────────────────────────────────────────────

const getMimeLabel = (mimeType) => {
  if (mimeType === 'application/vnd.google-apps.document') return 'Google Doc';
  if (mimeType === 'text/plain') return '.txt';
  return mimeType || '—';
};

const getMimeIcon = (mimeType) => {
  if (mimeType === 'application/vnd.google-apps.document') return FileCode;
  return FileText;
};

const formatBytes = (bytes) => {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
};

// Normalise a raw Drive API file object (camelCase) to consistent snake_case fields
const normaliseFile = (f) => ({
  id:             f.id,
  name:           f.name,
  mime_type:      f.mimeType  ?? f.mime_type  ?? '',
  size:           f.size      ?? f.fileSize   ?? null,
  modified_time:  f.modifiedTime ?? f.modified_time ?? null,
  web_view_link:  f.webViewLink  ?? f.web_view_link  ?? null,
});

// ── Sub-components ────────────────────────────────────────────────────────────

const StatusBadge = ({ connected }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.4rem',
      padding: '0.3rem 0.75rem',
      borderRadius: 'var(--radius-full)',
      fontSize: '0.8rem',
      fontWeight: 600,
      background: connected ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)',
      color: connected ? 'var(--status-safe)' : 'var(--status-high)',
      border: `1px solid ${connected ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)'}`,
    }}
  >
    {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
    {connected ? 'Connected' : 'Not Connected'}
  </span>
);

const ErrorBox = ({ message }) => (
  <div
    style={{
      background: 'var(--status-high-bg)',
      color: '#fca5a5',
      padding: '0.9rem 1.1rem',
      borderRadius: 'var(--radius-md)',
      marginBottom: '1.25rem',
      display: 'flex',
      alignItems: 'center',
      gap: '0.6rem',
      fontSize: '0.9rem',
    }}
  >
    <AlertCircle size={18} style={{ flexShrink: 0 }} />
    {message}
  </div>
);

const ProgressBar = ({ progress, statusMsg }) => (
  <div>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
      <span className="text-secondary" style={{ fontSize: '0.9rem' }}>{statusMsg}</span>
      <span className="text-gradient font-bold">{Math.round(progress)}%</span>
    </div>
    <div
      style={{
        width: '100%', height: '8px',
        background: 'rgba(255,255,255,0.1)',
        borderRadius: '4px', overflow: 'hidden', marginBottom: '1.5rem',
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${progress}%`,
          background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
          transition: 'width 0.3s ease',
        }}
      />
    </div>
    <div className="flex-center" style={{ gap: '0.5rem', color: 'var(--text-secondary)' }}>
      <Loader2 size={18} style={{ animation: 'spin 2s linear infinite' }} />
      {progress >= 100 ? 'Redirecting…' : 'Analyzing…'}
    </div>
  </div>
);

// ── File row ──────────────────────────────────────────────────────────────────

const FileRow = ({ file, onImport, importing }) => {
  const FileIcon = getMimeIcon(file.mime_type);
  const isImporting = importing === file.id;

  return (
    <tr>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <FileIcon size={16} style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />
          <span
            style={{
              fontWeight: 500,
              maxWidth: 320,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={file.name}
          >
            {file.name}
          </span>
        </div>
      </td>
      <td>
        <span
          style={{
            fontSize: '0.78rem',
            padding: '0.2rem 0.55rem',
            borderRadius: 'var(--radius-full)',
            background: 'rgba(255,255,255,0.07)',
            color: 'var(--text-secondary)',
            border: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          {getMimeLabel(file.mime_type)}
        </span>
      </td>
      <td style={{ color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
        {formatBytes(file.size) || '—'}
      </td>
      <td style={{ color: 'var(--text-tertiary)', fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
        {formatDate(file.modified_time)}
      </td>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {file.web_view_link && (
            <a
              href={file.web_view_link}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="Open in Google Drive"
              style={{
                display: 'flex',
                alignItems: 'center',
                color: 'var(--text-tertiary)',
                padding: '0.3rem',
                borderRadius: 'var(--radius-sm)',
                transition: 'color 0.2s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent-primary)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
            >
              <ExternalLink size={14} />
            </a>
          )}
          <button
            className="btn btn-primary"
            style={{ padding: '0.35rem 0.9rem', fontSize: '0.82rem', minWidth: 90 }}
            onClick={() => onImport(file)}
            disabled={isImporting || !!importing}
          >
            {isImporting ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                Importing…
              </span>
            ) : (
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Download size={13} /> Import
              </span>
            )}
          </button>
        </div>
      </td>
    </tr>
  );
};

// ── Main component ────────────────────────────────────────────────────────────

const GoogleDrive = () => {
  const navigate = useNavigate();
  const { refresh } = useDataStore();

  const [connected, setConnected]     = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [files, setFiles]             = useState([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [search, setSearch]           = useState('');
  const [searchInput, setSearchInput] = useState('');
  // error state replaced by toast notifications

  // Import / analysis state
  const [importing, setImporting]     = useState(null); // file_id being imported
  const [analysisId, setAnalysisId]   = useState(null);
  const [progress, setProgress]       = useState(0);
  const [statusMsg, setStatusMsg]     = useState('');
  const [analyzing, setAnalyzing]     = useState(false);

  // Watcher state
  const [watcher, setWatcher]         = useState(null);  // { running, last_checked, files_processed, errors, poll_interval_seconds }
  const [watcherLoading, setWatcherLoading] = useState(false);

  // ── Auth status ────────────────────────────────────────────────────────────

  const checkStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const data = await getDriveStatus();
      setConnected(data.authenticated);
    } catch {
      setConnected(false);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  // Handle ?auth=success / ?auth=error redirected back from the OAuth callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authResult = params.get('auth');
    if (authResult === 'success') {
      toast.success('Google Drive connected successfully!');
      // Re-check status now that credentials are stored
      checkStatus();
    } else if (authResult === 'error') {
      const reason = params.get('reason') || 'unknown error';
      toast.error(`Google Drive connection failed: ${reason}`);
    }
    // Clean the query string so a refresh doesn't re-trigger the toast
    if (authResult) {
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [checkStatus]);

  // ── Watcher status ─────────────────────────────────────────────────────────

  const fetchWatcherStatus = useCallback(async () => {
    try {
      const data = await getDriveWatcherStatus();
      setWatcher(data);
    } catch {
      // non-fatal — watcher panel just won't show live data
    }
  }, []);

  // Poll watcher status every 10s when connected
  useEffect(() => {
    if (!connected) return;
    fetchWatcherStatus();
    const interval = setInterval(fetchWatcherStatus, 10_000);
    return () => clearInterval(interval);
  }, [connected, fetchWatcherStatus]);

  const handleWatcherToggle = async () => {
    setWatcherLoading(true);
    try {
      if (watcher?.running) {
        await stopDriveWatcher();
      } else {
        await startDriveWatcher();
      }
      await fetchWatcherStatus();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to toggle watcher.');
    } finally {
      setWatcherLoading(false);
    }
  };

  // ── Load files when connected ──────────────────────────────────────────────

  const loadFiles = useCallback(async (searchTerm = '') => {
    setFilesLoading(true);
    try {
      const data = await getDriveFiles(50, searchTerm || undefined);
      setFiles((data.files || []).map(normaliseFile));
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to load files from Google Drive.');
      setFiles([]);
    } finally {
      setFilesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (connected) loadFiles(search);
  }, [connected, search, loadFiles]);

  // ── Connect to Google Drive ────────────────────────────────────────────────

  const handleConnect = async () => {
    try {
      const data = await getDriveAuthUrl();
      // Open the OAuth consent screen in the same tab — Google redirects back to /callback
      window.location.href = data.auth_url;
    } catch (err) {
      toast.error('Could not get Google auth URL. Check your backend configuration.');
    }
  };

  // ── Search ─────────────────────────────────────────────────────────────────

  const handleSearch = (e) => {
    e.preventDefault();
    setSearch(searchInput.trim());
  };

  // ── Import + poll ──────────────────────────────────────────────────────────

  const pollUntilDone = (resultId) => {
    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.random() * 2, 88));
    }, 500);

    const pollStart = Date.now();
    let currentInterval = POLL_INITIAL_INTERVAL_MS;

    const poll = async () => {
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        clearInterval(progressInterval);
        toast.error('Analysis is taking longer than expected. Check the Dashboard for results.');
        setAnalyzing(false);
        setImporting(null);
        return;
      }
      try {
        const s = await getReportStatus(resultId);
        if (s.status === 'COMPLETED') {
          clearInterval(progressInterval);
          setProgress(100);
          setStatusMsg('Complete! Redirecting…');
          toast.success('Analysis complete! Opening report…');
          // Refresh DataStore so Dashboard shows the new report immediately
          refresh(true);
          setTimeout(() => navigate(`/report/${resultId}`), 700);
        } else if (s.status === 'FAILED') {
          clearInterval(progressInterval);
          toast.error(s.error_message || 'Analysis failed on the server.');
          setAnalyzing(false);
          setImporting(null);
        } else {
          // Schedule next poll with exponential backoff
          currentInterval = Math.min(currentInterval * POLL_BACKOFF_FACTOR, POLL_MAX_INTERVAL_MS);
          setTimeout(poll, currentInterval);
        }
      } catch {
        clearInterval(progressInterval);
        toast.error('Lost connection while checking status. Check the Dashboard for results.');
        setAnalyzing(false);
        setImporting(null);
      }
    };

    setTimeout(poll, currentInterval);
  };

  const handleImport = async (file) => {
    setImporting(file.id);
    setAnalyzing(true);
    setProgress(5);
    setStatusMsg(`Importing "${file.name}" from Google Drive…`);

    let result;
    try {
      result = await importDriveFile(file.id, file.name, file.mime_type);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to import file. Please try again.');
      setImporting(null);
      setAnalyzing(false);
      return;
    }

    setAnalysisId(result.id);
    setStatusMsg('Analyzing transcript…');
    setProgress(15);
    pollUntilDone(result.id);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="animate-fade-in" style={{ maxWidth: 1100, margin: '0 auto' }}>

      {/* Page header */}
      <div className="page-header" style={{ marginBottom: 'var(--spacing-xl)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 className="heading-1 page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <HardDrive size={30} style={{ color: 'var(--accent-primary)' }} />
              Google Drive
            </h1>
            <p className="page-subtitle">
              Import .txt files and Google Docs directly from your Drive for analysis — no upload needed.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {!statusLoading && <StatusBadge connected={connected} />}
            {connected && (
              <button
                className="btn btn-secondary"
                onClick={() => loadFiles(search)}
                disabled={filesLoading}
                title="Refresh file list"
              >
                <RefreshCw size={15} style={{ animation: filesLoading ? 'spin 1s linear infinite' : 'none' }} />
                Refresh
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Analysis in progress overlay ── */}
      {analyzing && (
        <div
          className="glass-panel animate-slide-up"
          style={{ padding: 'var(--spacing-2xl)', marginBottom: 'var(--spacing-xl)', textAlign: 'center' }}
        >
          <HardDrive size={48} style={{ color: 'var(--accent-primary)', margin: '0 auto 1rem auto' }} />
          <h2 className="heading-2" style={{ marginBottom: '0.5rem' }}>Importing & Analyzing</h2>
          <p className="text-secondary" style={{ marginBottom: '2rem' }}>
            {analysisId ? `Report #${analysisId}` : 'Starting…'}
          </p>
          <ProgressBar progress={progress} statusMsg={statusMsg} />
        </div>
      )}

      {/* ── Not connected panel ── */}
      {!statusLoading && !connected && !analyzing && (
        <div
          className="glass-panel animate-slide-up"
          style={{ padding: 'var(--spacing-2xl)', textAlign: 'center', marginBottom: 'var(--spacing-xl)' }}
        >
          <div
            style={{
              width: 72, height: 72,
              borderRadius: '50%',
              background: 'rgba(99,102,241,0.12)',
              border: '2px solid rgba(99,102,241,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 1.5rem auto',
            }}
          >
            <Link2Off size={32} style={{ color: 'var(--accent-primary)' }} />
          </div>

          <h2 className="heading-2" style={{ marginBottom: '0.75rem' }}>Connect Google Drive</h2>
          <p className="text-secondary" style={{ maxWidth: 480, margin: '0 auto 2rem auto', lineHeight: 1.6 }}>
            Grant read-only access to your Google Drive so Melody Wings Safety can list and import
            text files and Google Docs for analysis. No files are modified.
          </p>



          <button className="btn btn-primary" style={{ padding: '0.75rem 2rem', fontSize: '1rem' }} onClick={handleConnect}>
            <Link2 size={18} /> Connect Google Drive
          </button>

          <div
            style={{
              marginTop: '2rem',
              display: 'flex',
              justifyContent: 'center',
              gap: '2rem',
              flexWrap: 'wrap',
            }}
          >
            {[
              { icon: CheckCircle, text: 'Read-only access' },
              { icon: CheckCircle, text: '.txt files & Google Docs' },
              { icon: CheckCircle, text: 'No files modified' },
            ].map(({ icon: Icon, text }) => (
              <div key={text} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                <Icon size={14} style={{ color: 'var(--status-safe)' }} /> {text}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Loading status ── */}
      {statusLoading && (
        <div className="glass-panel" style={{ padding: 'var(--spacing-2xl)', textAlign: 'center' }}>
          <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent-primary)', margin: '0 auto 1rem auto' }} />
          <p className="text-secondary">Checking Google Drive connection…</p>
        </div>
      )}

      {/* ── Connected: file browser ── */}
      {connected && !analyzing && (
        <>
          {/* Connection status card */}
          <div
            className="glass-panel animate-slide-up delay-100"
            style={{
              padding: 'var(--spacing-lg) var(--spacing-xl)',
              marginBottom: 'var(--spacing-lg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div
                style={{
                  width: 40, height: 40,
                  borderRadius: '50%',
                  background: 'rgba(52,211,153,0.12)',
                  border: '1px solid rgba(52,211,153,0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <CheckCircle size={20} style={{ color: 'var(--status-safe)' }} />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Google Drive Connected</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                  Read-only · .txt files and Google Docs
                </div>
              </div>
            </div>

            {/* Search */}
            <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem' }}>
              <div
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  background: 'rgba(255,255,255,0.05)',
                  padding: '0.45rem 1rem',
                  borderRadius: 'var(--radius-full)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <Search size={14} style={{ color: 'var(--text-tertiary)' }} />
                <input
                  type="text"
                  placeholder="Search files…"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  style={{
                    background: 'transparent', border: 'none',
                    color: 'white', outline: 'none', width: 180, fontSize: '0.875rem',
                  }}
                />
              </div>
              <button type="submit" className="btn btn-secondary" style={{ padding: '0.45rem 1rem' }}>
                Search
              </button>
              {search && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.45rem 0.75rem' }}
                  onClick={() => { setSearch(''); setSearchInput(''); }}
                  title="Clear search"
                >
                  ✕
                </button>
              )}
            </form>
          </div>



          {/* ── Auto-watcher panel ── */}
          {watcher !== null && (
            <div
              className="glass-panel animate-slide-up delay-150"
              style={{
                padding: 'var(--spacing-lg) var(--spacing-xl)',
                marginBottom: 'var(--spacing-lg)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '1rem',
                borderLeft: `3px solid ${watcher.running ? 'var(--status-safe)' : 'var(--border-color)'}`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                {/* Status dot */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    background: watcher.running ? 'var(--status-safe)' : 'var(--text-tertiary)',
                    boxShadow: watcher.running ? '0 0 6px var(--status-safe)' : 'none',
                    animation: watcher.running ? 'pulse 2s ease-in-out infinite' : 'none',
                  }} />
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                    Auto-Watcher {watcher.running ? 'Running' : 'Stopped'}
                  </span>
                </div>

                {/* Stats */}
                <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    <Clock size={13} />
                    Every {watcher.poll_interval_seconds}s
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    <FileCheck size={13} />
                    {watcher.files_processed} file{watcher.files_processed !== 1 ? 's' : ''} processed
                  </div>
                  {watcher.errors > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', color: 'var(--status-high)' }}>
                      <AlertCircle size={13} />
                      {watcher.errors} error{watcher.errors !== 1 ? 's' : ''}
                    </div>
                  )}
                  {watcher.last_checked && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                      <Activity size={13} />
                      Last checked: {new Date(watcher.last_checked).toLocaleTimeString()}
                    </div>
                  )}
                </div>
              </div>

              {/* Toggle button */}
              <button
                className={`btn ${watcher.running ? 'btn-secondary' : 'btn-primary'}`}
                style={{ padding: '0.4rem 1rem', fontSize: '0.85rem', minWidth: 110 }}
                onClick={handleWatcherToggle}
                disabled={watcherLoading}
              >
                {watcherLoading ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Wait…
                  </span>
                ) : watcher.running ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Square size={14} /> Stop Watcher
                  </span>
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Play size={14} /> Start Watcher
                  </span>
                )}
              </button>
            </div>
          )}

          {/* File list */}
          <div className="glass-panel animate-slide-up delay-200">
            <div
              style={{
                padding: 'var(--spacing-lg) var(--spacing-xl)',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <h2 className="heading-3" style={{ margin: 0 }}>
                Drive Files
                {!filesLoading && (
                  <span style={{ marginLeft: '0.6rem', fontSize: '0.8rem', color: 'var(--text-tertiary)', fontWeight: 400 }}>
                    {files.length} file{files.length !== 1 ? 's' : ''}
                    {search ? ` matching "${search}"` : ''}
                  </span>
                )}
              </h2>
              {search && (
                <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Filtered by: <strong style={{ color: 'var(--accent-primary)' }}>"{search}"</strong>
                </span>
              )}
            </div>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>File Name</th>
                    <th>Type</th>
                    <th>Size</th>
                    <th>Last Modified</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filesLoading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} style={{ opacity: 1 - i * 0.15 }}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                            <div className="skeleton" style={{ width: 16, height: 16, borderRadius: 4, flexShrink: 0 }} />
                            <div className="skeleton" style={{ height: 14, width: '75%', borderRadius: 6 }} />
                          </div>
                        </td>
                        <td><div className="skeleton" style={{ height: 20, width: 60, borderRadius: 99 }} /></td>
                        <td><div className="skeleton" style={{ height: 14, width: 50, borderRadius: 6 }} /></td>
                        <td><div className="skeleton" style={{ height: 14, width: 80, borderRadius: 6 }} /></td>
                        <td><div className="skeleton" style={{ height: 28, width: 80, borderRadius: 20 }} /></td>
                      </tr>
                    ))
                  ) : files.length === 0 ? (
                    <tr>
                      <td colSpan="5" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                        {search
                          ? `No files matching "${search}". Try a different search term.`
                          : 'No .txt files or Google Docs found in your Drive.'}
                      </td>
                    </tr>
                  ) : (
                    files.map((file) => (
                      <FileRow
                        key={file.id}
                        file={file}
                        onImport={handleImport}
                        importing={importing}
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Footer hint */}
            {files.length > 0 && !filesLoading && (
              <div
                style={{
                  padding: 'var(--spacing-md) var(--spacing-xl)',
                  borderTop: '1px solid var(--border-color)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  color: 'var(--text-tertiary)',
                  fontSize: '0.8rem',
                }}
              >
                <Clock size={13} />
                Showing up to 50 files. Use search to narrow results.
                <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <ChevronRight size={13} />
                  Click <strong style={{ color: 'var(--text-secondary)' }}>Import</strong> to run the full analysis pipeline on any file.
                </span>
              </div>
            )}
          </div>

          {/* How it works */}
          <div
            className="glass-panel animate-slide-up delay-300"
            style={{ padding: 'var(--spacing-lg) var(--spacing-xl)', marginTop: 'var(--spacing-lg)' }}
          >
            <h3 className="heading-3" style={{ marginBottom: 'var(--spacing-md)' }}>How it works</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--spacing-md)' }}>
              {[
                { step: '1', title: 'Browse', desc: 'Your Drive files are listed here — .txt and Google Docs only.' },
                { step: '2', title: 'Import', desc: 'Click Import to download the file content directly from Drive.' },
                { step: '3', title: 'Analyze', desc: 'The full grooming detection pipeline runs on the text content.' },
                { step: '4', title: 'Report', desc: 'You\'re redirected to the full report with risk score and findings.' },
              ].map(({ step, title, desc }) => (
                <div key={step} style={{ display: 'flex', gap: '0.75rem' }}>
                  <div
                    style={{
                      width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                      background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.75rem', fontWeight: 700, color: '#fff',
                    }}
                  >
                    {step}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.2rem' }}>{title}</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
};

export default GoogleDrive;
