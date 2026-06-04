/**
 * Dashboard — Analysis history table.
 *
 * State comes from the global DataStore (no independent fetching).
 * Delete is optimistic: row disappears instantly, server call runs async.
 * New analyses pushed via WebSocket appear without refresh.
 */

import React, { useCallback, useDeferredValue, useMemo, useState, memo } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  ShieldAlert, Activity, FileAudio, Search, TrendingUp,
  CheckCircle, AlertTriangle, Clock, ChevronRight, RefreshCw,
  BarChart2, Brain, Trash2, X, Download, GitCompare,
  Square, CheckSquare,
} from 'lucide-react';
import { deleteReport, bulkDeleteReports, exportReportsCSV } from '../api';
import { useDataStore } from '../store/dataStore';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import toast from 'react-hot-toast';

// ── Helpers ───────────────────────────────────────────────────────────────────

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

const MiniRiskBar = memo(({ score }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
    <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 99 }}>
      <div style={{
        width: `${Math.min(100, score ?? 0)}%`, height: '100%', borderRadius: 99,
        background: getRiskColor(score), transition: 'width 0.4s ease',
      }} />
    </div>
    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: getRiskColor(score), minWidth: 36 }}>
      {score != null ? score.toFixed(0) : '—'}
    </span>
  </div>
));

// ── Component ─────────────────────────────────────────────────────────────────

