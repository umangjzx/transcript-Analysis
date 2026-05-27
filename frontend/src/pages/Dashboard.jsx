import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend, LineChart, Line, CartesianGrid,
  ScatterChart, Scatter, ZAxis, ReferenceLine,
} from 'recharts';
import {
  ShieldAlert, Activity, FileAudio, Search, TrendingUp,
  CheckCircle, AlertTriangle, Clock, ChevronRight, RefreshCw,
  BarChart2, Brain, Trash2, X,
} from 'lucide-react';
import { getHistory, getAnalyticsSummary, deleteReport } from '../api';

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

const SEV_COLORS = {
  critical: 'var(--status-critical)',
  high:     'var(--status-high)',
  moderate: 'var(--status-moderate)',
  medium:   'var(--status-moderate)',
  low:      'var(--status-low)',
  safe:     'var(--status-safe)',
  unknown:  'var(--text-tertiary)',
};

const HIST_COLORS = [
  'var(--status-safe)',
  'var(--status-low)',
  'var(--status-moderate)',
  'var(--status-high)',
  'var(--status-critical)',
];

const CONF_COLORS = [
  'var(--text-tertiary)',
  'var(--status-low)',
  'var(--status-moderate)',
  'var(--status-high)',
];

const CTX_COLORS = [
  'var(--status-critical)',
  'var(--accent-primary)',
  'var(--status-safe)',
  'var(--text-tertiary)',
  'var(--status-moderate)',
];

const capitalize = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

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

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
      <div style={{ fontWeight: 600, marginBottom: 2 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.fill || p.color }}>{p.name || 'Count'}: <strong>{p.value}</strong></div>
      ))}
    </div>
  );
};

