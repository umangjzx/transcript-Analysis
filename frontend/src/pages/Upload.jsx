import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud, FileAudio, FileVideo, FileText,
  AlertCircle, Loader2, CheckCircle,
} from 'lucide-react';
import { uploadAudio, uploadVideo, analyzeTranscript, uploadTranscriptFile, getReportStatus } from '../api';
import { useDataStore } from '../store/dataStore';

// ── Constants ─────────────────────────────────────────────────────────────────

const MAX_FILE_MB = 200;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
const MAX_VIDEO_MB = 500;
const MAX_VIDEO_BYTES = MAX_VIDEO_MB * 1024 * 1024;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;
const POLL_INITIAL_INTERVAL_MS = 2000;
const POLL_MAX_INTERVAL_MS = 30000;
const POLL_BACKOFF_FACTOR = 1.5;

const AUDIO_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.aac', '.ogg'];
const VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv'];
const TEXT_EXTENSIONS  = ['.txt'];

// ── Tab button ────────────────────────────────────────────────────────────────

const ModeTab = ({ active, onClick, icon: Icon, label }) => (
  <button
    onClick={onClick}
    style={{
      flex: 1,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.5rem',
      padding: '0.75rem 1rem',
      background: active
        ? 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))'
        : 'rgba(0,0,0,0.02)',
      border: active ? 'none' : '1px solid var(--border-color)',
      borderRadius: 'var(--radius-md)',
      color: active ? '#fff' : 'var(--text-secondary)',
      cursor: 'pointer',
      fontWeight: active ? 600 : 400,
      fontSize: '0.9rem',
      transition: 'all 0.2s ease',
    }}
  >
    <Icon size={18} />
    {label}
  </button>
);

// ── Shared progress / status UI ───────────────────────────────────────────────

const ProgressBar = ({ progress, statusMsg }) => (
  <div>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
      <span className="text-secondary">{statusMsg}</span>
      <span className="text-gradient font-bold">{Math.round(progress)}%</span>
    </div>
    <div
      style={{
        width: '100%', height: '8px',
        background: 'rgba(0,0,0,0.05)',
        borderRadius: '4px', overflow: 'hidden', marginBottom: '2rem',
      }}
    >
      <div
        className="glow-progress-bar"
        style={{
          height: '100%', width: `${progress}%`,
          background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
          transition: 'width 0.3s ease',
        }}
      />
    </div>
    <div className="flex-center" style={{ gap: '0.5rem', color: 'var(--text-secondary)' }}>
      <Loader2 size={20} style={{ animation: 'spin 2s linear infinite' }} />
      {progress >= 100
        ? <><CheckCircle size={16} style={{ color: 'var(--status-safe)' }} /> Redirecting...</>
        : 'Processing…'}
    </div>
  </div>
);