const Dashboard = () => {
  const navigate = useNavigate();

  // ── Global store — no independent fetching ───────────────────────────────
  const {
    history, analytics, loading, refreshing,
    totalReports, stats, refresh, removeReport,
  } = useDataStore();

  // ── Local UI state ───────────────────────────────────────────────────────
  const [search, setSearch]               = useState('');
  const deferredSearch                    = useDeferredValue(search);
  const [datePreset, setDatePreset]       = useState('all');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [statusFilter, setStatusFilter]   = useState('all');
  const [startDate, setStartDate]         = useState('');
  const [endDate, setEndDate]             = useState('');
  const [sortKey, setSortKey]             = useState('id');
  const [sortDir, setSortDir]             = useState('desc');
  const [page, setPage]                   = useState(0);
  const pageSize                          = 20;

  // Delete UI state
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting]           = useState(null);

  // Bulk selection
  const [selectedIds, setSelectedIds]     = useState(new Set());
  const [bulkDeleting, setBulkDeleting]   = useState(false);

  // Keyboard navigation
  const [focusedRow, setFocusedRow]       = useState(-1);

  // ── Filtering + sorting ──────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = (deferredSearch || '').toLowerCase();
    let startMs = 0, endMs = Infinity;

    if (datePreset !== 'all') {
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      if (datePreset === 'today') { startMs = todayStart; }
      else if (datePreset === 'yesterday') { startMs = todayStart - 86400000; endMs = todayStart; }
      else if (datePreset === 'custom') {
        startMs = startDate ? new Date(startDate).getTime() : 0;
        endMs   = endDate   ? new Date(endDate).getTime() + 86400000 : Infinity;
      }
    }

    const out = history.filter(h => {
      if (q && !(h.filename || '').toLowerCase().includes(q)) return false;
      if (severityFilter !== 'all' && (h.severity || 'safe').toLowerCase() !== severityFilter) return false;
      if (statusFilter !== 'all' && (h.status || '').toLowerCase() !== statusFilter) return false;
      if (datePreset !== 'all') {
        if (!h.created_at) return false;
        const t = new Date(h.created_at).getTime();
        if (!(t >= startMs && t <= endMs)) return false;
      }
      return true;
    });

    out.sort((a, b) => {
      let va = a?.[sortKey], vb = b?.[sortKey];
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });

    return out;
  }, [history, deferredSearch, severityFilter, statusFilter, datePreset, startDate, endDate, sortKey, sortDir]);

  // Client-side page slice of filtered results
  const paginated = useMemo(
    () => filtered.slice(page * pageSize, (page + 1) * pageSize),
    [filtered, page, pageSize],
  );

  // Reset to page 0 when filters change
  const prevFilterKey = useMemo(
    () => `${deferredSearch}|${severityFilter}|${statusFilter}|${datePreset}|${sortKey}|${sortDir}`,
    [deferredSearch, severityFilter, statusFilter, datePreset, sortKey, sortDir],
  );
  const prevFilterRef = React.useRef(prevFilterKey);
  if (prevFilterRef.current !== prevFilterKey) {
    prevFilterRef.current = prevFilterKey;
    if (page !== 0) setPage(0);
  }

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleSort = useCallback((key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  }, [sortKey]);

  const SortIcon = ({ col }) => sortKey === col
    ? <span style={{ fontSize: '0.7rem', marginLeft: 3 }}>{sortDir === 'asc' ? '↑' : '↓'}</span>
    : null;

  // ── Optimistic delete ────────────────────────────────────────────────────
  const handleDeleteClick = (e, item) => { e.stopPropagation(); setConfirmDelete(item); };

  const handleDeleteConfirm = useCallback(async () => {
    if (!confirmDelete) return;
    const id = confirmDelete.id;
    setConfirmDelete(null);

    // 1. Optimistic: remove from UI instantly
    removeReport(id);
    setDeleting(id);

    // 2. Fire server delete async
    try {
      await deleteReport(id);
      toast.success(`Report #${id} deleted.`);
    } catch (err) {
      // Revert: re-fetch to restore the row
      toast.error(`Delete failed — ${err?.response?.data?.detail || err.message}`);
      refresh(true); // silent background refetch to restore state
    } finally {
      setDeleting(null);
    }
  }, [confirmDelete, removeReport, refresh]);

  // ── Bulk delete ──────────────────────────────────────────────────────────
  const toggleSelect = (id) => setSelectedIds(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const selectAll = () => {
    if (selectedIds.size === filtered.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(filtered.map(r => r.id)));
  };

  const handleBulkDelete = async () => {
    if (!selectedIds.size) return;
    setBulkDeleting(true);
    const ids = [...selectedIds];

    // Optimistic: remove all immediately
    ids.forEach(id => removeReport(id));
    setSelectedIds(new Set());

    const result = await bulkDeleteReports(ids);
    if (result.deleted.length) toast.success(`Deleted ${result.deleted.length} report(s)`);
    if (result.failed.length) {
      toast.error(`${result.failed.length} deletion(s) failed`);
      refresh(true); // restore any that failed
    }
    setBulkDeleting(false);
  };

  const handleBulkExport = () => {
    const toExport = selectedIds.size > 0
      ? filtered.filter(r => selectedIds.has(r.id))
      : filtered;
    const csv  = exportReportsCSV(toExport);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `melody-wings-reports-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${toExport.length} reports`);
  };

  const handleCompareSelected = () => {
    const ids = [...selectedIds].slice(0, 2);
    if (ids.length === 2) navigate(`/compare?ids=${ids[0]},${ids[1]}`);
    else toast.error('Select exactly 2 reports to compare');
  };

  // ── Keyboard shortcuts ───────────────────────────────────────────────────
  useKeyboardShortcuts({
    onNewAnalysis:  () => navigate('/upload'),
    onArrowUp:      () => setFocusedRow(r => Math.max(r - 1, 0)),
    onArrowDown:    () => setFocusedRow(r => Math.min(r + 1, paginated.length - 1)),
    onEnter:        () => { if (focusedRow >= 0 && paginated[focusedRow]) navigate(`/report/${paginated[focusedRow].id}`); },
    onDelete:       () => { if (focusedRow >= 0 && paginated[focusedRow]) setConfirmDelete(paginated[focusedRow]); },
    onSelectAll:    () => selectAll(),
  });

  // ── Render ───────────────────────────────────────────────────────────────
  const { highRisk, safeCount, avgScore } = stats;

  return (
    <div className="animate-fade-in" style={{ padding: 'var(--spacing-xl)', maxWidth: 1400, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--spacing-2xl)' }}>
        <div>
          <h1 className="heading-1 page-title">Dashboard</h1>
          <p className="page-subtitle">All audio analyses — click any row to open the full report.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {refreshing && (
            <span style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} /> Syncing…
            </span>
          )}
          <button className="btn btn-secondary" onClick={() => refresh(false)} disabled={loading}>
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
        <div className="stat-card glass-panel hover-lift animate-slide-up delay-100">
          <div className="flex-between">
            <span className="stat-title">Total Analyzed</span>
            <FileAudio size={20} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <span className="stat-value text-gradient">{totalReports}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>total files analyzed</span>
        </div>

        <div className="stat-card glass-panel hover-lift animate-slide-up delay-200">
          <div className="flex-between">
            <span className="stat-title">High / Critical Risk</span>
            <ShieldAlert size={20} style={{ color: 'var(--status-high)' }} />
          </div>
          <span className="stat-value" style={{ color: 'var(--status-high)' }}>{highRisk}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
            {history.length ? `${((highRisk / history.length) * 100).toFixed(0)}% of total` : '—'}
          </span>
        </div>

        <div className="stat-card glass-panel hover-lift animate-slide-up delay-300">
          <div className="flex-between">
            <span className="stat-title">Average Risk Score</span>
            <TrendingUp size={20} style={{ color: 'var(--status-moderate)' }} />
          </div>
          <span className="stat-value" style={{ color: getRiskColor(analytics?.avg_risk_score ?? avgScore) }}>
            {(analytics?.avg_risk_score ?? avgScore).toFixed(1)}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>out of 100</span>
        </div>

        <div className="stat-card glass-panel hover-lift animate-slide-up delay-400">
          <div className="flex-between">
            <span className="stat-title">Safe / Low Risk</span>
            <CheckCircle size={20} style={{ color: 'var(--status-safe)' }} />
          </div>
          <span className="stat-value" style={{ color: 'var(--status-safe)' }}>{safeCount}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>clean recordings</span>
        </div>

        {analytics && (
          <>
            <div className="stat-card glass-panel hover-lift animate-slide-up delay-500">
              <div className="flex-between">
                <span className="stat-title">Total Findings</span>
                <Activity size={20} style={{ color: 'var(--accent-secondary)' }} />
              </div>
              <span className="stat-value" style={{ color: 'var(--accent-secondary)' }}>{analytics.total_findings}</span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>across all reports</span>
            </div>
            <div className="stat-card glass-panel hover-lift animate-slide-up delay-600">
              <div className="flex-between">
                <span className="stat-title">High Confidence Detections</span>
                <Brain size={20} style={{ color: 'var(--accent-primary)' }} />
              </div>
              <span className="stat-value" style={{ color: 'var(--accent-primary)' }}>
                {analytics.high_confidence_count ?? '—'}
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                {analytics.total_findings
                  ? `${((analytics.high_confidence_count / analytics.total_findings) * 100).toFixed(0)}% of all findings`
                  : 'confidence ≥ 75%'}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Analytics shortcut row */}
      {analytics && (
        <div className="glass-panel" style={{ padding: 'var(--spacing-lg)', marginBottom: 'var(--spacing-xl)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <BarChart2 size={20} style={{ color: 'var(--accent-primary)' }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Analytics & Charts</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                {analytics.total_findings} findings · {analytics.total_reports} reports · Avg score {analytics.avg_risk_score?.toFixed(1)}
              </div>
            </div>
          </div>
          <button className="btn btn-primary" style={{ padding: '0.5rem 1.25rem', fontSize: '0.9rem' }} onClick={() => navigate('/analytics')}>
            <BarChart2 size={16} /> View Analytics
          </button>
        </div>
      )}

      {/* Table panel */}
      <div className="glass-panel animate-slide-up delay-400">
        {/* Table header / controls */}
        <div className="flex-between" style={{ padding: 'var(--spacing-lg) var(--spacing-xl)', borderBottom: '1px solid var(--border-color)', flexWrap: 'wrap', gap: '1rem' }}>
          <h2 className="heading-3">Analysis History</h2>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>

            {/* Bulk action bar */}
            {selectedIds.size > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.3rem 0.75rem', background: 'rgba(56,189,248,0.06)', borderRadius: 'var(--radius-full)', border: '1px solid rgba(56,189,248,0.15)' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-primary)' }}>{selectedIds.size} selected</span>
                <button className="btn btn-secondary" style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }} onClick={handleBulkExport} title="Export selected as CSV">
                  <Download size={13} /> Export
                </button>
                {selectedIds.size === 2 && (
                  <button className="btn btn-secondary" style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }} onClick={handleCompareSelected} title="Compare selected">
                    <GitCompare size={13} /> Compare
                  </button>
                )}
                <button
                  className="btn"
                  style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem', background: 'rgba(239,68,68,0.1)', color: 'var(--status-high)', border: '1px solid rgba(239,68,68,0.2)' }}
                  onClick={handleBulkDelete}
                  disabled={bulkDeleting}
                >
                  <Trash2 size={13} /> Delete
                </button>
                <button onClick={() => setSelectedIds(new Set())} style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: '0.2rem' }}>
                  <X size={14} />
                </button>
              </div>
            )}

            {/* Date filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <select value={datePreset} onChange={e => setDatePreset(e.target.value)}
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}>
                <option value="all" style={{ background: 'var(--bg-primary)' }}>All Time</option>
                <option value="today" style={{ background: 'var(--bg-primary)' }}>Today</option>
                <option value="yesterday" style={{ background: 'var(--bg-primary)' }}>Yesterday</option>
                <option value="custom" style={{ background: 'var(--bg-primary)' }}>Custom Range</option>
              </select>
              {datePreset === 'custom' && (
                <>
                  <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem' }} />
                  <span style={{ color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>to</span>
                  <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem' }} />
                  {(startDate || endDate) && (
                    <button className="btn-icon" onClick={() => { setStartDate(''); setEndDate(''); }} style={{ padding: '0.3rem' }}>
                      <X size={14} />
                    </button>
                  )}
                </>
              )}
            </div>

            {/* Severity + status filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}>
                <option value="all" style={{ background: 'var(--bg-primary)' }}>All Severities</option>
                <option value="safe"     style={{ background: 'var(--bg-primary)' }}>Safe</option>
                <option value="low"      style={{ background: 'var(--bg-primary)' }}>Low</option>
                <option value="moderate" style={{ background: 'var(--bg-primary)' }}>Moderate</option>
                <option value="high"     style={{ background: 'var(--bg-primary)' }}>High</option>
                <option value="critical" style={{ background: 'var(--bg-primary)' }}>Critical</option>
              </select>
              <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}>
                <option value="all"        style={{ background: 'var(--bg-primary)' }}>All Statuses</option>
                <option value="completed"  style={{ background: 'var(--bg-primary)' }}>Completed</option>
                <option value="processing" style={{ background: 'var(--bg-primary)' }}>Processing</option>
                <option value="failed"     style={{ background: 'var(--bg-primary)' }}>Failed</option>
              </select>
            </div>

            {/* Search */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.05)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-full)', border: '1px solid var(--border-color)', transition: 'all 0.2s' }}>
              <Search size={15} style={{ color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                placeholder="Search files..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', width: 180 }}
                onFocus={e => e.target.parentElement.style.borderColor = 'var(--accent-primary)'}
                onBlur={e => e.target.parentElement.style.borderColor = 'var(--border-color)'}
              />
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 40, padding: '0.5rem' }}>
                  <button onClick={selectAll}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: selectedIds.size === filtered.length && filtered.length > 0 ? 'var(--accent-primary)' : 'var(--text-tertiary)', display: 'flex', alignItems: 'center' }}>
                    {selectedIds.size === filtered.length && filtered.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                  </button>
                </th>
                <th onClick={() => handleSort('id')}         style={{ cursor: 'pointer', userSelect: 'none' }}>ID <SortIcon col="id" /></th>
                <th onClick={() => handleSort('filename')}   style={{ cursor: 'pointer', userSelect: 'none' }}>File Name <SortIcon col="filename" /></th>
                <th onClick={() => handleSort('risk_score')} style={{ cursor: 'pointer', userSelect: 'none' }}>Risk Score <SortIcon col="risk_score" /></th>
                <th onClick={() => handleSort('severity')}   style={{ cursor: 'pointer', userSelect: 'none' }}>Severity <SortIcon col="severity" /></th>
                <th onClick={() => handleSort('created_at')} style={{ cursor: 'pointer', userSelect: 'none' }}>Date & Time <SortIcon col="created_at" /></th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} style={{ opacity: 1 - i * 0.12 }}>
                    <td><div className="skeleton" style={{ height: 16, width: 16, borderRadius: 3 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: 40, borderRadius: 6 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: '85%', borderRadius: 6 }} /></td>
                    <td><div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><div className="skeleton" style={{ flex: 1, height: 6, borderRadius: 99 }} /><div className="skeleton" style={{ height: 14, width: 30, borderRadius: 6 }} /></div></td>
                    <td><div className="skeleton" style={{ height: 22, width: 64, borderRadius: 99 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: 90, borderRadius: 6 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: 70, borderRadius: 6 }} /></td>
                    <td><div style={{ display: 'flex', gap: '0.4rem' }}><div className="skeleton" style={{ height: 28, width: 56, borderRadius: 20 }} /><div className="skeleton" style={{ height: 28, width: 28, borderRadius: 8 }} /></div></td>
                  </tr>
                ))
              ) : paginated.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ padding: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4rem 2rem', gap: '1rem', textAlign: 'center' }}>
                      <div style={{ width: 72, height: 72, borderRadius: '50%', background: search ? 'rgba(245,158,11,0.1)' : 'rgba(56,189,248,0.1)', border: `2px solid ${search ? 'rgba(245,158,11,0.25)' : 'rgba(56,189,248,0.25)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {search ? <Search size={30} style={{ color: 'var(--status-moderate)' }} /> : <FileAudio size={30} style={{ color: 'var(--accent-primary)' }} />}
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
                          {search ? 'No Matches Found' : 'No Analyses Yet'}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-tertiary)', maxWidth: 340 }}>
                          {search ? `No files match "${search}". Try a different keyword or clear the search.` : 'Upload a transcript from Google Drive to get started with your first safety analysis.'}
                        </div>
                      </div>
                      {search ? (
                        <button className="btn btn-secondary" style={{ marginTop: '0.25rem', fontSize: '0.85rem', padding: '0.5rem 1.25rem' }} onClick={() => setSearch('')}>✕ Clear Search</button>
                      ) : (
                        <button className="btn btn-primary" style={{ marginTop: '0.25rem', fontSize: '0.85rem', padding: '0.5rem 1.4rem' }} onClick={() => navigate('/google-drive')}>Go to Google Drive</button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : paginated.map((item, i) => (
                <tr
                  key={item.id}
                  style={{
                    cursor: 'pointer',
                    background: focusedRow === i ? 'rgba(56,189,248,0.04)' : selectedIds.has(item.id) ? 'rgba(56,189,248,0.02)' : undefined,
                    outline: focusedRow === i ? '2px solid var(--accent-primary)' : 'none',
                    outlineOffset: '-2px',
                    opacity: deleting === item.id ? 0.4 : 1,
                    transition: 'opacity 0.2s',
                  }}
                  onClick={() => navigate(`/report/${item.id}`)}
                  role="button"
                  tabIndex={0}
                  aria-label={`View report ${item.filename}`}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/report/${item.id}`); } }}
                  onFocus={() => setFocusedRow(i)}
                >
                  <td style={{ width: 40, padding: '0.5rem' }} onClick={e => e.stopPropagation()}>
                    <button onClick={e => { e.stopPropagation(); toggleSelect(item.id); }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: selectedIds.has(item.id) ? 'var(--accent-primary)' : 'var(--text-tertiary)', display: 'flex', alignItems: 'center' }}>
                      {selectedIds.has(item.id) ? <CheckSquare size={15} /> : <Square size={15} />}
                    </button>
                  </td>
                  <td style={{ color: 'var(--text-tertiary)', fontFamily: 'monospace', fontSize: '0.85rem' }}>#{item.id}</td>
                  <td style={{ fontWeight: 500, maxWidth: 350 }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.filename}>{item.filename}</div>
                  </td>
                  <td style={{ minWidth: 160 }}><MiniRiskBar score={item.risk_score} /></td>
                  <td><span className={`badge ${getBadgeClass(item.severity)}`}>{item.severity || '—'}</span></td>
                  <td style={{ color: 'var(--text-tertiary)', fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
                    {item.created_at ? new Date(item.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                  </td>
                  <td>
                    {(item.status || '').toUpperCase() === 'PROCESSING' ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--status-moderate)', fontSize: '0.82rem' }}><Clock size={13} /> Processing…</span>
                    ) : (item.status || '').toUpperCase() === 'FAILED' ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--status-high)', fontSize: '0.82rem' }}><AlertTriangle size={13} /> Failed</span>
                    ) : (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--status-safe)', fontSize: '0.82rem' }}><CheckCircle size={13} /> Complete</span>
                    )}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                      <button type="button" className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.82rem' }} onClick={e => { e.stopPropagation(); navigate(`/report/${item.id}`); }}>
                        View <ChevronRight size={14} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-icon"
                        title="Delete report"
                        disabled={deleting === item.id}
                        onClick={e => { e.preventDefault(); e.stopPropagation(); handleDeleteClick(e, item); }}
                        style={{ padding: '0.35rem', color: deleting === item.id ? 'var(--text-tertiary)' : 'var(--status-high)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', background: 'transparent', cursor: deleting === item.id ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center' }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        {filtered.length > 0 && (
          <div style={{ padding: 'var(--spacing-md) var(--spacing-xl)', borderTop: '1px solid var(--border-color)', color: 'var(--text-tertiary)', fontSize: '0.82rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <span>Showing {paginated.length} of {filtered.length} filtered ({totalReports} total) — page {page + 1} of {Math.max(1, Math.ceil(filtered.length / pageSize))}</span>
              <button className="btn btn-secondary" style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }} onClick={handleBulkExport} title="Export visible as CSV">
                <Download size={12} /> Export CSV
              </button>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn btn-secondary" style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }} disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>← Previous</button>
              <button className="btn btn-secondary" style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }} disabled={(page + 1) * pageSize >= filtered.length} onClick={() => setPage(p => p + 1)}>Next →</button>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation modal */}
      {confirmDelete && createPortal(
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem', overflowY: 'auto' }}
          onClick={() => setConfirmDelete(null)}
        >
          <div className="glass-panel" style={{ maxWidth: 420, width: '100%', padding: '1.75rem', borderRadius: 'var(--radius-lg)', flexShrink: 0 }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <Trash2 size={20} style={{ color: 'var(--status-high)' }} />
                <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>Delete Report</span>
              </div>
              <button className="btn-icon" onClick={() => setConfirmDelete(null)} style={{ color: 'var(--text-tertiary)' }}><X size={18} /></button>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>Are you sure you want to permanently delete this report?</p>
            <div style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '0.75rem 1rem', marginBottom: '1.5rem', fontSize: '0.85rem' }}>
              <div style={{ color: 'var(--text-tertiary)', marginBottom: '0.2rem' }}>#{confirmDelete.id}</div>
              <div style={{ color: 'var(--text-primary)', fontWeight: 500, wordBreak: 'break-all' }}>{confirmDelete.filename}</div>
              {confirmDelete.severity && <span className={`badge ${getBadgeClass(confirmDelete.severity)}`} style={{ marginTop: '0.5rem', display: 'inline-block' }}>{confirmDelete.severity}</span>}
            </div>
            <p style={{ color: 'var(--text-tertiary)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>This will delete the database record and PDF report. This action cannot be undone.</p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button
                className="btn"
                style={{ background: 'var(--status-high)', color: '#fff', border: 'none', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                onClick={handleDeleteConfirm}
              >
                <Trash2 size={14} /> Delete
              </button>
            </div>
          </div>
        </div>
        , document.body)}
    </div>
  );
};

export default Dashboard;
