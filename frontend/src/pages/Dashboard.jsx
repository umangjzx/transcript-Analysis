import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldAlert, Activity, FileAudio, Search, TrendingUp,
  CheckCircle, AlertTriangle, Clock, ChevronRight, RefreshCw
} from 'lucide-react';
import { getHistory } from '../api';

const getBadgeClass = (severity) => {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return 'badge-critical';
  if (s === 'high')     return 'badge-high';
  if (s === 'moderate' || s === 'medium') return 'badge-moderate';
  if (s === 'low')      return 'badge-low';
  return 'badge-safe';
};

const getRiskColor = (score) => {
  if (score >= 80) return 'var(--status-critical)';
  if (score >= 61) return 'var(--status-high)';
  if (score >= 41) return 'var(--status-moderate)';
  if (score >= 21) return 'var(--status-low)';
  return 'var(--status-safe)';
};

const MiniRiskBar = ({ score }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
    <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 99 }}>
      <div style={{
        width: `${score}%`, height: '100%', borderRadius: 99,
        background: getRiskColor(score), transition: 'width 0.6s ease'
      }} />
    </div>
    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: getRiskColor(score), minWidth: 36 }}>
      {score != null ? score.toFixed(0) : '—'}
    </span>
  </div>
);

const Dashboard = () => {
  const [history, setHistory]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState('');
  const [sortKey, setSortKey]   = useState('id');
  const [sortDir, setSortDir]   = useState('desc');
  const navigate = useNavigate();

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const data = await getHistory();
      // Backend returns a plain array
      setHistory(Array.isArray(data) ? data : (data.reports || []));
    } catch (err) {
      console.error('Failed to fetch history', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchHistory(); }, []);

  const highRisk    = history.filter(h => ['high','critical'].includes((h.severity || '').toLowerCase()));
  const safeCount   = history.filter(h => ['safe','low'].includes((h.severity || '').toLowerCase())).length;
  const avgScore    = history.length ? (history.reduce((s, h) => s + (h.risk_score || 0), 0) / history.length) : 0;

  const filtered = history
    .filter(h => (h.filename || '').toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      let va = a[sortKey], vb = b[sortKey];
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortIcon = ({ col }) => sortKey === col
    ? <span style={{ fontSize: '0.7rem', marginLeft: 3 }}>{sortDir === 'asc' ? '↑' : '↓'}</span>
    : null;

  return (
    <div className="animate-fade-in" style={{ padding: 'var(--spacing-xl)', maxWidth: 1400, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--spacing-2xl)' }}>
        <div>
          <h1 className="heading-1 page-title">Dashboard</h1>
          <p className="page-subtitle">All audio analyses — click any row to open the full report.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={fetchHistory} disabled={loading}>
            <RefreshCw size={16} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Refresh
          </button>
          <button className="btn btn-primary" onClick={() => navigate('/upload')}>
            <FileAudio size={16} /> Analyze New File
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="stats-grid">
        <div className="stat-card glass-panel">
          <div className="flex-between">
            <span className="stat-title">Total Analyzed</span>
            <FileAudio size={20} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <span className="stat-value text-gradient">{history.length}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>audio files processed</span>
        </div>

        <div className="stat-card glass-panel">
          <div className="flex-between">
            <span className="stat-title">High / Critical Risk</span>
            <ShieldAlert size={20} style={{ color: 'var(--status-high)' }} />
          </div>
          <span className="stat-value" style={{ color: 'var(--status-high)' }}>{highRisk.length}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
            {history.length ? `${((highRisk.length / history.length) * 100).toFixed(0)}% of total` : '—'}
          </span>
        </div>

        <div className="stat-card glass-panel">
          <div className="flex-between">
            <span className="stat-title">Average Risk Score</span>
            <TrendingUp size={20} style={{ color: 'var(--status-moderate)' }} />
          </div>
          <span className="stat-value" style={{ color: getRiskColor(avgScore) }}>{avgScore.toFixed(1)}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>out of 100</span>
        </div>

        <div className="stat-card glass-panel">
          <div className="flex-between">
            <span className="stat-title">Safe / Low Risk</span>
            <CheckCircle size={20} style={{ color: 'var(--status-safe)' }} />
          </div>
          <span className="stat-value" style={{ color: 'var(--status-safe)' }}>{safeCount}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>clean recordings</span>
        </div>
      </div>

      {/* Table Panel */}
      <div className="glass-panel">
        <div className="flex-between" style={{ padding: 'var(--spacing-lg) var(--spacing-xl)', borderBottom: '1px solid var(--border-color)' }}>
          <h2 className="heading-3">Analysis History</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.05)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-full)', border: '1px solid var(--border-color)' }}>
            <Search size={15} style={{ color: 'var(--text-tertiary)' }} />
            <input
              type="text"
              placeholder="Search files..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', width: 180 }}
            />
          </div>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th onClick={() => handleSort('id')} style={{ cursor: 'pointer', userSelect: 'none' }}>ID <SortIcon col="id" /></th>
                <th onClick={() => handleSort('filename')} style={{ cursor: 'pointer', userSelect: 'none' }}>File Name <SortIcon col="filename" /></th>
                <th onClick={() => handleSort('risk_score')} style={{ cursor: 'pointer', userSelect: 'none' }}>Risk Score <SortIcon col="risk_score" /></th>
                <th onClick={() => handleSort('severity')} style={{ cursor: 'pointer', userSelect: 'none' }}>Severity <SortIcon col="severity" /></th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                    <div className="loading-spinner" style={{ width: 32, height: 32 }} />
                    Loading analyses...
                  </div>
                </td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                  {search ? `No files matching "${search}"` : 'No analyses yet. Upload an audio file to begin.'}
                </td></tr>
              ) : filtered.map(item => (
                <tr key={item.id} onClick={() => navigate(`/report/${item.id}`)}>
                  <td style={{ color: 'var(--text-tertiary)', fontFamily: 'monospace', fontSize: '0.85rem' }}>#{item.id}</td>
                  <td style={{ fontWeight: 500, maxWidth: 350 }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.filename}>
                      {item.filename}
                    </div>
                  </td>
                  <td style={{ minWidth: 160 }}>
                    <MiniRiskBar score={item.risk_score} />
                  </td>
                  <td>
                    <span className={`badge ${getBadgeClass(item.severity)}`}>{item.severity || '—'}</span>
                  </td>
                  <td>
                    {item.status === 'PROCESSING' ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--status-moderate)', fontSize: '0.82rem' }}>
                        <Clock size={13} /> Processing...
                      </span>
                    ) : item.status === 'FAILED' ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--status-high)', fontSize: '0.82rem' }}>
                        <AlertTriangle size={13} /> Failed
                      </span>
                    ) : (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--status-safe)', fontSize: '0.82rem' }}>
                        <CheckCircle size={13} /> Complete
                      </span>
                    )}
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
                      onClick={e => { e.stopPropagation(); navigate(`/report/${item.id}`); }}
                    >
                      View <ChevronRight size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filtered.length > 0 && (
          <div style={{ padding: 'var(--spacing-md) var(--spacing-xl)', borderTop: '1px solid var(--border-color)', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
            Showing {filtered.length} of {history.length} records
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