const ErrorBox = ({ message }) => (
  <div
    style={{
      background: 'var(--status-high-bg)', color: '#fca5a5',
      padding: '1rem', borderRadius: 'var(--radius-md)',
      marginBottom: '2rem', display: 'flex',
      alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
    }}
  >
    <AlertCircle size={20} /> {message}
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────

const Upload = () => {
  const navigate = useNavigate();
  const { refresh } = useDataStore();

  // 'audio' | 'video' | 'transcript'
  const [mode, setMode] = useState('audio');

  // Shared state
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [error, setError] = useState('');

  // Transcript-mode state
  const [transcriptText, setTranscriptText] = useState('');
  const [transcriptFilename, setTranscriptFilename] = useState('');
  const [transcriptFile, setTranscriptFile] = useState(null); // .txt file upload

  const fileInputRef = useRef(null);
  const txtInputRef  = useRef(null);

  // ── Helpers ────────────────────────────────────────────────────────────────

  const resetState = () => {
    setFile(null);
    setError('');
    setProgress(0);
    setStatusMsg('');
    setTranscriptText('');
    setTranscriptFilename('');
    setTranscriptFile(null);
  };

  const switchMode = (newMode) => {
    setMode(newMode);
    resetState();
  };

  const allowedExtensions = mode === 'video' ? VIDEO_EXTENSIONS : AUDIO_EXTENSIONS;

  const handleTxtFileSelect = (selectedFile) => {
    setError('');
    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase();
    if (ext !== '.txt') {
      setError('Only .txt files are supported for transcript upload.');
      return;
    }
    if (selectedFile.size > 10 * 1024 * 1024) {
      setError('File is too large. Maximum 10 MB for text files.');
      return;
    }
    setTranscriptFile(selectedFile);
    setTranscriptFilename(selectedFile.name);
    // Also read the file content into the textarea for preview
    const reader = new FileReader();
    reader.onload = (e) => setTranscriptText(e.target.result || '');
    reader.readAsText(selectedFile);
  };

  const handleFileSelect = (selectedFile) => {
    setError('');
    const maxBytes = mode === 'video' ? MAX_VIDEO_BYTES : MAX_FILE_BYTES;
    const maxMb    = mode === 'video' ? MAX_VIDEO_MB   : MAX_FILE_MB;
    if (selectedFile.size > maxBytes) {
      setError(`File is too large. Maximum allowed size is ${maxMb} MB.`);
      return;
    }
    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase();
    if (!allowedExtensions.includes(ext)) {
      setError(`Unsupported format "${ext}". Allowed: ${allowedExtensions.join(', ')}`);
      return;
    }
    setFile(selectedFile);
  };

  // ── Polling helper ─────────────────────────────────────────────────────────

  const pollUntilDone = (resultId, progressInterval) => {
    const pollStart = Date.now();
    let currentInterval = POLL_INITIAL_INTERVAL_MS;

    const poll = async () => {
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        clearInterval(progressInterval);
        setError(
          'Analysis is taking longer than expected. ' +
          'The job is still running — check the Dashboard for results.',
        );
        setIsProcessing(false);
        return;
      }
      try {
        const statusResult = await getReportStatus(resultId);
        if (statusResult.status === 'COMPLETED') {
          clearInterval(progressInterval);
          setProgress(100);
          setStatusMsg('Complete! Redirecting…');
          // Silently refresh the DataStore so Dashboard shows the new report
          refresh(true);
          setTimeout(() => navigate(`/report/${resultId}`), 600);
        } else if (statusResult.status === 'FAILED') {
          clearInterval(progressInterval);
          const backendMsg = statusResult.error_message;
          const niceMsg = backendMsg
            ? `Analysis failed: ${backendMsg}`
            : 'Analysis failed on the server. Please try again or contact an administrator with the report ID.';
          setError(niceMsg);
          setIsProcessing(false);
        } else {
          // Schedule next poll with exponential backoff
          currentInterval = Math.min(currentInterval * POLL_BACKOFF_FACTOR, POLL_MAX_INTERVAL_MS);
          setTimeout(poll, currentInterval);
        }
      } catch {
        clearInterval(progressInterval);
        setError('Lost connection to server while checking status. Check the Dashboard for results.');
        setIsProcessing(false);
      }
    };

    setTimeout(poll, currentInterval);
  };

  // ── Submit handlers ────────────────────────────────────────────────────────

  const handleFileUpload = async () => {
    if (!file) return;
    setIsProcessing(true);
    setError('');
    setProgress(0);
    setStatusMsg('Uploading file…');

    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.random() * 2, 85));
    }, 500);

    let result;
    try {
      const uploadFn = mode === 'video' ? uploadVideo : uploadAudio;
      result = await uploadFn(file, (evt) => {
        if (evt.total) {
          setProgress(Math.round((evt.loaded / evt.total) * 40));
        }
      });
    } catch (err) {
      clearInterval(progressInterval);
      const detail = err.response?.data?.detail;
      let msg = 'Failed to upload file. Please try again.';
      if (typeof detail === 'string') msg = detail;
      else if (Array.isArray(detail)) msg = detail[0]?.msg || msg;
      else if (err.code === 'ECONNABORTED') msg = 'Upload timed out. Try a smaller file.';
      setError(msg);
      setIsProcessing(false);
      return;
    }

    setStatusMsg(mode === 'video' ? 'Extracting audio & analyzing…' : 'Analyzing audio…');
    pollUntilDone(result.id, progressInterval);
  };

  const handleTranscriptSubmit = async () => {
    if (!transcriptText.trim() && !transcriptFile) {
      setError('Please paste a transcript or drop a .txt file before submitting.');
      return;
    }
    setIsProcessing(true);
    setError('');
    setProgress(10);
    setStatusMsg('Submitting transcript…');

    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.random() * 2, 85));
    }, 500);

    let result;
    try {
      if (transcriptFile) {
        // File upload path — sends multipart/form-data
        result = await uploadTranscriptFile(transcriptFile, (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 40));
        });
      } else {
        // JSON path — sends transcript text directly
        result = await analyzeTranscript(
          transcriptText.trim(),
          transcriptFilename.trim() || 'transcript_input.txt',
        );
      }
    } catch (err) {
      clearInterval(progressInterval);
      const detail = err.response?.data?.detail;
      let msg = 'Failed to submit transcript. Please try again.';
      if (typeof detail === 'string') msg = detail;
      setError(msg);
      setIsProcessing(false);
      return;
    }

    setStatusMsg('Analyzing transcript…');
    pollUntilDone(result.id, progressInterval);
  };

  // ── Drag & drop ────────────────────────────────────────────────────────────

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const modeConfig = {
    audio: {
      title: 'Analyze Audio',
      subtitle: `Upload an audio file to scan for grooming patterns and risks. Max ${MAX_FILE_MB} MB · ${AUDIO_EXTENSIONS.join(', ')}`,
      icon: FileAudio,
      dropLabel: 'Click or drag audio file here',
      dropSub: `Supported: ${AUDIO_EXTENSIONS.join(', ')} · Max ${MAX_FILE_MB} MB`,
    },
    video: {
      title: 'Analyze Video',
      subtitle: `Upload a video file — audio is extracted automatically. Max ${MAX_VIDEO_MB} MB · ${VIDEO_EXTENSIONS.join(', ')}`,
      icon: FileVideo,
      dropLabel: 'Click or drag video file here',
      dropSub: `Supported: ${VIDEO_EXTENSIONS.join(', ')} · Max ${MAX_VIDEO_MB} MB`,
    },
    transcript: {
      title: 'Analyze Transcript',
      subtitle: 'Paste or type a transcript directly — skips transcription and runs the full analysis pipeline.',
      icon: FileText,
    },
  };

  const cfg = modeConfig[mode];
  const FileIcon = cfg.icon;

  return (
    <div className="animate-fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="page-header" style={{ textAlign: 'center' }}>
        <h1 className="heading-1 page-title">{cfg.title}</h1>
        <p className="page-subtitle">{cfg.subtitle}</p>
      </div>

      {/* Mode tabs */}
      <div className="animate-slide-up delay-100" style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <ModeTab active={mode === 'audio'}      onClick={() => switchMode('audio')}      icon={FileAudio} label="Audio File" />
        <ModeTab active={mode === 'video'}      onClick={() => switchMode('video')}      icon={FileVideo} label="Video File" />
        <ModeTab active={mode === 'transcript'} onClick={() => switchMode('transcript')} icon={FileText}  label="Transcript Text" />
      </div>

      <div className="glass-panel animate-slide-up delay-200" style={{ padding: 'var(--spacing-2xl)' }}>

        {/* ── Audio / Video upload ── */}
        {(mode === 'audio' || mode === 'video') && (
          <>
            {!file ? (
              <div
                className={`upload-zone hover-lift-3d ${isDragging ? 'drag-active' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  border: isDragging ? '2px solid var(--accent-primary)' : '2px dashed var(--border-color)',
                  background: isDragging ? 'rgba(56, 189, 248, 0.05)' : 'transparent',
                  transition: 'all 0.3s ease'
                }}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  accept={allowedExtensions.join(',')}
                  onChange={(e) => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
                />
                <UploadCloud className="upload-icon" />
                <h3 className="heading-3" style={{ marginBottom: '0.5rem' }}>{cfg.dropLabel}</h3>
                <p className="text-secondary">{cfg.dropSub}</p>
              </div>
            ) : (
              <div style={{ textAlign: 'center' }}>
                <FileIcon size={64} className="text-gradient" style={{ margin: '0 auto 1.5rem auto' }} />
                <h3 className="heading-3">{file.name}</h3>
                <p className="text-secondary" style={{ marginBottom: '2rem' }}>
                  {(file.size / (1024 * 1024)).toFixed(2)} MB
                </p>

                {error && <ErrorBox message={error} />}

                {isProcessing ? (
                  <ProgressBar progress={progress} statusMsg={statusMsg} />
                ) : (
                  <div className="flex-center" style={{ gap: '1rem' }}>
                    <button className="btn btn-secondary" onClick={resetState}>Cancel</button>
                    <button className="btn btn-primary" onClick={handleFileUpload}>Start Analysis</button>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* ── Transcript text input ── */}
        {mode === 'transcript' && (
          <div>
            {error && <ErrorBox message={error} />}

            {/* .txt file drop zone */}
            {!isProcessing && (
              <div
                onDragOver={(e) => { e.preventDefault(); }}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0];
                  if (f) handleTxtFileSelect(f);
                }}
                onClick={() => txtInputRef.current?.click()}
                style={{
                  border: '2px dashed rgba(255,255,255,0.18)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1rem 1.25rem',
                  marginBottom: '1.25rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  cursor: 'pointer',
                  background: transcriptFile ? 'rgba(99,255,180,0.06)' : 'rgba(255,255,255,0.03)',
                  transition: 'background 0.2s',
                }}
              >
                <input
                  ref={txtInputRef}
                  type="file"
                  accept=".txt"
                  style={{ display: 'none' }}
                  onChange={(e) => { if (e.target.files?.[0]) handleTxtFileSelect(e.target.files[0]); }}
                />
                <FileText size={22} style={{ color: transcriptFile ? 'var(--status-safe)' : 'var(--text-tertiary)', flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  {transcriptFile ? (
                    <>
                      <span style={{ fontWeight: 600, color: 'var(--status-safe)', fontSize: '0.9rem' }}>
                        {transcriptFile.name}
                      </span>
                      <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                        ({(transcriptFile.size / 1024).toFixed(1)} KB) — content loaded below
                      </span>
                    </>
                  ) : (
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                      Drop a <strong>.txt</strong> file here or click to browse — content will be loaded automatically
                    </span>
                  )}
                </div>
                {transcriptFile && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setTranscriptFile(null); setTranscriptFilename(''); setTranscriptText(''); }}
                    style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: '0.2rem' }}
                  >
                    ✕
                  </button>
                )}
              </div>
            )}

            <div style={{ marginBottom: '1rem' }}>
              <label
                htmlFor="transcript-filename"
                style={{ display: 'block', marginBottom: '0.4rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}
              >
                Display name (optional)
              </label>
              <input
                id="transcript-filename"
                type="text"
                placeholder="e.g. interview_2026-05-26.txt"
                value={transcriptFilename}
                onChange={(e) => setTranscriptFilename(e.target.value)}
                disabled={isProcessing}
                style={{
                  width: '100%', padding: '0.6rem 0.9rem',
                  background: 'rgba(0,0,0,0.02)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-primary)', fontSize: '0.9rem',
                  outline: 'none', boxSizing: 'border-box',
                  transition: 'all 0.2s ease',
                }}
              />
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <label
                htmlFor="transcript-text"
                style={{ display: 'block', marginBottom: '0.4rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}
              >
                Transcript <span style={{ color: '#fca5a5' }}>*</span>
                <span style={{ marginLeft: '0.5rem', fontWeight: 400, color: 'var(--text-tertiary)', fontSize: '0.8rem' }}>
                  (paste text or drop a .txt file above)
                </span>
              </label>
              <textarea
                id="transcript-text"
                rows={14}
                placeholder="Paste or type the conversation transcript here…"
                value={transcriptText}
                onChange={(e) => { setTranscriptText(e.target.value); if (transcriptFile) setTranscriptFile(null); }}
                disabled={isProcessing}
                style={{
                  width: '100%', padding: '0.75rem 0.9rem',
                  background: 'rgba(0,0,0,0.02)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-primary)', fontSize: '0.9rem',
                  resize: 'vertical', outline: 'none',
                  fontFamily: 'inherit', lineHeight: 1.6,
                  boxSizing: 'border-box',
                  transition: 'all 0.2s ease',
                }}
              />
              <p style={{ marginTop: '0.3rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                {transcriptText.length.toLocaleString()} / 500,000 characters
              </p>
            </div>

            {isProcessing ? (
              <ProgressBar progress={progress} statusMsg={statusMsg} />
            ) : (
              <div className="flex-center" style={{ gap: '1rem' }}>
                <button className="btn btn-secondary" onClick={resetState}>Clear</button>
                <button
                  className="btn btn-primary"
                  onClick={handleTranscriptSubmit}
                  disabled={!transcriptText.trim() && !transcriptFile}
                >
                  Analyze Transcript
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        textarea:focus, input[type="text"]:focus {
          border-color: var(--accent-primary) !important;
        }
        textarea:disabled, input:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
};

export default Upload;
