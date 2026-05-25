import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileAudio, AlertCircle, Loader2, CheckCircle } from 'lucide-react';
import { uploadAudio, getReportStatus } from '../api';

// Maximum file size shown to the user (must match backend MAX_UPLOAD_MB)
const MAX_FILE_MB = 200;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;

// How long to poll before giving up (10 minutes)
const POLL_TIMEOUT_MS = 10 * 60 * 1000;
// Poll interval
const POLL_INTERVAL_MS = 3000;

const VALID_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.aac', '.ogg'];

const Upload = () => {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('Uploading...');
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]);
  };

  const handleFileSelect = (selectedFile) => {
    setError('');

    // Client-side size check
    if (selectedFile.size > MAX_FILE_BYTES) {
      setError(`File is too large. Maximum allowed size is ${MAX_FILE_MB} MB.`);
      return;
    }

    // Client-side extension check
    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase();
    if (!VALID_EXTENSIONS.includes(ext)) {
      setError(`Unsupported format "${ext}". Allowed: ${VALID_EXTENSIONS.join(', ')}`);
      return;
    }

    setFile(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);
    setError('');
    setProgress(0);
    setStatusMsg('Uploading file...');

    // Animate progress bar during upload
    const progressInterval = setInterval(() => {
      setProgress((p) => Math.min(p + Math.random() * 2, 85));
    }, 500);

    let result;
    try {
      result = await uploadAudio(file, (evt) => {
        if (evt.total) {
          const pct = Math.round((evt.loaded / evt.total) * 40); // upload = 0–40%
          setProgress(pct);
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
      setIsUploading(false);
      return;
    }

    // Poll for completion
    setStatusMsg('Analyzing audio...');
    const pollStart = Date.now();

    const pollInterval = setInterval(async () => {
      // Timeout guard
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        clearInterval(pollInterval);
        clearInterval(progressInterval);
        setError(
          'Analysis is taking longer than expected. ' +
          'The job is still running — check the Dashboard for results.'
        );
        setIsUploading(false);
        return;
      }

      try {
        const statusResult = await getReportStatus(result.id);

        if (statusResult.status === 'COMPLETED') {
          clearInterval(pollInterval);
          clearInterval(progressInterval);
          setProgress(100);
          setStatusMsg('Complete! Redirecting...');
          setTimeout(() => navigate(`/report/${result.id}`), 600);

        } else if (statusResult.status === 'FAILED') {
          clearInterval(pollInterval);
          clearInterval(progressInterval);
          setError(statusResult.error_message || 'Analysis failed on the server.');
          setIsUploading(false);
        }
        // PROCESSING — keep polling
      } catch (err) {
        clearInterval(pollInterval);
        clearInterval(progressInterval);
        setError('Lost connection to server while checking status. Check the Dashboard for results.');
        setIsUploading(false);
      }
    }, POLL_INTERVAL_MS);
  };

  return (
    <div className="animate-fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="page-header" style={{ textAlign: 'center' }}>
        <h1 className="heading-1 page-title">Analyze Audio</h1>
        <p className="page-subtitle">
          Upload an audio file to scan for grooming patterns, explicit content, and risks.
          Max {MAX_FILE_MB} MB · {VALID_EXTENSIONS.join(', ')}
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 'var(--spacing-2xl)' }}>

        {!file ? (
          <div
            className={`upload-zone ${isDragging ? 'drag-active' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept={VALID_EXTENSIONS.join(',')}
              onChange={(e) => {
                if (e.target.files?.[0]) handleFileSelect(e.target.files[0]);
              }}
            />
            <UploadCloud className="upload-icon" />
            <h3 className="heading-3" style={{ marginBottom: '0.5rem' }}>
              Click or drag audio file here
            </h3>
            <p className="text-secondary">
              Supported: {VALID_EXTENSIONS.join(', ')} · Max {MAX_FILE_MB} MB
            </p>
          </div>
        ) : (
          <div style={{ textAlign: 'center' }}>
            <FileAudio
              size={64}
              className="text-gradient"
              style={{ margin: '0 auto 1.5rem auto' }}
            />
            <h3 className="heading-3">{file.name}</h3>
            <p className="text-secondary" style={{ marginBottom: '2rem' }}>
              {(file.size / (1024 * 1024)).toFixed(2)} MB
            </p>

            {error && (
              <div
                style={{
                  background: 'var(--status-high-bg)',
                  color: '#fca5a5',
                  padding: '1rem',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: '2rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                }}
              >
                <AlertCircle size={20} /> {error}
              </div>
            )}

            {isUploading ? (
              <div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: '0.5rem',
                  }}
                >
                  <span className="text-secondary">{statusMsg}</span>
                  <span className="text-gradient font-bold">{Math.round(progress)}%</span>
                </div>
                <div
                  style={{
                    width: '100%',
                    height: '8px',
                    background: 'rgba(255,255,255,0.1)',
                    borderRadius: '4px',
                    overflow: 'hidden',
                    marginBottom: '2rem',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${progress}%`,
                      background:
                        'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
                <div
                  className="flex-center"
                  style={{ gap: '0.5rem', color: 'var(--text-secondary)' }}
                >
                  <Loader2
                    size={20}
                    style={{ animation: 'spin 2s linear infinite' }}
                  />
                  {progress >= 100 ? (
                    <>
                      <CheckCircle size={16} style={{ color: 'var(--status-safe)' }} />
                      Redirecting...
                    </>
                  ) : (
                    'Processing NLP models...'
                  )}
                </div>
              </div>
            ) : (
              <div className="flex-center" style={{ gap: '1rem' }}>
                <button className="btn btn-secondary" onClick={() => { setFile(null); setError(''); }}>
                  Cancel
                </button>
                <button className="btn btn-primary" onClick={handleUpload}>
                  Start Analysis
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
      `}</style>
    </div>
  );
};

export default Upload;