const Dashboard = () => {
  const [history, setHistory]     = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState('');
  const [datePreset, setDatePreset] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate]     = useState('');
  const [sortKey, setSortKey]     = useState('id');
  const [sortDir, setSortDir]     = useState('desc');
  // Delete state
  const [confirmDelete, setConfirmDelete] = useState(null); // item to confirm
  const [deleting, setDeleting]           = useState(null); // id being deleted
  const navigate = useNavigate();

  const handleDeleteClick = (e, item) => {
    e.stopPropagation();
    setConfirmDelete(item);
  };

  const handleDeleteConfirm = async () => {
    if (!confirmDelete) return;
    const id = confirmDelete.id;
    console.log(`[Dashboard] handleDeleteConfirm called for id=${id}`);
    setDeleting(id);
    setConfirmDelete(null);
    try {
      await deleteReport(id);
      setHistory(prev => prev.filter(h => h.id !== id));
    } catch (err) {
      console.error('Delete failed', err);
      alert(`Failed to delete report #${id}: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [histData, analyticsData] = await Promise.all([
        getHistory(),
        getAnalyticsSummary().catch(() => null),
      ]);
      // getHistory() already normalises to an array in api.js
      setHistory(Array.isArray(histData) ? histData : (histData?.reports || []));
      setAnalytics(analyticsData);
    } catch (err) {
      console.error('Failed to fetch dashboard data', err);
      setHistory([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const highRisk  = history.filter(h => ['high','critical'].includes((h.severity || '').toLowerCase()));
  const safeCount = history.filter(h => ['safe','low'].includes((h.severity || '').toLowerCase())).length;
  const avgScore  = history.length ? (history.reduce((s, h) => s + (h.risk_score || 0), 0) / history.length) : 0;

  const filtered = history
    .filter(h => (h.filename || '').toLowerCase().includes(search.toLowerCase()))
    .filter(h => {
      if (datePreset === 'all') return true;
      if (!h.created_at) return false;
      const hDateObj = new Date(h.created_at);
      const hDate = hDateObj.getTime();
      
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      
      if (datePreset === 'today') {
        return hDate >= todayStart;
      }
      if (datePreset === 'yesterday') {
        const yesterdayStart = todayStart - 86400000;
        return hDate >= yesterdayStart && hDate < todayStart;
      }
      if (datePreset === 'custom') {
        if (!startDate && !endDate) return true;
        const start = startDate ? new Date(startDate).getTime() : 0;
        const end = endDate ? new Date(endDate).getTime() + 86400000 : Infinity;
        return hDate >= start && hDate <= end;
      }
      return true;
    })
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

  // ── Derived chart data from analytics summary ──────────────────────────────

  // Severity × Status stacked bar (replaces plain severity pie)
  const SEV_ORDER = ['Critical', 'High', 'Moderate', 'Low', 'Safe', 'Unknown'];
  const STATUS_COLORS = {
    COMPLETED: 'var(--status-safe)',
    PROCESSING: 'var(--status-moderate)',
    FAILED: 'var(--status-high)',
  };
  const statusStackData = analytics
    ? SEV_ORDER
        .filter(sev => (analytics.severity_distribution || {})[sev] > 0)
        .map(sev => {
          const total = (analytics.severity_distribution || {})[sev] || 0;
          // Approximate split: use status_distribution ratios applied to severity total
          const statusDist = analytics.status_distribution || {};
          const grandTotal = Object.values(statusDist).reduce((a, b) => a + b, 0) || 1;
          return {
            severity: sev,
            Completed: Math.round(total * ((statusDist.COMPLETED || 0) / grandTotal)),
            Processing: Math.round(total * ((statusDist.PROCESSING || 0) / grandTotal)),
            Failed: Math.round(total * ((statusDist.FAILED || 0) / grandTotal)),
            _total: total,
          };
        })
    : [];

  const riskHistData = analytics
    ? Object.entries(analytics.risk_score_histogram || {}).map(([range, count], i) => ({ range, count, fill: HIST_COLORS[i] }))
    : [];

  const topCatData = (analytics?.top_categories || []).slice(0, 8).map(d => ({
    name: capitalize(d.category),
    count: d.count,
  }));

  const ctxData = analytics
    ? Object.entries(analytics.context_type_totals || {}).map(([name, value], i) => ({
        name: capitalize(name), value,
      }))
    : [];

  const confHistData = analytics
    ? Object.entries(analytics.confidence_histogram || {}).map(([range, count], i) => ({
        range: range + '%', count, fill: CONF_COLORS[i],
      }))
    : [];

  // Findings timeline scatter: last 20 analyses, x=index, y=risk_score, size=finding count
  const timelineScatterData = [...history]
    .filter(h => h.created_at && h.risk_score != null)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .slice(-20)
    .map((h, i) => ({
      x: i + 1,
      y: Math.round(h.risk_score),
      z: 1,
      label: h.filename ? h.filename.slice(0, 14) + (h.filename.length > 14 ? '…' : '') : `#${h.id}`,
      severity: (h.severity || 'safe').toLowerCase(),
    }));

  // ── Risk Score Trend: last 20 analyses sorted by date ──────────────────────
  const trendData = [...history]
    .filter(h => h.created_at && h.risk_score != null)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .slice(-20)
    .map((h, i) => ({
      idx: i + 1,
      label: h.filename ? h.filename.slice(0, 12) + (h.filename.length > 12 ? '…' : '') : `#${h.id}`,
      score: Math.round(h.risk_score),
      severity: h.severity || 'safe',
    }));

  return (
    <div className="animate-fade-in" style={{ padding: 'var(--spacing-xl)', maxWidth: 1400, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--spacing-2xl)' }}>
        <div>
          <h1 className="heading-1 page-title">Dashboard</h1>
          <p className="page-subtitle">All audio analyses — click any row to open the full report.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={fetchAll} disabled={loading}>
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
        <div className="stat-card glass-panel hover-lift-3d animate-slide-up delay-100">
          <div className="flex-between">
            <span className="stat-title">Total Analyzed</span>
            <FileAudio size={20} style={{ color: 'var(--accent-primary)' }} />
          </div>
          <span className="stat-value text-gradient">{history.length}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>audio files processed</span>
        </div>

        <div className="stat-card glass-panel hover-lift-3d animate-slide-up delay-200">
          <div className="flex-between">
            <span className="stat-title">High / Critical Risk</span>
            <ShieldAlert size={20} style={{ color: 'var(--status-high)' }} />
          </div>
          <span className="stat-value" style={{ color: 'var(--status-high)' }}>{highRisk.length}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
            {history.length ? `${((highRisk.length / history.length) * 100).toFixed(0)}% of total` : '—'}
          </span>
        </div>

        <div className="stat-card glass-panel hover-lift-3d animate-slide-up delay-300">
          <div className="flex-between">
            <span className="stat-title">Average Risk Score</span>
            <TrendingUp size={20} style={{ color: 'var(--status-moderate)' }} />
          </div>
          <span className="stat-value" style={{ color: getRiskColor(avgScore) }}>{avgScore.toFixed(1)}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>out of 100</span>
        </div>

        <div className="stat-card glass-panel hover-lift-3d animate-slide-up delay-400">
          <div className="flex-between">
            <span className="stat-title">Safe / Low Risk</span>
            <CheckCircle size={20} style={{ color: 'var(--status-safe)' }} />
          </div>
          <span className="stat-value" style={{ color: 'var(--status-safe)' }}>{safeCount}</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>clean recordings</span>
        </div>

        {analytics && (
          <>
            <div className="stat-card glass-panel hover-lift-3d animate-slide-up delay-500">
              <div className="flex-between">
                <span className="stat-title">Total Findings</span>
                <Activity size={20} style={{ color: 'var(--accent-secondary)' }} />
              </div>
              <span className="stat-value" style={{ color: 'var(--accent-secondary)' }}>{analytics.total_findings}</span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>across all reports</span>
            </div>

            <div className="stat-card glass-panel hover-lift-3d animate-slide-up delay-600">
              <div className="flex-between">
                <span className="stat-title">High Confidence Detections</span>
                <Brain size={20} style={{ color: 'var(--accent-primary)' }} />
              </div>
              <span className="stat-value" style={{ color: 'var(--accent-primary)' }}>
                {analytics.high_confidence_count != null ? analytics.high_confidence_count : '—'}
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                {analytics.total_findings
                  ? `${analytics.total_findings > 0 ? ((analytics.high_confidence_count / analytics.total_findings) * 100).toFixed(0) : 0}% of all findings`
                  : 'confidence ≥ 75%'}
              </span>
            </div>
          </>
        )}
      </div>

      {/* ── Analytics Charts Row ─────────────────────────────────────────────── */}
      {analytics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--spacing-lg)', marginBottom: 'var(--spacing-xl)' }}>

          {/* Severity × Status Stacked Bar (replaces plain severity pie) */}
          {statusStackData.length > 0 && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
                <ShieldAlert size={16} style={{ color: 'var(--status-high)' }} />
                <h3 className="heading-3" style={{ margin: 0 }}>Severity Distribution</h3>
              </div>
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={statusStackData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <XAxis dataKey="severity" stroke="var(--text-tertiary)" fontSize={11} />
                    <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        const total = statusStackData.find(d => d.severity === label)?._total || 0;
                        return (
                          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                            <div style={{ fontWeight: 600, marginBottom: 4 }}>{label} <span style={{ color: 'var(--text-tertiary)' }}>({total} total)</span></div>
                            {payload.map((p, i) => p.value > 0 && (
                              <div key={i} style={{ color: p.fill }}>
                                {p.name}: <strong>{p.value}</strong>
                              </div>
                            ))}
                          </div>
                        );
                      }}
                      cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                    />
                    <Legend
                      wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 11, paddingTop: 8 }}
                    />
                    <Bar dataKey="Completed" stackId="a" fill="var(--status-safe)" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="Processing" stackId="a" fill="var(--status-moderate)" />
                    <Bar dataKey="Failed" stackId="a" fill="var(--status-high)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Risk Score Histogram */}
          {riskHistData.length > 0 && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
                <BarChart2 size={16} style={{ color: 'var(--accent-primary)' }} />
                <h3 className="heading-3" style={{ margin: 0 }}>Risk Score Distribution</h3>
              </div>
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={riskHistData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <XAxis dataKey="range" stroke="var(--text-tertiary)" fontSize={11} />
                    <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Reports">
                      {riskHistData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Top Categories Bar */}
          {topCatData.length > 0 && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
                <TrendingUp size={16} style={{ color: 'var(--accent-secondary)' }} />
                <h3 className="heading-3" style={{ margin: 0 }}>Top Risk Categories</h3>
              </div>
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={topCatData} layout="vertical" margin={{ top: 5, right: 30, left: 100, bottom: 5 }}>
                    <XAxis type="number" stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                    <YAxis dataKey="name" type="category" width={95} stroke="var(--text-secondary)" fontSize={11} tick={{ fill: 'var(--text-secondary)' }} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Occurrences">
                      {topCatData.map((_, i) => (
                        <Cell key={i} fill={i < 2 ? 'var(--status-critical)' : i < 4 ? 'var(--status-high)' : 'var(--status-moderate)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Findings Timeline Scatter (replaces Context Type donut) */}
          {timelineScatterData.length > 1 && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
                <Activity size={16} style={{ color: 'var(--accent-primary)' }} />
                <h3 className="heading-3" style={{ margin: 0 }}>Risk Score Scatter</h3>
                <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-tertiary)', fontWeight: 500 }}>
                  Last {timelineScatterData.length} analyses
                </span>
              </div>
              <div style={{ height: 260 }}>
                <ResponsiveContainer>
                  <ScatterChart margin={{ top: 8, right: 16, left: -10, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                    <XAxis
                      dataKey="x"
                      type="number"
                      name="Analysis"
                      stroke="var(--text-tertiary)"
                      fontSize={11}
                      tickCount={Math.min(timelineScatterData.length, 10)}
                      domain={[1, timelineScatterData.length]}
                      tick={{ fill: 'var(--text-tertiary)' }}
                      label={{ value: 'Analysis #', position: 'insideBottom', offset: -2, fill: 'var(--text-tertiary)', fontSize: 10 }}
                    />
                    <YAxis
                      dataKey="y"
                      type="number"
                      name="Risk Score"
                      stroke="var(--text-tertiary)"
                      fontSize={11}
                      domain={[0, 100]}
                      tickCount={6}
                      tick={{ fill: 'var(--text-tertiary)' }}
                    />
                    <ZAxis dataKey="z" range={[60, 60]} />
                    <ReferenceLine y={80} stroke="var(--status-critical)" strokeDasharray="4 3" strokeOpacity={0.5} />
                    <ReferenceLine y={61} stroke="var(--status-high)" strokeDasharray="4 3" strokeOpacity={0.4} />
                    <ReferenceLine y={41} stroke="var(--status-moderate)" strokeDasharray="4 3" strokeOpacity={0.35} />
                    <Tooltip
                      cursor={{ strokeDasharray: '3 3' }}
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0].payload;
                        const color = getRiskColor(d.y);
                        return (
                          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                            <div style={{ fontWeight: 600, marginBottom: 2, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.label}</div>
                            <div style={{ color }}>Risk Score: <strong>{d.y}</strong>/100</div>
                          </div>
                        );
                      }}
                    />
                    <Scatter
                      data={timelineScatterData}
                      shape={(props) => {
                        const { cx, cy, payload } = props;
                        const color = getRiskColor(payload.y);
                        return <circle cx={cx} cy={cy} r={7} fill={color} stroke="#fff" strokeWidth={1.5} fillOpacity={0.85} />;
                      }}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '1.25rem', marginTop: '0.5rem', fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                {[['var(--status-critical)', 'Critical 80+'], ['var(--status-high)', 'High 61–79'], ['var(--status-moderate)', 'Moderate 41–60'], ['var(--status-safe)', 'Safe <21']].map(([c, l]) => (
                  <span key={l} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }} />{l}
                  </span>
                ))}
              </div>
            </div>
          )}

              {confHistData.some(d => d.count > 0) && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
                <Brain size={16} style={{ color: 'var(--accent-primary)' }} />
                <h3 className="heading-3" style={{ margin: 0 }}>Detection Confidence</h3>
              </div>
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={confHistData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <XAxis dataKey="range" stroke="var(--text-tertiary)" fontSize={11} />
                    <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Reports">
                      {confHistData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {analytics.high_confidence_count != null && analytics.total_findings > 0 && (
                <div style={{ textAlign: 'center', marginTop: '0.5rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                  High confidence (≥75%): <strong style={{ color: 'var(--status-safe)' }}>
                    {analytics.high_confidence_count}
                  </strong>
                  <span style={{ marginLeft: '0.5rem', color: 'var(--text-tertiary)' }}>
                    of {analytics.total_findings} findings
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Risk Score Trend */}
          {trendData.length > 1 && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
                <TrendingUp size={16} style={{ color: 'var(--accent-primary)' }} />
                <h3 className="heading-3" style={{ margin: 0 }}>Risk Score Trend</h3>
                <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-tertiary)', fontWeight: 500 }}>Last {trendData.length} analyses</span>
              </div>
              <div style={{ height: 260 }}>
                <ResponsiveContainer>
                  <LineChart data={trendData} margin={{ top: 8, right: 16, left: -10, bottom: 30 }}>
                    <defs>
                      <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--accent-primary)" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="var(--accent-primary)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                    <XAxis
                      dataKey="label"
                      stroke="var(--text-tertiary)"
                      fontSize={10}
                      angle={-35}
                      textAnchor="end"
                      interval={0}
                      tick={{ fill: 'var(--text-tertiary)' }}
                    />
                    <YAxis
                      stroke="var(--text-tertiary)"
                      fontSize={11}
                      domain={[0, 100]}
                      tickCount={6}
                      tick={{ fill: 'var(--text-tertiary)' }}
                    />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        const score = payload[0].value;
                        const color =
                          score >= 80 ? 'var(--status-critical)'
                          : score >= 61 ? 'var(--status-high)'
                          : score >= 41 ? 'var(--status-moderate)'
                          : score >= 21 ? 'var(--status-low)'
                          : 'var(--status-safe)';
                        return (
                          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                            <div style={{ fontWeight: 600, marginBottom: 2, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
                            <div style={{ color }}>Risk Score: <strong>{score}</strong>/100</div>
                          </div>
                        );
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="score"
                      stroke="var(--accent-primary)"
                      strokeWidth={2.5}
                      dot={(props) => {
                        const score = props.payload.score;
                        const color =
                          score >= 80 ? 'var(--status-critical)'
                          : score >= 61 ? 'var(--status-high)'
                          : score >= 41 ? 'var(--status-moderate)'
                          : score >= 21 ? 'var(--status-low)'
                          : 'var(--status-safe)';
                        return <circle key={props.key} cx={props.cx} cy={props.cy} r={5} fill={color} stroke="#fff" strokeWidth={1.5} />;
                      }}
                      activeDot={{ r: 7, strokeWidth: 2 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '1.25rem', marginTop: '0.5rem', fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                {[['var(--status-critical)', 'Critical 80+'], ['var(--status-high)', 'High 61–79'], ['var(--status-moderate)', 'Moderate 41–60'], ['var(--status-safe)', 'Safe <21']].map(([c, l]) => (
                  <span key={l} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }} />{l}
                  </span>
                ))}
              </div>
            </div>
          )}

        </div>
      )}

      {/* Table Panel */}
      <div className="glass-panel animate-slide-up delay-400">
        <div className="flex-between" style={{ padding: 'var(--spacing-lg) var(--spacing-xl)', borderBottom: '1px solid var(--border-color)', flexWrap: 'wrap', gap: '1rem' }}>
          <h2 className="heading-3">Analysis History</h2>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            {/* Date Filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <select
                value={datePreset}
                onChange={(e) => setDatePreset(e.target.value)}
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem', cursor: 'pointer' }}
              >
                <option value="all" style={{ background: 'var(--bg-primary)' }}>All Time</option>
                <option value="today" style={{ background: 'var(--bg-primary)' }}>Today</option>
                <option value="yesterday" style={{ background: 'var(--bg-primary)' }}>Yesterday</option>
                <option value="custom" style={{ background: 'var(--bg-primary)' }}>Custom Range</option>
              </select>

              {datePreset === 'custom' && (
                <>
                  <input
                    type="date"
                    value={startDate}
                    onChange={e => setStartDate(e.target.value)}
                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem' }}
                    title="Start Date"
                  />
                  <span style={{ color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>to</span>
                  <input
                    type="date"
                    value={endDate}
                    onChange={e => setEndDate(e.target.value)}
                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', outline: 'none', fontFamily: 'inherit', fontSize: '0.85rem' }}
                    title="End Date"
                  />
                  {(startDate || endDate) && (
                    <button 
                      className="btn-icon" 
                      onClick={() => { setStartDate(''); setEndDate(''); }}
                      title="Clear custom dates"
                      style={{ padding: '0.3rem' }}
                    >
                      <X size={14} />
                    </button>
                  )}
                </>
              )}
            </div>

            {/* Search */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.05)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-full)', border: '1px solid var(--border-color)', transition: 'all 0.3s ease' }}>
              <Search size={15} style={{ color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                placeholder="Search files..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ background: 'transparent', border: 'none', color: 'white', outline: 'none', width: 180 }}
                onFocus={(e) => e.target.parentElement.style.borderColor = 'var(--accent-primary)'}
                onBlur={(e) => e.target.parentElement.style.borderColor = 'var(--border-color)'}
              />
            </div>
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
                <th onClick={() => handleSort('created_at')} style={{ cursor: 'pointer', userSelect: 'none' }}>Date <SortIcon col="created_at" /></th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                    <div className="loading-spinner" style={{ width: 32, height: 32 }} />
                    Loading analyses...
                  </div>
                </td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                  {search ? `No files matching "${search}"` : 'No analyses yet. Upload an audio file to begin.'}
                </td></tr>
              ) : filtered.map((item, i) => (
                <tr key={item.id} className="animate-slide-up" style={{ cursor: 'pointer', animationDelay: `${Math.min(i * 50, 500)}ms` }} onClick={() => navigate(`/report/${item.id}`)}>
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
                  <td style={{ color: 'var(--text-tertiary)', fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
                    {item.created_at
                      ? new Date(item.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
                      : '—'}
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
                  <td onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
                        onClick={e => { e.stopPropagation(); navigate(`/report/${item.id}`); }}
                      >
                        View <ChevronRight size={14} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-icon"
                        title="Delete report"
                        disabled={deleting === item.id}
                        onClick={e => {
                          e.preventDefault();
                          e.stopPropagation();
                          console.log(`[Dashboard] trash clicked for id=${item.id}`);
                          handleDeleteClick(e, item);
                        }}
                        style={{
                          padding: '0.35rem',
                          color: deleting === item.id ? 'var(--text-tertiary)' : 'var(--status-high)',
                          border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-sm)',
                          background: 'transparent',
                          cursor: deleting === item.id ? 'not-allowed' : 'pointer',
                          display: 'flex', alignItems: 'center',
                        }}
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

        {filtered.length > 0 && (
          <div style={{ padding: 'var(--spacing-md) var(--spacing-xl)', borderTop: '1px solid var(--border-color)', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
            Showing {filtered.length} of {history.length} records
          </div>
        )}
      </div>

      {/* ── Delete confirmation modal ─────────────────────────────────────── */}
      {confirmDelete && createPortal(
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.65)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '1rem',
            overflowY: 'auto',
          }}
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="glass-panel"
            style={{ maxWidth: 420, width: '100%', padding: '1.75rem', borderRadius: 'var(--radius-lg)', flexShrink: 0 }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <Trash2 size={20} style={{ color: 'var(--status-high)' }} />
                <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                  Delete Report
                </span>
              </div>
              <button
                className="btn-icon"
                onClick={() => setConfirmDelete(null)}
                style={{ color: 'var(--text-tertiary)' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
              Are you sure you want to permanently delete this report?
            </p>
            <div style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: '0.75rem 1rem',
              marginBottom: '1.5rem',
              fontSize: '0.85rem',
            }}>
              <div style={{ color: 'var(--text-tertiary)', marginBottom: '0.2rem' }}>
                #{confirmDelete.id}
              </div>
              <div style={{ color: 'var(--text-primary)', fontWeight: 500, wordBreak: 'break-all' }}>
                {confirmDelete.filename}
              </div>
              {confirmDelete.severity && (
                <span
                  className={`badge ${getBadgeClass(confirmDelete.severity)}`}
                  style={{ marginTop: '0.5rem', display: 'inline-block' }}
                >
                  {confirmDelete.severity}
                </span>
              )}
            </div>
            <p style={{ color: 'var(--text-tertiary)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>
              This will delete the database record and the PDF report from disk. This action cannot be undone.
            </p>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setConfirmDelete(null)}
              >
                Cancel
              </button>
              <button
                className="btn"
                style={{
                  background: 'var(--status-high)',
                  color: '#fff',
                  border: 'none',
                  display: 'flex', alignItems: 'center', gap: '0.4rem',
                }}
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
