'use client';

/**
 * Analytics — Dedicated page for all charts and visualizations.
 * Charts audit: removed low-value scatter/radar/status-donut,
 * fixed severity distribution, added ML calibration + risk heatmap.
 */

import React, { useCallback, useMemo, useState, memo } from 'react';
import { useRouter } from 'next/navigation';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend, LineChart, Line, CartesianGrid, ReferenceLine,
  AreaChart, Area,
} from 'recharts';
import {
  ShieldAlert, FileAudio, TrendingUp,
  BarChart2, Brain, RefreshCw, ArrowLeft,
  Eye, EyeOff, Sparkles, Loader2, ChevronDown, ChevronUp, Calendar,
} from 'lucide-react';
import { getAnalyticsInsights } from '@/lib/api';
import { useDataStore } from '@/store/dataStore';
import toast from 'react-hot-toast';

const getRiskColor = (score) => {
  if (score >= 80) return 'var(--status-critical)';
  if (score >= 61) return 'var(--status-high)';
  if (score >= 41) return 'var(--status-moderate)';
  if (score >= 21) return 'var(--status-low)';
  return 'var(--status-safe)';
};

const capitalize = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

const HIST_COLORS = [
  'var(--status-safe)', 'var(--status-low)',
  'var(--status-moderate)', 'var(--status-high)', 'var(--status-critical)',
];
const CONF_COLORS = [
  'var(--text-tertiary)', 'var(--status-low)',
  'var(--status-moderate)', 'var(--status-high)',
];

const SEV_ORDER = ['Critical', 'High', 'Moderate', 'Low', 'Safe'];
const SEV_COLORS = {
  Critical: 'var(--status-critical)',
  High: 'var(--status-high)',
  Moderate: 'var(--status-moderate)',
  Low: 'var(--status-low)',
  Safe: 'var(--status-safe)',
};

const ChartTooltip = memo(({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)', boxShadow: 'var(--shadow-md)' }}>
      <div style={{ fontWeight: 600, marginBottom: 2 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.fill || p.color }}>{p.name || 'Count'}: <strong>{p.value}</strong></div>
      ))}
    </div>
  );
});
ChartTooltip.displayName = 'ChartTooltip';

