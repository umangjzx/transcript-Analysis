'use client';

/**
 * Dashboard — Analysis history table (Next.js port).
 */

import React, { useCallback, useDeferredValue, useMemo, useState, memo, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  ShieldAlert, Activity, FileAudio, Search, TrendingUp,
  CheckCircle, AlertTriangle, Clock, ChevronRight, RefreshCw,
  BarChart2, Brain, Trash2, X, Download, GitCompare,
  Square, CheckSquare,
} from 'lucide-react';
import { deleteReport, bulkDeleteReports, exportReportsCSV } from '@/lib/api';
import { useDataStore, useDataStoreStats } from '@/store/dataStore';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import toast from 'react-hot-toast';

// ── Helpers ───────────────────────────────────────────────────────────────────

const getBadgeClass = (severity) => {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return 'badge-critical';
  if (s === 'high') return 'badge-high';
  if (s === 'moderate' || s === 'medium') return 'badge-moderate';
  if (s === 'low') return 'badge-low';
  return 'badge-safe';
};

/** WCAG 1.4.1 — non-color indicator alongside colored badge */
const getSeverityIcon = (severity) => {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return '⬤';
  if (s === 'high') return '▲';
  if (s === 'moderate' || s === 'medium') return '◆';
  if (s === 'low') return '●';
  return '○';
};

const getRiskColor = (score) => {
  if (score >= 80) return 'var(--status-critical)';
  if (score >= 61) return 'var(--status-high)';
  if (score >= 41) return 'var(--status-moderate)';
  if (score >= 21) return 'var(--status-low)';
  return 'var(--status-safe)';
};

const MiniRiskBar = memo(({ score }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 90 }}>
    <div style={{ flex: 1, height: 6, background: 'rgba(15,23,42,0.08)', borderRadius: 99, minWidth: 50 }}>
      <div style={{
        width: `${Math.min(100, score ?? 0)}%`, height: '100%', borderRadius: 99,
        background: getRiskColor(score), transition: 'width 0.4s ease',
      }} />
    </div>
    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: getRiskColor(score), minWidth: 28 }}>
      {score != null ? score.toFixed(0) : '—'}
    </span>
  </div>
));
MiniRiskBar.displayName = 'MiniRiskBar';

