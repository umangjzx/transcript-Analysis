/**
 * Compare — Side-by-side report comparison view.
 *
 * URL: /compare?ids=1,2
 * Allows selecting 2 reports and comparing risk scores, findings, categories.
 */

import React, { useEffect, useState, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, GitCompare, AlertTriangle, CheckCircle,
  TrendingUp, TrendingDown, Minus, BarChart2, ShieldAlert,
} from 'lucide-react';
import { getReport, getHistory } from '../api';

const capitalize = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

const getScoreColor = (score) => {
  if (score >= 80) return 'var(--status-critical)';
  if (score >= 61) return 'var(--status-high)';
  if (score >= 41) return 'var(--status-moderate)';
  if (score >= 21) return 'var(--status-low)';
  return 'var(--status-safe)';
};

const getBadgeClass = (severity) => {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return 'badge-critical';
  if (s === 'high') return 'badge-high';
  if (s === 'moderate' || s === 'medium') return 'badge-moderate';
  if (s === 'low') return 'badge-low';
  return 'badge-safe';
};

const DiffIndicator = ({ a, b, label, format = 'number' }) => {
  const diff = (b || 0) - (a || 0);
  const color = diff > 0 ? 'var(--status-high)' : diff < 0 ? 'var(--status-safe)' : 'var(--text-tertiary)';
  const Icon = diff > 0 ? TrendingUp : diff < 0 ? TrendingDown : Minus;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color }}>
      <Icon size={14} />
      <span>{diff > 0 ? '+' : ''}{format === 'percent' ? `${(diff * 100).toFixed(1)}%` : diff.toFixed(1)}</span>
      <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
    </div>
  );
};

