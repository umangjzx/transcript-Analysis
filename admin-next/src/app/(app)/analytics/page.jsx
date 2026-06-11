'use client';

/**
 * Analytics — Dedicated page for all charts and visualizations.
 * Ported from React Router version to Next.js App Router.
 */

import React, { useCallback, useEffect, useMemo, useState, memo } from 'react';
import { useRouter } from 'next/navigation';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend, LineChart, Line, CartesianGrid,
  ScatterChart, Scatter, ZAxis, ReferenceLine,
  AreaChart, Area, RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from 'recharts';
import {
  ShieldAlert, Activity, FileAudio, TrendingUp,
  CheckCircle, BarChart2, Brain, RefreshCw, ArrowLeft,
  Eye, EyeOff, Sparkles, Loader2, ChevronDown, ChevronUp,
} from 'lucide-react';
import { getAnalyticsInsights } from '@/lib/api';
import { useDataStore, useDataStoreStats } from '@/store/dataStore';
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
const CTX_COLORS = [
  'var(--status-critical)', 'var(--accent-primary)',
  'var(--status-safe)', 'var(--text-tertiary)', 'var(--status-moderate)',
];

const SEV_ORDER = ['Critical', 'High', 'Moderate', 'Low', 'Safe', 'Unknown'];

const ChartTooltip = memo(({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
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

  // Use global DataStore — no independent fetching needed
  const { history, analytics, loading, refreshing, refresh } = useDataStore();

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

  const statusStackData = useMemo(() => {
    if (!analytics) return [];
    const sevDist = analytics.severity_distribution || {};
    const statusDist = analytics.status_distribution || {};
    const grandTotal = Object.values(statusDist).reduce((a, b) => a + b, 0) || 1;
    return SEV_ORDER
      .filter(sev => (sevDist?.[sev] || 0) > 0)
      .map(sev => {
        const total = sevDist?.[sev] || 0;
        return {
          severity: sev,
          Completed: Math.round(total * ((statusDist.COMPLETED || 0) / grandTotal)),
          Processing: Math.round(total * ((statusDist.PROCESSING || 0) / grandTotal)),
          Failed: Math.round(total * ((statusDist.FAILED || 0) / grandTotal)),
          _total: total,
        };
      });
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

  const timelineScatterData = useMemo(() => (
    [...history]
      .filter(h => h.created_at && h.risk_score != null)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
      .slice(-20)
      .map((h, i) => ({
        x: i + 1, y: Math.round(h.risk_score), z: 1,
        label: h.filename ? h.filename.slice(0, 14) + (h.filename.length > 14 ? '…' : '') : `#${h.id}`,
        severity: (h.severity || 'safe').toLowerCase(),
      }))
  ), [history]);

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

  const contextRadarData = useMemo(() => {
    if (!analytics?.context_type_totals) return [];
    return Object.entries(analytics.context_type_totals)
      .map(([name, value]) => ({ subject: capitalize(name).split(' ')[0], count: value }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
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

  const statusDonutData = useMemo(() => {
    if (!analytics?.status_distribution) return [];
    return Object.entries(analytics.status_distribution)
      .map(([name, value]) => ({ name: capitalize(name), value }))
      .filter(d => d.value > 0);
  }, [analytics]);

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
    { id: 'scatter', label: 'Risk Scatter' },
    { id: 'confidence', label: 'Confidence' },
    { id: 'trend', label: 'Risk Trend' },
    { id: 'ml-agreement', label: 'ML Agreement' },
    { id: 'context-radar', label: 'Context Radar' },
    { id: 'volume', label: 'Volume' },
    { id: 'avg-risk-day', label: 'Avg Risk/Day' },
    { id: 'status-donut', label: 'Status' },
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
          <span className="stat-value text-gradient">{history.length}</span>
        </div>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">High / Critical</span>
          <span className="stat-value" style={{ color: 'var(--status-high)' }}>{highRisk}</span>
        </div>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">Avg Risk Score</span>
          <span className="stat-value" style={{ color: getRiskColor(analytics?.avg_risk_score ?? avgScore) }}>{(analytics?.avg_risk_score ?? avgScore).toFixed(1)}</span>
        </div>
        <div className="stat-card glass-panel hover-lift">
          <span className="stat-title">Safe / Low</span>
          <span className="stat-value" style={{ color: 'var(--status-safe)' }}>{safeCount}</span>
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
        {/* Header */}
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
              background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Sparkles size={16} color="white" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>AI Analytics Insights</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
                LLM-powered explanation of your data • Powered by Mistral
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

        {/* Body */}
        {insightsExpanded && (
          <div style={{ padding: '1.25rem' }}>
            {insightsLoading && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', padding: '2rem' }}>
                <Loader2 size={28} style={{ color: 'var(--accent-primary)', animation: 'spin 1.5s linear infinite' }} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.3rem' }}>Generating insights...</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>Analyzing your data with Mistral LLM — this may take 10-30 seconds</div>
                </div>
              </div>
            )}

            {!insightsLoading && !insights && (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-tertiary)' }}>
                <Sparkles size={32} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
                <p style={{ fontSize: '0.9rem' }}>Click &quot;Generate Insights&quot; to get an AI-powered explanation of your analytics data.</p>
                <p style={{ fontSize: '0.78rem', marginTop: '0.5rem' }}>The LLM will analyze all charts and metrics to provide actionable summaries.</p>
              </div>
            )}

            {!insightsLoading && insights && (
              <div className="insights-content" style={{ fontSize: '0.9rem', lineHeight: 1.75, color: 'var(--text-secondary)' }}>
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
                  if (line.startsWith('*') && line.endsWith('*') && !line.startsWith('**')) {
                    return <p key={i} style={{ fontStyle: 'italic', color: 'var(--text-tertiary)', fontSize: '0.82rem', marginTop: '0.5rem' }}>{line.slice(1, -1)}</p>;
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
              background: isVisible(id) ? 'rgba(56,189,248,0.08)' : 'rgba(0,0,0,0.02)',
              border: `1px solid ${isVisible(id) ? 'rgba(56,189,248,0.2)' : 'var(--border-color)'}`,
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

        {/* Severity Distribution */}
        {statusStackData.length > 0 && isVisible('severity') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <ShieldAlert size={16} style={{ color: 'var(--status-high)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Severity Distribution</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={statusStackData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <XAxis dataKey="severity" stroke="var(--text-tertiary)" fontSize={11} />
                  <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                  <Bar dataKey="Completed" stackId="a" fill="var(--status-safe)" />
                  <Bar dataKey="Processing" stackId="a" fill="var(--status-moderate)" />
                  <Bar dataKey="Failed" stackId="a" fill="var(--status-high)" radius={[4, 4, 0, 0]} />
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
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={topCatData} layout="vertical" margin={{ top: 5, right: 30, left: 100, bottom: 5 }}>
                  <XAxis type="number" stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                  <YAxis dataKey="name" type="category" width={95} stroke="var(--text-secondary)" fontSize={11} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,23,42,0.04)' }} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Occurrences">
                    {topCatData.map((_, i) => <Cell key={i} fill={i < 2 ? 'var(--status-critical)' : i < 4 ? 'var(--status-high)' : 'var(--status-moderate)'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Risk Score Scatter */}
        {timelineScatterData.length > 1 && isVisible('scatter') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <Activity size={16} style={{ color: 'var(--accent-primary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Risk Score Scatter</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 8, right: 16, left: -10, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="x" type="number" stroke="var(--text-tertiary)" fontSize={11} domain={[1, timelineScatterData.length]} label={{ value: 'Analysis #', position: 'insideBottom', offset: -2, fill: 'var(--text-tertiary)', fontSize: 10 }} />
                  <YAxis dataKey="y" type="number" stroke="var(--text-tertiary)" fontSize={11} domain={[0, 100]} />
                  <ZAxis dataKey="z" range={[60, 60]} />
                  <ReferenceLine y={80} stroke="var(--status-critical)" strokeDasharray="4 3" strokeOpacity={0.5} />
                  <ReferenceLine y={41} stroke="var(--status-moderate)" strokeDasharray="4 3" strokeOpacity={0.35} />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (<div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}><div style={{ fontWeight: 600 }}>{d.label}</div><div style={{ color: getRiskColor(d.y) }}>Score: <strong>{d.y}</strong></div></div>);
                  }} />
                  <Scatter data={timelineScatterData} shape={(props) => { const { cx, cy, payload } = props; return <circle cx={cx} cy={cy} r={7} fill={getRiskColor(payload.y)} stroke="#fff" strokeWidth={1.5} fillOpacity={0.85} />; }} />
                </ScatterChart>
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
                    return (<div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}><div style={{ fontWeight: 600 }}>{label}</div><div style={{ color: getRiskColor(score) }}>Score: <strong>{score}</strong></div></div>);
                  }} />
                  <Line type="monotone" dataKey="score" stroke="var(--accent-primary)" strokeWidth={2.5} dot={(props) => <circle key={props.key} cx={props.cx} cy={props.cy} r={5} fill={getRiskColor(props.payload.score)} stroke="#fff" strokeWidth={1.5} />} activeDot={{ r: 7 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ML Agreement */}
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
                  <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {analytics?.ml_agreement_totals?.rate != null && (
              <div style={{ textAlign: 'center', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                Agreement rate: <strong style={{ color: 'var(--status-safe)' }}>{(analytics.ml_agreement_totals.rate * 100).toFixed(1)}%</strong>
              </div>
            )}
          </div>
        )}

        {/* Context Type Radar */}
        {contextRadarData.length > 2 && isVisible('context-radar') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <Activity size={16} style={{ color: 'var(--accent-secondary)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Context Type Radar</h3>
            </div>
            <div style={{ height: 280 }}>
              <ResponsiveContainer>
                <RadarChart data={contextRadarData}>
                  <PolarGrid stroke="var(--border-color)" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                  <Radar name="Findings" dataKey="count" stroke="var(--accent-primary)" fill="var(--accent-primary)" fillOpacity={0.25} strokeWidth={2} />
                  <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8 }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
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
                      <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.3} />
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
                    return (<div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.5rem 0.9rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}><div style={{ fontWeight: 600 }}>{label}</div><div style={{ color: getRiskColor(val) }}>Avg: <strong>{val}</strong></div></div>);
                  }} />
                  <Line type="monotone" dataKey="avg" stroke="var(--status-moderate)" strokeWidth={2.5} dot={{ r: 4, fill: 'var(--status-moderate)', stroke: '#fff', strokeWidth: 1.5 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Status Donut */}
        {statusDonutData.length > 0 && isVisible('status-donut') && (
          <div className="glass-panel" style={{ padding: 'var(--spacing-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 'var(--spacing-md)' }}>
              <CheckCircle size={16} style={{ color: 'var(--status-safe)' }} />
              <h3 className="heading-3" style={{ margin: 0 }}>Processing Status</h3>
            </div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={statusDonutData} cx="50%" cy="50%" innerRadius={55} outerRadius={95} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                    {statusDonutData.map((entry, i) => {
                      const colors = { Completed: 'var(--status-safe)', Processing: 'var(--status-moderate)', Failed: 'var(--status-high)' };
                      return <Cell key={i} fill={colors[entry.name] || CTX_COLORS[i % CTX_COLORS.length]} />;
                    })}
                  </Pie>
                  <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
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
                  <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 8 }} />
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