// ── Component ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();

  const history = useDataStore((s) => s.history);
  const analytics = useDataStore((s) => s.analytics);
  const loading = useDataStore((s) => s.loading);
  const refreshing = useDataStore((s) => s.refreshing);
  const totalReports = useDataStore((s) => s.totalReports);
  const refresh = useDataStore((s) => s.refresh);
  const removeReport = useDataStore((s) => s.removeReport);
  const { highRisk, safeCount, avgScore } = useDataStoreStats();

  // ── Local UI state ───────────────────────────────────────────────────────
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [datePreset, setDatePreset] = useState('all');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [sortKey, setSortKey] = useState('id');
  const [sortDir, setSortDir] = useState('desc');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [focusedRow, setFocusedRow] = useState(-1);

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
        endMs = endDate ? new Date(endDate).getTime() + 86400000 : Infinity;
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

  const paginated = useMemo(
    () => filtered.slice(page * pageSize, (page + 1) * pageSize),
    [filtered, page, pageSize],
  );

  // ── Table virtualization for large datasets (200+) ───────────────────────
  const useVirtual = filtered.length >= 200;
  const tableContainerRef = useRef(null);
  const rowVirtualizer = useVirtualizer({
    count: useVirtual ? filtered.length : 0,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 52,
    overscan: 20,
    enabled: useVirtual,
  });

  // Items to render: virtualized full list or paginated subset
  const visibleItems = useVirtual
    ? rowVirtualizer.getVirtualItems().map(vi => ({ ...vi, item: filtered[vi.index] }))
    : paginated.map((item, i) => ({ index: i, item }));

  const prevFilterKey = useMemo(
    () => `${deferredSearch}|${severityFilter}|${statusFilter}|${datePreset}|${sortKey}|${sortDir}`,
    [deferredSearch, severityFilter, statusFilter, datePreset, sortKey, sortDir],
  );
  const prevFilterRef = useRef(prevFilterKey);
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

  const handleDeleteConfirm = useCallback(async () => {
    if (!confirmDelete) return;
    const id = confirmDelete.id;
    setConfirmDelete(null);
    removeReport(id);
    setDeleting(id);

    try {
      await deleteReport(id);
      toast.success(`Report #${id} deleted.`);
    } catch (err) {
      toast.error(`Delete failed — ${err?.response?.data?.detail || err.message}`);
      refresh(true);
    } finally {
      setDeleting(null);
    }
  }, [confirmDelete, removeReport, refresh]);

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
    ids.forEach(id => removeReport(id));
    setSelectedIds(new Set());

    const result = await bulkDeleteReports(ids);
    if (result.deleted.length) toast.success(`Deleted ${result.deleted.length} report(s)`);
    if (result.failed.length) {
      toast.error(`${result.failed.length} deletion(s) failed`);
      refresh(true);
    }
    setBulkDeleting(false);
  };

  const handleBulkExport = () => {
    const toExport = selectedIds.size > 0
      ? filtered.filter(r => selectedIds.has(r.id))
      : filtered;
    const csv = exportReportsCSV(toExport);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `melody-wings-reports-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${toExport.length} reports`);
  };

  const handleCompareSelected = () => {
    const ids = [...selectedIds].slice(0, 2);
    if (ids.length === 2) router.push(`/compare?ids=${ids[0]},${ids[1]}`);
    else toast.error('Select exactly 2 reports to compare');
  };

  useKeyboardShortcuts({
    onNewAnalysis: () => router.push('/upload'),
    onArrowUp: () => setFocusedRow(r => Math.max(r - 1, 0)),
    onArrowDown: () => setFocusedRow(r => Math.min(r + 1, paginated.length - 1)),
    onEnter: () => { if (focusedRow >= 0 && paginated[focusedRow]) router.push(`/report/${paginated[focusedRow].id}`); },
    onDelete: () => { if (focusedRow >= 0 && paginated[focusedRow]) setConfirmDelete(paginated[focusedRow]); },
    onSelectAll: () => selectAll(),
  });

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
          <button className="btn btn-primary" onClick={() => router.push('/upload')}>
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
          <span className="stat-value" style={{ color: 'var(--status-high)' }}>
            {analytics?.severity_distribution
              ? (analytics.severity_distribution.High || 0) + (analytics.severity_distribution.Critical || 0)
              : highRisk}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
            {totalReports ? `${((
              (analytics?.severity_distribution
                ? (analytics.severity_distribution.High || 0) + (analytics.severity_distribution.Critical || 0)
                : highRisk
              ) / totalReports) * 100).toFixed(0)}% of total` : '—'}
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
          <span className="stat-value" style={{ color: 'var(--status-safe)' }}>
            {analytics?.severity_distribution
              ? (analytics.severity_distribution.Safe || 0) + (analytics.severity_distribution.Low || 0)
              : safeCount}
          </span>
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

      {/* Analytics shortcut */}
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
          <button className="btn btn-primary" style={{ padding: '0.5rem 1.25rem', fontSize: '0.9rem' }} onClick={() => router.push('/analytics')}>
            <BarChart2 size={16} /> View Analytics
          </button>
        </div>
      )}

      {/* Table panel */}
      <div className="glass-panel animate-slide-up delay-400">
        <div className="flex-between" style={{ padding: 'var(--spacing-lg) var(--spacing-xl)', borderBottom: '1px solid var(--border-color)', flexWrap: 'wrap', gap: '1rem' }}>
          <h2 className="heading-3">Analysis History</h2>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
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

            {/* Filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <select value={datePreset} onChange={e => setDatePreset(e.target.value)}
                style={{ background: 'rgba(15,23,42,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}>
                <option value="all">All Time</option>
                <option value="today">Today</option>
                <option value="yesterday">Yesterday</option>
                <option value="custom">Custom Range</option>
              </select>
              {datePreset === 'custom' && (
                <>
                  <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} style={{ background: 'rgba(15,23,42,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem' }} />
                  <span style={{ color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>to</span>
                  <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} style={{ background: 'rgba(15,23,42,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem' }} />
                </>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}
                style={{ background: 'rgba(15,23,42,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}>
                <option value="all">All Severities</option>
                <option value="safe">Safe</option>
                <option value="low">Low</option>
                <option value="moderate">Moderate</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
              <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                style={{ background: 'rgba(15,23,42,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}>
                <option value="all">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(15,23,42,0.05)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-full)', border: '1px solid var(--border-color)' }}>
              <Search size={15} style={{ color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                placeholder="Search files..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', outline: 'none', width: 180 }}
              />
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="table-container" ref={tableContainerRef} style={useVirtual ? { maxHeight: '70vh', overflow: 'auto' } : undefined}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 40, padding: '0.5rem' }}>
                  <button onClick={selectAll} style={{ background: 'none', border: 'none', cursor: 'pointer', color: selectedIds.size === filtered.length && filtered.length > 0 ? 'var(--accent-primary)' : 'var(--text-tertiary)', display: 'flex', alignItems: 'center' }}>
                    {selectedIds.size === filtered.length && filtered.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                  </button>
                </th>
                <th onClick={() => handleSort('id')} style={{ cursor: 'pointer', userSelect: 'none', minWidth: 50 }}>ID <SortIcon col="id" /></th>
                <th onClick={() => handleSort('filename')} style={{ cursor: 'pointer', userSelect: 'none', minWidth: 200 }}>File Name <SortIcon col="filename" /></th>
                <th onClick={() => handleSort('risk_score')} style={{ cursor: 'pointer', userSelect: 'none', minWidth: 120 }}>Risk Score <SortIcon col="risk_score" /></th>
                <th onClick={() => handleSort('severity')} style={{ cursor: 'pointer', userSelect: 'none', minWidth: 100 }}>Severity <SortIcon col="severity" /></th>
                <th onClick={() => handleSort('created_at')} style={{ cursor: 'pointer', userSelect: 'none', minWidth: 140 }}>Date & Time <SortIcon col="created_at" /></th>
                <th style={{ minWidth: 90 }}>Status</th>
                <th style={{ minWidth: 100 }}></th>
              </tr>
            </thead>
            <tbody style={useVirtual ? { height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative', display: 'block' } : undefined}>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} style={{ opacity: 1 - i * 0.12 }}>
                    <td><div className="skeleton" style={{ height: 16, width: 16, borderRadius: 3 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: 40, borderRadius: 6 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: '85%', borderRadius: 6 }} /></td>
                    <td><div className="skeleton" style={{ height: 6, borderRadius: 99 }} /></td>
                    <td><div className="skeleton" style={{ height: 22, width: 64, borderRadius: 99 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: 90, borderRadius: 6 }} /></td>
                    <td><div className="skeleton" style={{ height: 14, width: 70, borderRadius: 6 }} /></td>
                    <td></td>
                  </tr>
                ))
              ) : visibleItems.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ padding: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4rem 2rem', gap: '1rem', textAlign: 'center' }}>
                      <FileAudio size={30} style={{ color: 'var(--accent-primary)' }} />
                      <div style={{ fontWeight: 700, fontSize: '1.05rem' }}>
                        {search ? 'No Matches Found' : 'No Analyses Yet'}
                      </div>
                      <div style={{ fontSize: '0.875rem', color: 'var(--text-tertiary)', maxWidth: 340 }}>
                        {search ? `No files match "${search}".` : 'Upload a transcript to get started.'}
                      </div>
                    </div>
                  </td>
                </tr>
              ) : visibleItems.map((vi) => {
                const item = vi.item;
                const i = vi.index;
                const rowStyle = useVirtual
                  ? { position: 'absolute', top: 0, left: 0, width: '100%', height: `${vi.size}px`, transform: `translateY(${vi.start}px)`, display: 'table-row' }
                  : {};
                return (
                  <tr
                    key={item.id}
                    style={{
                      ...rowStyle,
                      cursor: 'pointer',
                      background: focusedRow === i ? 'rgba(56,189,248,0.04)' : selectedIds.has(item.id) ? 'rgba(56,189,248,0.02)' : undefined,
                      opacity: deleting === item.id ? 0.4 : 1,
                    }}
                    onClick={() => router.push(`/report/${item.id}`)}
                  >
                    <td style={{ width: 40, padding: '0.5rem' }} onClick={e => e.stopPropagation()}>
                      <button onClick={e => { e.stopPropagation(); toggleSelect(item.id); }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: selectedIds.has(item.id) ? 'var(--accent-primary)' : 'var(--text-tertiary)', display: 'flex', alignItems: 'center' }}>
                        {selectedIds.has(item.id) ? <CheckSquare size={15} /> : <Square size={15} />}
                      </button>
                    </td>
                    <td style={{ color: 'var(--text-tertiary)', fontFamily: 'monospace', fontSize: '0.8rem' }}>#{item.id}</td>
                    <td style={{ fontWeight: 500 }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.filename}>{item.filename}</div>
                    </td>
                    <td style={{ minWidth: 120, maxWidth: 150 }}><MiniRiskBar score={item.risk_score} /></td>
                    <td style={{ minWidth: 90 }}><span className={`badge ${getBadgeClass(item.severity)}`} aria-label={`Severity: ${item.severity || 'Unknown'}`}>{getSeverityIcon(item.severity)} {item.severity || 'Unknown'}</span></td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                      {item.created_at ? new Date(item.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                    </td>
                    <td>
                      <span style={{
                        fontSize: '0.78rem', fontWeight: 600,
                        color: (item.status || '').toUpperCase() === 'COMPLETED' ? 'var(--status-safe)' :
                          (item.status || '').toUpperCase() === 'PROCESSING' ? 'var(--status-moderate)' :
                            'var(--status-high)',
                      }}>
                        {item.status || 'Unknown'}
                      </span>
                    </td>
                    <td onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                        <button className="btn btn-secondary" style={{ padding: '0.3rem 0.7rem', fontSize: '0.78rem' }} onClick={() => router.push(`/report/${item.id}`)}>
                          View <ChevronRight size={12} />
                        </button>
                        <button
                          className="btn-icon"
                          style={{ padding: '0.3rem', color: 'var(--text-tertiary)' }}
                          onClick={() => setConfirmDelete(item)}
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination (hidden when using virtualization) */}
        {!useVirtual && filtered.length > pageSize && (
          <div style={{ padding: 'var(--spacing-md) var(--spacing-xl)', borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
              Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, filtered.length)} of {filtered.length}
            </span>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn btn-secondary" style={{ padding: '0.3rem 0.8rem', fontSize: '0.82rem' }} disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</button>
              <button className="btn btn-secondary" style={{ padding: '0.3rem 0.8rem', fontSize: '0.82rem' }} disabled={(page + 1) * pageSize >= filtered.length} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setConfirmDelete(null)}>
          <div className="glass-panel" style={{ padding: '2rem', maxWidth: 400, textAlign: 'center' }} onClick={e => e.stopPropagation()}>
            <Trash2 size={32} style={{ color: 'var(--status-high)', margin: '0 auto 1rem' }} />
            <h3 className="heading-3" style={{ marginBottom: '0.5rem' }}>Delete Report #{confirmDelete.id}?</h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              This will permanently remove "{confirmDelete.filename}". This action cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              <button className="btn btn-secondary" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button className="btn" style={{ background: 'var(--status-high)', color: '#fff' }} onClick={handleDeleteConfirm}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
