import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileAudio, AlertCircle, Loader2 } from 'lucide-react';
import { uploadAudio, getReportStatus } from '../api';

const Upload = () => {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (selectedFile) => {
    setError('');
    // Basic validation
    const validTypes = ['audio/mpeg', 'audio/wav', 'audio/x-m4a', 'audio/aac', 'audio/ogg', 'audio/mp4'];
    // We could check type, but checking extension is more reliable across browsers for these specific types
    setFile(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) return;
    
    setIsUploading(true);
    setError('');
    setProgress(0);
    
    try {
      // Fake progress for upload phase
      const progressInterval = setInterval(() => {
        setProgress(p => Math.min(p + Math.random() * 2, 85));
      }, 500);

      const result = await uploadAudio(file);
      
      // Start polling for backend completion
      const pollInterval = setInterval(async () => {
        try {
          const statusResult = await getReportStatus(result.id);
          if (statusResult.status === 'COMPLETED') {
            clearInterval(pollInterval);
            clearInterval(progressInterval);
            setProgress(100);
            setTimeout(() => {
              navigate(`/report/${result.id}`);
            }, 500);
          } else if (statusResult.status === 'FAILED') {
            clearInterval(pollInterval);
            clearInterval(progressInterval);
            setError(statusResult.error_message || 'Backend processing failed.');
            setIsUploading(false);
          }
        } catch (err) {
          clearInterval(pollInterval);
          clearInterval(progressInterval);
          setError('Lost connection to server while checking status.');
          setIsUploading(false);
        }
      }, 3000); // Check every 3 seconds
      
    } catch (err) {
      console.error(err);
      let errorMessage = 'Failed to upload and analyze file. Please try again.';
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          errorMessage = err.response.data.detail[0]?.msg || errorMessage;
        } else if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        }
      }
      setError(errorMessage);
      setIsUploading(false);
    }
  };

  return (
    <div className="animate-fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="page-header" style={{ textAlign: 'center' }}>
        <h1 className="heading-1 page-title">Analyze Audio</h1>
        <p className="page-subtitle">Upload an audio file to scan for grooming patterns, explicit content, and risks.</p>
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
              accept=".mp3,.wav,.m4a,.aac,.ogg"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileSelect(e.target.files[0]);
                }
              }}
            />
            <UploadCloud className="upload-icon" />
            <h3 className="heading-3" style={{ marginBottom: '0.5rem' }}>Click or drag audio file here</h3>
            <p className="text-secondary">Supported formats: .mp3, .wav, .m4a, .aac, .ogg</p>
          </div>
        ) : (
          <div style={{ textAlign: 'center' }}>
            <FileAudio size={64} className="text-gradient" style={{ margin: '0 auto 1.5rem auto' }} />
            <h3 className="heading-3">{file.name}</h3>
            <p className="text-secondary" style={{ marginBottom: '2rem' }}>{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
            
            {error && (
              <div style={{ background: 'var(--status-high-bg)', color: '#fca5a5', padding: '1rem', borderRadius: 'var(--radius-md)', marginBottom: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                <AlertCircle size={20} /> {error}
              </div>
            )}
            
            {isUploading ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span className="text-secondary">Analyzing...</span>
                  <span className="text-gradient font-bold">{Math.round(progress)}%</span>
                </div>
                <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden', marginBottom: '2rem' }}>
                  <div style={{ height: '100%', width: `${progress}%`, background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))', transition: 'width 0.3s ease' }}></div>
                </div>
                <div className="flex-center" style={{ gap: '0.5rem', color: 'var(--text-secondary)' }}>
                  <Loader2 size={20} className="spinner" style={{ animation: 'spin 2s linear infinite' }} /> Processing NLP models...
                </div>
              </div>
            ) : (
              <div className="flex-center" style={{ gap: '1rem' }}>
                <button className="btn btn-secondary" onClick={() => setFile(null)}>Cancel</button>
                <button className="btn btn-primary" onClick={handleUpload}>Start Analysis</button>
              </div>
            )}
          </div>
        )}
      </div>
      
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default Upload;