const Compare = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const ids = (searchParams.get('ids') || '').split(',').filter(Boolean).map(Number);

  const [reports, setReports] = useState([null, null]);
  const [loading, setLoading] = useState(true);
  const [allReports, setAllReports] = useState([]);
  const [selectedIds, setSelectedIds] = useState(ids.length >= 2 ? ids.slice(0, 2) : [null, null]);

  // Load report list for selector
  useEffect(() => {
    getHistory(0, 100).then((data) => {
      setAllReports(Array.isArray(data) ? data : data?.reports || []);
    }).catch(() => {});
  }, []);

  // Load selected reports
  useEffect(() => {
    const [id1, id2] = selectedIds;
    if (!id1 || !id2) { setLoading(false); return; }

    setLoading(true);
    Promise.all([getReport(id1), getReport(id2)])
      .then(([r1, r2]) => setReports([r1, r2]))
      .catch(() => setReports([null, null]))
      .finally(() => setLoading(false));
  }, [selectedIds]);

  const handleSelect = (index, id) => {
    const newIds = [...selectedIds];
    newIds[index] = id ? Number(id) : null;
    setSelectedIds(newIds);
    if (newIds[0] && newIds[1]) {
      navigate(`/compare?ids=${newIds[0]},${newIds[1]}`, { replace: true });
    }
  };

  const [reportA, reportB] = reports;

  // Category comparison
  const categoryComparison = useMemo(() => {
    if (!reportA || !reportB) return [];
    const statsA = reportA.stats || {};
    const statsB = reportB.stats || {};
    const catsA = statsA.categories || statsA.category_breakdown || {};
    const catsB = statsB.categories || statsB.category_breakdown || {};
    const allCats = new Set([...Object.keys(catsA), ...Object.keys(catsB)]);
    return [...allCats].map((cat) => ({
      name: capitalize(cat),
      a: catsA[cat] || 0,
      b: catsB[cat] || 0,
    })).sort((x, y) => Math.max(y.a, y.b) - Math.max(x.a, x.b));
  }, [reportA, reportB]);

  return (
    <div className="animate-fade-in" style={{ maxWidth: 1400, margin: '0 auto', padding: 'var(--spacing-xl)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: 'var(--spacing-xl)' }}>
        <button className="btn btn-icon" onClick={() => navigate('/')} title="Back to Dashboard">
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="heading-1 page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <GitCompare size={28} style={{ color: 'var(--accent-primary)' }} />
            Compare Reports
          </h1>
          <p className="page-subtitle">Select two reports to compare side-by-side</p>
        </div>
      </div>

      {/* Selectors */}
      <div className="glass-panel" style={{ padding: 'var(--spacing-lg)', marginBottom: 'var(--spacing-xl)', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {[0, 1].map((idx) => (
          <div key={idx} style={{ flex: 1, minWidth: 200 }}>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginBottom: '0.3rem', display: 'block' }}>
              Report {idx === 0 ? 'A' : 'B'}
            </label>
            <select
              value={selectedIds[idx] || ''}
              onChange={(e) => handleSelect(idx, e.target.value)}
              style={{
                width: '100%', padding: '0.6rem 0.9rem',
                background: 'rgba(0,0,0,0.02)', border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)', color: 'var(--text-primary)',
                fontSize: '0.9rem', outline: 'none', cursor: 'pointer',
              }}
            >
              <option value="">Select a report...</option>
              {allReports.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} — {r.filename} ({r.severity}, Score: {r.risk_score?.toFixed(0)})
                </option>
              ))}
            </select>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', color: 'var(--text-tertiary)', fontSize: '1.5rem', fontWeight: 700, padding: '0 0.5rem' }}>
          vs
        </div>
      </div>

      {/* Loading */}
      {loading && selectedIds[0] && selectedIds[1] && (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
          <div className="loading-spinner" style={{ margin: '0 auto 1rem' }} />
          <p style={{ color: 'var(--text-secondary)' }}>Loading reports...</p>
        </div>
      )}

      {/* Comparison */}
      {!loading && reportA && reportB && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-lg)' }}>

          {/* Score comparison */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 'var(--spacing-lg)' }}>
            {[reportA, reportB].map((report, idx) => (
              <div key={idx} className="glass-panel hover-lift" style={{ padding: 'var(--spacing-xl)', textAlign: 'center' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginBottom: '0.5rem' }}>
                  Report {idx === 0 ? 'A' : 'B'} — #{report.id}
                </p>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {report.filename}
                </h3>
                <div style={{ fontSize: '3rem', fontWeight: 800, color: getScoreColor(report.risk_score || 0), lineHeight: 1 }}>
                  {(report.risk_score || 0).toFixed(0)}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: '0.25rem' }}>Risk Score</div>
                <span className={`badge ${getBadgeClass(report.severity)}`} style={{ marginTop: '0.75rem' }}>
                  {report.severity}
                </span>
              </div>
            ))}

            {/* Diff column */}
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '0.75rem', padding: '1rem' }}>
              <DiffIndicator a={reportA.risk_score} b={reportB.risk_score} label="score" />
              <DiffIndicator a={(reportA.findings || []).length} b={(reportB.findings || []).length} label="findings" />
              <DiffIndicator a={(reportA.evidence || []).length} b={(reportB.evidence || []).length} label="evidence" />
            </div>
          </div>

          {/* Stats comparison table */}
          <div className="glass-panel" style={{ padding: 'var(--spacing-xl)' }}>
            <h3 className="heading-3" style={{ marginBottom: 'var(--spacing-md)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <BarChart2 size={18} style={{ color: 'var(--accent-primary)' }} />
              Metrics Comparison
            </h3>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '0.6rem', color: 'var(--text-tertiary)', fontSize: '0.8rem', borderBottom: '1px solid var(--border-color)' }}>Metric</th>
                  <th style={{ textAlign: 'center', padding: '0.6rem', color: 'var(--accent-primary)', fontSize: '0.8rem', borderBottom: '1px solid var(--border-color)' }}>Report A</th>
                  <th style={{ textAlign: 'center', padding: '0.6rem', color: 'var(--accent-secondary)', fontSize: '0.8rem', borderBottom: '1px solid var(--border-color)' }}>Report B</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { label: 'Risk Score', a: reportA.risk_score?.toFixed(1), b: reportB.risk_score?.toFixed(1) },
                  { label: 'Severity', a: reportA.severity, b: reportB.severity },
                  { label: 'Total Findings', a: (reportA.findings || []).length, b: (reportB.findings || []).length },
                  { label: 'Evidence Items', a: (reportA.evidence || []).length, b: (reportB.evidence || []).length },
                  { label: 'Words Analyzed', a: reportA.stats?.word_count || '—', b: reportB.stats?.word_count || '—' },
                  { label: 'Timeline Segments', a: (reportA.timeline || []).length, b: (reportB.timeline || []).length },
                ].map((row, i) => (
                  <tr key={i}>
                    <td style={{ padding: '0.6rem', fontSize: '0.9rem', fontWeight: 500 }}>{row.label}</td>
                    <td style={{ padding: '0.6rem', textAlign: 'center', fontSize: '0.9rem', color: 'var(--accent-primary)' }}>{row.a}</td>
                    <td style={{ padding: '0.6rem', textAlign: 'center', fontSize: '0.9rem', color: 'var(--accent-secondary)' }}>{row.b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Category comparison */}
          {categoryComparison.length > 0 && (
            <div className="glass-panel" style={{ padding: 'var(--spacing-xl)' }}>
              <h3 className="heading-3" style={{ marginBottom: 'var(--spacing-md)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <ShieldAlert size={18} style={{ color: 'var(--accent-secondary)' }} />
                Category Breakdown
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {categoryComparison.slice(0, 10).map((cat) => {
                  const max = Math.max(cat.a, cat.b, 1);
                  return (
                    <div key={cat.name} style={{ display: 'grid', gridTemplateColumns: '140px 1fr 40px 1fr 40px', gap: '0.5rem', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.82rem', fontWeight: 500, textAlign: 'right' }}>{cat.name}</span>
                      <div style={{ height: 8, background: 'rgba(0,0,0,0.05)', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${(cat.a / max) * 100}%`, background: 'var(--accent-primary)', borderRadius: 4 }} />
                      </div>
                      <span style={{ fontSize: '0.78rem', color: 'var(--accent-primary)', textAlign: 'center', fontWeight: 600 }}>{cat.a}</span>
                      <div style={{ height: 8, background: 'rgba(0,0,0,0.05)', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${(cat.b / max) * 100}%`, background: 'var(--accent-secondary)', borderRadius: 4 }} />
                      </div>
                      <span style={{ fontSize: '0.78rem', color: 'var(--accent-secondary)', textAlign: 'center', fontWeight: 600 }}>{cat.b}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && (!selectedIds[0] || !selectedIds[1]) && (
        <div className="glass-panel" style={{ padding: '4rem', textAlign: 'center' }}>
          <GitCompare size={48} style={{ color: 'var(--text-tertiary)', margin: '0 auto 1rem' }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem' }}>
            Select two reports above to compare them side-by-side
          </p>
        </div>
      )}
    </div>
  );
};

export default Compare;