export default function AnalyticsPage() {
  const router = useRouter();
  const { history, analytics, loading, refreshing, refresh, totalReports } = useDataStore();

  // LLM Insights state
  const [insights, setInsights] = useState(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsExpanded, setInsightsExpanded] = useState(true);

  const [hiddenCharts, setHiddenCharts] = useState(() => {
    if (typeof window === 'undefined') return [];
    try { return JSON.parse(localStorage.getItem('analytics_hidden_charts') || '[]'); }
    catch { return []; }
  });

  const toggleChart = (chartId) => {
    setHiddenCharts((prev) => {
      const next = prev.includes(chartId) ? prev.filter((c) => c !== chartId) : [...prev, chartId];
      localStorage.setItem('analytics_hidden_charts', JSON.stringify(next));
      return next;
    });
  };
  const isVisible = (chartId) => !hiddenCharts.includes(chartId);

  const fetchInsights = useCallback(async () => {
    setInsightsLoading(true);
    try {
      const data = await getAnalyticsInsights();
      setInsights(data.insights || 'No insights available.');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setInsights(typeof detail === 'string' ? detail : 'Failed to generate insights. Make sure Ollama is running.');
    } finally {
      setInsightsLoading(false);
    }
  }, []);

  // ── Derived chart data ─────────────────────────────────────────────────────

  // FIXED: Severity Distribution — simple count per severity (no synthetic status split)
  const severityBarData = useMemo(() => {
    if (!analytics?.severity_distribution) return [];
    return SEV_ORDER
      .filter(sev => (analytics.severity_distribution[sev] || 0) > 0)
      .map(sev => ({
        severity: sev,
        count: analytics.severity_distribution[sev] || 0,
        fill: SEV_COLORS[sev],
      }));
  }, [analytics]);

  const riskHistData = useMemo(() => (
    analytics
      ? Object.entries(analytics.risk_score_histogram || {}).map(([range, count], i) => ({ range, count, fill: HIST_COLORS[i] }))
      : []
  ), [analytics]);

  const topCatData = useMemo(() => (
    (analytics?.top_categories || []).slice(0, 8).map(d => ({
      name: capitalize(d.category), count: d.count,
    }))
  ), [analytics]);

  const confHistData = useMemo(() => (
    analytics
      ? Object.entries(analytics.confidence_histogram || {}).map(([range, count], i) => ({
        range: range + '%', count, fill: CONF_COLORS[i],
      }))
      : []
  ), [analytics]);

  const trendData = useMemo(() => (
    [...history]
      .filter(h => h.created_at && h.risk_score != null)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
      .slice(-20)
      .map((h, i) => ({
        idx: i + 1,
        label: h.filename ? h.filename.slice(0, 12) + (h.filename.length > 12 ? '…' : '') : `#${h.id}`,
        score: Math.round(h.risk_score),
      }))
  ), [history]);

  const mlAgreementData = useMemo(() => {
    if (!analytics?.ml_agreement_totals) return [];
    const { agreed, disagreed, total } = analytics.ml_agreement_totals;
    if (!total) return [];
    const noSignal = total - agreed - disagreed;
    return [
      { name: 'Agreed', value: agreed },
      { name: 'Disagreed', value: disagreed },
      ...(noSignal > 0 ? [{ name: 'No Signal', value: noSignal }] : []),
    ].filter(d => d.value > 0);
  }, [analytics]);

  const volumeData = useMemo(() => {
    const byDate = {};
    history.filter(h => h.created_at).forEach(h => {
      const day = new Date(h.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      byDate[day] = (byDate[day] || 0) + 1;
    });
    return Object.entries(byDate).slice(-14).map(([date, count]) => ({ date, count }));
  }, [history]);

  const avgRiskByDay = useMemo(() => {
    const byDate = {};
    history.filter(h => h.created_at && h.risk_score != null).forEach(h => {
      const day = new Date(h.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      if (!byDate[day]) byDate[day] = { sum: 0, count: 0 };
      byDate[day].sum += h.risk_score;
      byDate[day].count += 1;
    });
    return Object.entries(byDate).slice(-14).map(([date, { sum, count }]) => ({ date, avg: Math.round(sum / count) }));
  }, [history]);

  const severityTrendData = useMemo(() => {
    const sorted = [...history]
      .filter(h => h.created_at && h.severity)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    if (sorted.length < 3) return [];
    const chunks = [];
    for (let i = 0; i < sorted.length; i += 5) {
      const chunk = sorted.slice(i, i + 5);
      const label = `${i + 1}-${Math.min(i + 5, sorted.length)}`;
      const counts = { label, Critical: 0, High: 0, Moderate: 0, Low: 0, Safe: 0 };
      chunk.forEach(h => {
        const sev = capitalize((h.severity || 'safe').toLowerCase());
        if (counts[sev] !== undefined) counts[sev]++;
        else counts.Safe++;
      });
      chunks.push(counts);
    }
    return chunks;
  }, [history]);

  // NEW: Risk Heatmap by Day of Week
  const riskByDayOfWeek = useMemo(() => {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const buckets = days.map(d => ({ day: d, count: 0, totalRisk: 0 }));
    history.filter(h => h.created_at && h.risk_score != null).forEach(h => {
      const dow = new Date(h.created_at).getDay();
      buckets[dow].count += 1;
      buckets[dow].totalRisk += h.risk_score;
    });
    return buckets.map(b => ({
      day: b.day,
      analyses: b.count,
      avgRisk: b.count > 0 ? Math.round(b.totalRisk / b.count) : 0,
    })).filter(b => b.analyses > 0);
  }, [history]);

  // NEW: ML Calibration — risk score distribution by ML agreement
  const mlCalibrationData = useMemo(() => {
    if (!analytics?.ml_agreement_totals) return [];
    const { agreed, disagreed, total, rate } = analytics.ml_agreement_totals;
    if (!total) return [];
    // Show agreement as a bar comparison
    return [
      { label: 'ML Agrees with Rules', value: agreed, fill: 'var(--status-safe)' },
      { label: 'ML Disagrees', value: disagreed, fill: 'var(--status-high)' },
      { label: 'No ML Signal', value: Math.max(0, total - agreed - disagreed), fill: 'var(--text-tertiary)' },
    ].filter(d => d.value > 0);
  }, [analytics]);

  // ── Stat summaries ─────────────────────────────────────────────────────────
  const { highRisk, safeCount, avgScore } = useMemo(() => {
    let high = 0, safe = 0, sum = 0;
    for (const h of history) {
      const sev = (h.severity || '').toLowerCase();
      if (sev === 'high' || sev === 'critical') high++;
      if (sev === 'safe' || sev === 'low') safe++;
      sum += (h.risk_score || 0);
    }
    return { highRisk: high, safeCount: safe, avgScore: history.length ? sum / history.length : 0 };
  }, [history]);

  const CHART_LIST = [
    { id: 'severity', label: 'Severity' },
    { id: 'risk-hist', label: 'Risk Distribution' },
    { id: 'top-cats', label: 'Top Categories' },
    { id: 'confidence', label: 'Confidence' },
    { id: 'trend', label: 'Risk Trend' },
    { id: 'ml-agreement', label: 'ML Agreement' },
    { id: 'ml-calibration', label: 'ML Calibration' },
    { id: 'volume', label: 'Volume' },
    { id: 'avg-risk-day', label: 'Avg Risk/Day' },
    { id: 'risk-heatmap', label: 'Risk by Weekday' },
    { id: 'severity-trend', label: 'Severity Trend' },
  ];

  if (loading) return (
    <div className="animate-fade-in" style={{ maxWidth: 1400, margin: '0 auto', padding: 'var(--spacing-xl)' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '40vh', gap: '1rem' }}>
        <div className="loading-spinner" />
        <p style={{ color: 'var(--text-secondary)' }}>Loading analytics...</p>
      </div>
    </div>
  );

  return (
    <div className="animate-fade-in" style={{ maxWidth: 1400, margin: '0 auto', padding: 'var(--spacing-xl)' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--spacing-xl)', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button className="btn btn-icon" onClick={() => router.push('/')} title="Back to Dashboard">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="heading-1 page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <BarChart2 size={28} style={{ color: 'var(--accent-primary)' }} />
              Analytics
            </h1>
            <p className="page-subtitle">Visualizations and insights across all analyses</p>
          </div>
        </div>
        <button className="btn btn-secondary" onClick={() => refresh(false)} disabled={loading || refreshing}>
          <RefreshCw size={16} style={{ animation: (loading || refreshing) ? 'spin 1s linear infinite' : 'none' }} />
          Refresh
        </button>
      </div>

      {/* Stat Cards */}
      <div className="stats-grid" style={{ marginBottom: 'var(--spacing-xl)' }}>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">Total Analyzed</span>
          <span className="stat-value">{analytics?.total_reports ?? totalReports}</span>
        </div>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">High / Critical</span>
          <span className="stat-value" style={{ color: 'var(--status-high)' }}>
            {analytics?.severity_distribution
              ? (analytics.severity_distribution.High || 0) + (analytics.severity_distribution.Critical || 0)
              : highRisk}
          </span>
        </div>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">Avg Risk Score</span>
          <span className="stat-value" style={{ color: getRiskColor(analytics?.avg_risk_score ?? avgScore) }}>{(analytics?.avg_risk_score ?? avgScore).toFixed(1)}</span>
        </div>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">Safe / Low</span>
          <span className="stat-value" style={{ color: 'var(--status-safe)' }}>
            {analytics?.severity_distribution
              ? (analytics.severity_distribution.Safe || 0) + (analytics.severity_distribution.Low || 0)
              : safeCount}
          </span>
        </div>
        {analytics && (
          <>
            <div className="stat-card glass-panel hover-lift">
              <span className="stat-title">Total Findings</span>
              <span className="stat-value" style={{ color: 'var(--accent-secondary)' }}>{analytics.total_findings}</span>
            </div>
            <div className="stat-card glass-panel hover-lift">
              <span className="stat-title">High Confidence</span>
              <span className="stat-value" style={{ color: 'var(--accent-primary)' }}>{analytics.high_confidence_count || 0}</span>
            </div>
          </>
        )}
      </div>

      {/* ── AI Insights Panel ─────────────────────────────────────────────── */}
      <div className="glass-panel" style={{ marginBottom: 'var(--spacing-lg)', overflow: 'hidden' }}>
        <div
          style={{
            padding: '0.875rem 1.25rem',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            borderBottom: insightsExpanded ? '1px solid var(--border-color)' : 'none',
            cursor: 'pointer',
          }}
          onClick={() => setInsightsExpanded((e) => !e)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: 'var(--accent-primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Sparkles size={16} color="white" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>AI Analytics Insights</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
                LLM-powered explanation of your data
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {!insights && !insightsLoading && (
              <button
                className="btn btn-primary"
                style={{ padding: '0.4rem 1rem', fontSize: '0.82rem' }}
                onClick={(e) => { e.stopPropagation(); fetchInsights(); setInsightsExpanded(true); }}
              >
                <Sparkles size={14} /> Generate Insights
              </button>
            )}
            {insights && !insightsLoading && (
              <button
                className="btn btn-secondary"
                style={{ padding: '0.3rem 0.7rem', fontSize: '0.75rem' }}
                onClick={(e) => { e.stopPropagation(); fetchInsights(); }}
                title="Regenerate insights"
              >
                <RefreshCw size={12} /> Refresh
              </button>
            )}
            {insightsExpanded ? <ChevronUp size={18} style={{ color: 'var(--text-tertiary)' }} /> : <ChevronDown size={18} style={{ color: 'var(--text-tertiary)' }} />}
          </div>
        </div>

        {insightsExpanded && (
          <div style={{ padding: '1.25rem' }}>
            {insightsLoading && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', padding: '2rem' }}>
                <Loader2 size={28} style={{ color: 'var(--accent-primary)', animation: 'spin 1.5s linear infinite' }} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.3rem' }}>Generating insights...</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>Analyzing your data — this may take 10-30 seconds</div>
                </div>
              </div>
            )}

            {!insightsLoading && !insights && (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-tertiary)' }}>
                <Sparkles size={32} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
                <p style={{ fontSize: '0.9rem' }}>Click &quot;Generate Insights&quot; to get an AI-powered explanation of your analytics data.</p>
              </div>
            )}

            {!insightsLoading && insights && (
              <div style={{ fontSize: '0.9rem', lineHeight: 1.75, color: 'var(--text-secondary)' }}>
                {insights.split('\n').map((line, i) => {
                  if (line.startsWith('## ')) {
                    return <h3 key={i} style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: i > 0 ? '1.25rem' : 0, marginBottom: '0.5rem' }}>{line.slice(3)}</h3>;
                  }
                  if (line.startsWith('**') && line.endsWith('**')) {
                    return <p key={i} style={{ fontWeight: 600, color: 'var(--text-primary)', marginTop: '0.75rem' }}>{line.slice(2, -2)}</p>;
                  }
                  if (line.startsWith('- ') || line.startsWith('• ')) {
                    const text = line.slice(2);
                    const parts = text.split(/(\*\*[^*]+\*\*)/);
                    return (
                      <div key={i} style={{ display: 'flex', gap: '0.5rem', marginLeft: '0.5rem', marginBottom: '0.3rem' }}>
                        <span style={{ color: 'var(--accent-primary)', flexShrink: 0 }}>•</span>
                        <span>
                          {parts.map((part, j) =>
                            part.startsWith('**') && part.endsWith('**')
                              ? <strong key={j} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
                              : part
                          )}
                        </span>
                      </div>
                    );
                  }
                  if (line.trim() === '') return <div key={i} style={{ height: '0.5rem' }} />;
                  const parts = line.split(/(\*\*[^*]+\*\*)/);
                  return (
                    <p key={i} style={{ marginBottom: '0.3rem' }}>
                      {parts.map((part, j) =>
                        part.startsWith('**') && part.endsWith('**')
                          ? <strong key={j} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
                          : part
                      )}
                    </p>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Chart Visibility Toggles */}
      <div className="glass-panel" style={{ padding: '0.75rem 1.25rem', marginBottom: 'var(--spacing-lg)', display: 'flex', flexWrap: 'wrap', gap: '0.4rem', alignItems: 'center' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginRight: '0.5rem' }}>Show:</span>
        {CHART_LIST.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => toggleChart(id)}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.25rem',
              padding: '0.2rem 0.55rem', fontSize: '0.72rem', fontWeight: 500,
              background: isVisible(id) ? 'var(--accent-soft)' : 'rgba(0,0,0,0.02)',
              border: `1px solid ${isVisible(id) ? 'var(--accent-soft-border)' : 'var(--border-color)'}`,
              borderRadius: 'var(--radius-full)',
              color: isVisible(id) ? 'var(--accent-primary)' : 'var(--text-tertiary)',
              cursor: 'pointer', transition: 'all 0.2s',
            }}
          >
            {isVisible(id) ? <Eye size={10} /> : <EyeOff size={10} />}
            {label}
          </button>
        ))}
      </div>

      {/* Charts Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 'var(--spacing-lg)' }}>

        {/* Severity Distribution (FIXED — actual counts) */}
        {severityBarData.length > 0 && isVisible('severity') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <ShieldAlert size={16} style={{ color: 'var(--status-high)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Severity Distribution</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={severityBarData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <XAxis dataKey="severity" stroke="var(--text-tertiary)" fontSize={11} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Reports">
                    {severityBarData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Risk Score Histogram */}
        {riskHistData.length > 0 && isVisible('risk-hist') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <BarChart2 size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Risk Score Distribution</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={riskHistData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <XAxis dataKey="range" stroke="var(--text-tertiary)" fontSize={11} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Reports">
                    {riskHistData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Top Categories */}
        {topCatData.length > 0 && isVisible('top-cats') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <TrendingUp size={16} style={{ color: 'var(--accent-secondary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Top Risk Categories</h3>
            </div>
            <div style={{ height: Math.max(260, topCatData.length * 38 + 40) }}>
              <ResponsiveContainer>
                <BarChart data={topCatData} layout="vertical" margin={{ top: 5, right: 30, left: 10, bottom: 5 }} barSize={22}>
                  <XAxis type="number" stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <YAxis dataKey="name" type="category" width={130} stroke="var(--text-secondary)" fontSize={11} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Occurrences">
                    {topCatData.map((_, i) => <Cell key={i} fill={i < 2 ? 'var(--status-critical)' : i < 4 ? 'var(--status-high)' : 'var(--status-moderate)'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Detection Confidence */}
        {confHistData.some(d => d.count > 0) && isVisible('confidence') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <Brain size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Detection Confidence</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={confHistData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <XAxis dataKey="range" stroke="var(--text-tertiary)" fontSize={11} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Reports">
                    {confHistData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Risk Score Trend */}
        {trendData.length > 1 && isVisible('trend') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <TrendingUp size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Risk Score Trend</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={trendData} margin={{ top: 8, right: 16, left: -10, bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--text-tertiary)" fontSize={10} angle={-35} textAnchor="end" interval={0} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} domain={[0, 100]} />
                  <Tooltip content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const score = payload[0].value;
                    return (<div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)', boxShadow: 'var(--shadow-md)' }}><div style={{ fontWeight: 600 }}>{label}</div><div style={{ color: getRiskColor(score) }}>Score: <strong>{score}</strong></div></div>);
                  }} />
                  <ReferenceLine y={80} stroke="var(--status-critical)" strokeDasharray="4 3" strokeOpacity={0.4} />
                  <ReferenceLine y={40} stroke="var(--status-moderate)" strokeDasharray="4 3" strokeOpacity={0.3} />
                  <Line type="monotone" dataKey="score" stroke="var(--accent-primary)" strokeWidth={2.5} dot={(props) => <circle key={props.key} cx={props.cx} cy={props.cy} r={5} fill={getRiskColor(props.payload.score)} stroke="var(--bg-secondary)" strokeWidth={1.5} />} activeDot={{ r: 7 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ML Agreement (Donut) */}
        {mlAgreementData.length > 0 && isVisible('ml-agreement') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <Brain size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>ML vs Regex Agreement</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={mlAgreementData} cx="50%" cy="50%" innerRadius={55} outerRadius={95} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                    <Cell fill="var(--status-safe)" />
                    <Cell fill="var(--status-high)" />
                    {mlAgreementData.length > 2 && <Cell fill="var(--text-tertiary)" />}
                  </Pie>
                  <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {analytics?.ml_agreement_totals?.rate != null && (
              <div style={{ textAlign: 'center', fontSize: '0.82rem', color: 'var(--text-tertiary)', marginTop: '0.5rem' }}>
                Agreement rate: <strong style={{ color: 'var(--status-safe)' }}>{(analytics.ml_agreement_totals.rate * 100).toFixed(1)}%</strong>
              </div>
            )}
          </div>
        )}

        {/* NEW: ML Calibration Bar Chart */}
        {mlCalibrationData.length > 0 && isVisible('ml-calibration') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <Brain size={16} style={{ color: 'var(--status-moderate)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>ML Calibration</h3>
              <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>Findings with ML signal</span>
            </div>
            <div style={{ height: Math.max(180, mlCalibrationData.length * 60 + 40) }}>
              <ResponsiveContainer>
                <BarChart data={mlCalibrationData} layout="vertical" margin={{ top: 10, right: 30, left: 10, bottom: 10 }} barSize={28}>
                  <XAxis type="number" stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <YAxis dataKey="label" type="category" width={140} stroke="var(--text-secondary)" fontSize={11} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} name="Findings">
                    {mlCalibrationData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {analytics?.ml_agreement_totals?.rate != null && (
              <div style={{ textAlign: 'center', fontSize: '0.82rem', color: 'var(--text-tertiary)', marginTop: '0.5rem' }}>
                Agreement rate: <strong style={{ color: 'var(--status-safe)' }}>{(analytics.ml_agreement_totals.rate * 100).toFixed(1)}%</strong>
              </div>
            )}
          </div>
        )}

        {/* Analysis Volume */}
        {volumeData.length > 1 && isVisible('volume') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <FileAudio size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Analysis Volume</h3>
              <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>Last 14 days</span>
            </div>
            <div style={{ height: 240 }}>
              <ResponsiveContainer>
                <AreaChart data={volumeData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <defs>
                    <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--text-tertiary)" fontSize={10} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="count" stroke="var(--accent-primary)" strokeWidth={2} fill="url(#volGrad)" name="Analyses" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Avg Risk by Day */}
        {avgRiskByDay.length > 1 && isVisible('avg-risk-day') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <TrendingUp size={16} style={{ color: 'var(--status-moderate)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Avg Risk by Day</h3>
              <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>Last 14 days</span>
            </div>
            <div style={{ height: 240 }}>
              <ResponsiveContainer>
                <LineChart data={avgRiskByDay} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--text-tertiary)" fontSize={10} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} domain={[0, 100]} />
                  <ReferenceLine y={80} stroke="var(--status-critical)" strokeDasharray="4 3" strokeOpacity={0.4} />
                  <ReferenceLine y={40} stroke="var(--status-moderate)" strokeDasharray="4 3" strokeOpacity={0.3} />
                  <Tooltip content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const val = payload[0].value;
                    return (<div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)', boxShadow: 'var(--shadow-md)' }}><div style={{ fontWeight: 600 }}>{label}</div><div style={{ color: getRiskColor(val) }}>Avg: <strong>{val}</strong></div></div>);
                  }} />
                  <Line type="monotone" dataKey="avg" stroke="var(--status-moderate)" strokeWidth={2.5} dot={{ r: 4, fill: 'var(--status-moderate)', stroke: 'var(--bg-secondary)', strokeWidth: 1.5 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* NEW: Risk by Day of Week */}
        {riskByDayOfWeek.length > 0 && isVisible('risk-heatmap') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <Calendar size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Risk by Weekday</h3>
              <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>Avg risk per day of week</span>
            </div>
            <div style={{ height: 240 }}>
              <ResponsiveContainer>
                <BarChart data={riskByDayOfWeek} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <XAxis dataKey="day" stroke="var(--text-tertiary)" fontSize={11} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} domain={[0, 100]} />
                  <Tooltip content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (<div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)', boxShadow: 'var(--shadow-md)' }}><div style={{ fontWeight: 600 }}>{label}</div><div style={{ color: getRiskColor(d.avgRisk) }}>Avg Risk: <strong>{d.avgRisk}</strong></div><div style={{ color: 'var(--text-secondary)' }}>Analyses: {d.analyses}</div></div>);
                  }} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="avgRisk" radius={[4, 4, 0, 0]} name="Avg Risk">
                    {riskByDayOfWeek.map((entry, i) => <Cell key={i} fill={getRiskColor(entry.avgRisk)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Severity Trend */}
        {severityTrendData.length > 2 && isVisible('severity-trend') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <ShieldAlert size={16} style={{ color: 'var(--status-critical)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Severity Trend</h3>
              <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>Grouped by 5</span>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <AreaChart data={severityTrendData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="label" stroke="var(--text-tertiary)" fontSize={10} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8 }} />
                  <Area type="monotone" dataKey="Critical" stackId="1" stroke="var(--status-critical)" fill="var(--status-critical)" fillOpacity={0.6} />
                  <Area type="monotone" dataKey="High" stackId="1" stroke="var(--status-high)" fill="var(--status-high)" fillOpacity={0.5} />
                  <Area type="monotone" dataKey="Moderate" stackId="1" stroke="var(--status-moderate)" fill="var(--status-moderate)" fillOpacity={0.4} />
                  <Area type="monotone" dataKey="Low" stackId="1" stroke="var(--status-low)" fill="var(--status-low)" fillOpacity={0.3} />
                  <Area type="monotone" dataKey="Safe" stackId="1" stroke="var(--status-safe)" fill="var(--status-safe)" fillOpacity={0.3} />
                  <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
