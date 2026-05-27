import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useParams, useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  RadarChart, PolarGrid, PolarAngleAxis, Radar, PieChart, Pie, Legend,
  ScatterChart, Scatter, ZAxis, LineChart, Line, CartesianGrid,
} from 'recharts';
import {
  Download, AlertTriangle, FileText, Activity, ShieldAlert,
  Brain, Clock, ChevronDown, ChevronUp, Code, MessageSquare,
  ArrowLeft, Zap, Eye, TrendingUp, Database, BarChart2, Info, CheckCircle, XCircle,
  Users, Mail, Bell, Trash2, X,
} from 'lucide-react';
import { getReport, downloadPdfUrl, sendAlertEmail, sendSummaryEmail, deleteReport } from '../api';
import Chatbot from '../components/Chatbot';

// ─── Helpers ────────────────────────────────────────────────────────────────
const getSeverityColor = (severity) => {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return 'var(--status-critical)';
  if (s === 'high')     return 'var(--status-high)';
  if (s === 'moderate' || s === 'medium') return 'var(--status-moderate)';
  if (s === 'low')      return 'var(--status-low)';
  return 'var(--status-safe)';
};

const getScoreColor = (score) => {
  if (score >= 80) return 'var(--status-critical)';
  if (score >= 61) return 'var(--status-high)';
  if (score >= 41) return 'var(--status-moderate)';
  if (score >= 21) return 'var(--status-low)';
  return 'var(--status-safe)';
};

const fmtPct = (v) => `${((v || 0) * 100).toFixed(1)}%`;
const fmtScore = (v) => (v != null ? (v * 100).toFixed(0) : '—');
const capitalize = (s) => (s || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

// ─── Skeleton loader ────────────────────────────────────────────────────────

const SkeletonBlock = ({ height = 80, style = {} }) => (
  <div
    style={{
      height,
      borderRadius: 'var(--radius-md)',
      background: 'linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.4s infinite',
      ...style,
    }}
  />
);

const FindingsSkeleton = () => (
  <div className="findings-debug-list" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
    {[100, 80, 90, 70, 85].map((h, i) => (
      <SkeletonBlock key={i} height={h} />
    ))}
    <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
  </div>
);

const EvidenceSkeleton = () => (
  <div className="evidence-list" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
    {[110, 90, 100, 80].map((h, i) => (
      <SkeletonBlock key={i} height={h} />
    ))}
  </div>
);

// ─── Sub-components ─────────────────────────────────────────────────────────

const TabButton = ({ active, onClick, icon: Icon, label, count }) => (
  <button
    className={`report-tab-btn ${active ? 'active' : ''}`}
    onClick={onClick}
  >
    <Icon size={15} />
    <span>{label}</span>
    {count != null && <span className="tab-badge">{count}</span>}
  </button>
);

const StatPill = ({ label, value, color }) => (
  <div className="stat-pill">
    <span className="stat-pill-label">{label}</span>
    <span className="stat-pill-value" style={{ color }}>{value}</span>
  </div>
);

const ConfidenceBar = ({ value, color }) => (
  <div className="conf-bar-track">
    <div
      className="conf-bar-fill"
      style={{ width: `${Math.min((value || 0) * 100, 100)}%`, background: color || 'var(--accent-primary)' }}
    />
    <span className="conf-bar-label">{fmtPct(value)}</span>
  </div>
);

const FindingCard = ({ finding, index }) => {
  const [expanded, setExpanded] = useState(false);
  const conf = finding.confidence || finding.max_confidence || 0;
  const color = getScoreColor(conf * 100);

  // Backend stores the sentence as "evidence"; support legacy "text" too
  const evidenceText = finding.evidence || finding.text || '';

  // ML result is stored under "ml" key in the backend
  const mlResult = finding.ml || finding.ml_result || {};

  // Scoring breakdown is nested under "scoring"
  const scoring = finding.scoring || {};
  const baseConf = scoring.base_confidence ?? finding.base_confidence;
  const ctxMultiplier = scoring.context_multiplier ?? finding.context_multiplier;
  const mlFusedConf = scoring.ml_fused_confidence;

  // Filter flags are nested under "filters"
  const filters = finding.filters || {};
  const isJoke = filters.is_joke ?? finding.is_joke ?? false;
  const isNegation = filters.is_negated ?? finding.is_negation ?? false;
  const jokePenalty = filters.joke_score ?? finding.joke_penalty ?? 0;
  const negPenalty = filters.negation_score ?? finding.negation_penalty ?? 0;

  // Context type — top-level field
  const contextType = finding.context_type || finding.context?.primary || 'NEUTRAL';

  // Matched text (single string from backend)
  const matchedText = finding.matched_text;

  // Categories
  const categories = finding.categories || (finding.category ? [finding.category] : []);

  return (
    <div className="finding-debug-card hover-lift-3d" style={{ borderLeftColor: color }}>
      <div className="finding-debug-header" onClick={() => setExpanded(e => !e)}>
        <div className="finding-debug-left">
          <span className="finding-index">#{index + 1}</span>
          <div>
            <div className="finding-category">
              {categories.map(capitalize).join(' · ') || capitalize(finding.category)}
            </div>
            <div className="finding-text-preview">"{evidenceText.slice(0, 90)}{evidenceText.length > 90 ? '...' : ''}"</div>
          </div>
        </div>
        <div className="finding-debug-right">
          <div className="finding-meta-pills">
            <span className="meta-pill" style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}>
              {fmtPct(conf)} conf
            </span>
            {contextType && contextType !== 'NEUTRAL' && contextType !== 'neutral' && (
              <span className="meta-pill context-pill">{contextType}</span>
            )}
            {isJoke && <span className="meta-pill joke-pill">JOKE</span>}
            {isNegation && <span className="meta-pill neg-pill">NEGATION</span>}
          </div>
          <button className="expand-btn">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="finding-debug-body">
          {/* Full Text */}
          <div className="debug-section">
            <div className="debug-section-title"><FileText size={13} /> Full Text</div>
            <div className="debug-quote">"{evidenceText}"</div>
          </div>

          {/* Score Breakdown */}
          <div className="debug-section">
            <div className="debug-section-title"><BarChart2 size={13} /> Confidence Breakdown</div>
            <div className="debug-grid">
              <div className="debug-row"><span>Base Regex Confidence</span><strong>{baseConf != null ? fmtPct(baseConf) : '—'}</strong></div>
              <div className="debug-row"><span>Context Multiplier</span><strong>{ctxMultiplier != null ? `×${Number(ctxMultiplier).toFixed(2)}` : '—'}</strong></div>
              <div className="debug-row"><span>Joke Penalty</span><strong style={{ color: isJoke ? 'var(--status-high)' : 'var(--text-tertiary)' }}>{isJoke ? `-${fmtPct(jokePenalty)}` : 'None'}</strong></div>
              <div className="debug-row"><span>Negation Penalty</span><strong style={{ color: isNegation ? 'var(--status-moderate)' : 'var(--text-tertiary)' }}>{isNegation ? `-${fmtPct(negPenalty)}` : 'None'}</strong></div>
              {mlFusedConf != null && (
                <div className="debug-row"><span>ML Fused Confidence</span><strong style={{ color: 'var(--accent-primary)' }}>{fmtPct(mlFusedConf)}</strong></div>
              )}
              <div className="debug-row highlight"><span>Final Confidence</span><strong style={{ color }}>{fmtPct(conf)}</strong></div>
            </div>
            <ConfidenceBar value={conf} color={color} />
          </div>

          {/* Matched Text */}
          {matchedText && (
            <div className="debug-section">
              <div className="debug-section-title"><Zap size={13} /> Matched Pattern Text</div>
              <div className="pattern-chips">
                <code className="pattern-chip">{matchedText}</code>
              </div>
            </div>
          )}

          {/* Context Info */}
          <div className="debug-section">
            <div className="debug-section-title"><Eye size={13} /> Context Analysis</div>
            <div className="debug-grid">
              <div className="debug-row"><span>Context Type</span><strong>{contextType}</strong></div>
              <div className="debug-row"><span>Speaker</span><strong>{finding.speaker || 'Unknown'}</strong></div>
              {finding.pattern_count != null && <div className="debug-row"><span>Pattern Matches</span><strong>{finding.pattern_count}</strong></div>}
              {finding.timestamp != null && <div className="debug-row"><span>Timestamp</span><strong>{Number(finding.timestamp).toFixed(1)}s</strong></div>}
            </div>
          </div>

          {/* ML Result */}
          {Object.keys(mlResult).length > 0 && !mlResult.error && (
            <div className="debug-section">
              <div className="debug-section-title"><Brain size={13} /> ML Zero-Shot (DistilBERT-MNLI)</div>
              <div className="debug-grid">
                <div className="debug-row"><span>Top Label</span><strong style={{ color: 'var(--accent-primary)' }}>{capitalize(mlResult.top_label)}</strong></div>
                <div className="debug-row"><span>Top Confidence</span><strong>{fmtPct(mlResult.top_confidence)}</strong></div>
                <div className="debug-row"><span>ML Risk Score</span><strong>{fmtPct(mlResult.ml_risk_score)}</strong></div>
                <div className="debug-row">
                  <span>Agreement with Regex</span>
                  <strong style={{ color: mlResult.agreement ? 'var(--status-safe)' : 'var(--status-high)' }}>
                    {mlResult.agreement == null ? '—' : mlResult.agreement ? '✓ Agrees' : '✗ Disagrees'}
                  </strong>
                </div>
                {mlResult.disagreement_flag && (
                  <div className="debug-row" style={{ gridColumn: '1/-1' }}>
                    <span className="disagreement-flag">⚠ Disagreement Flag: ML contradicts regex signal</span>
                  </div>
                )}
              </div>
              {mlResult.all_scores && (
                <div className="ml-scores-grid">
                  {Object.entries(mlResult.all_scores)
                    .sort(([, a], [, b]) => b - a)
                    .map(([label, score]) => (
                      <div key={label} className="ml-score-row">
                        <span className="ml-score-label">{capitalize(label)}</span>
                        <div className="conf-bar-track small">
                          <div className="conf-bar-fill" style={{ width: `${score * 100}%`, background: label === 'safe' ? 'var(--status-safe)' : 'var(--accent-secondary)' }} />
                        </div>
                        <span className="ml-score-val">{(score * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}

          {/* Matched Labels */}
          {mlResult.matched_labels && mlResult.matched_labels.length > 0 && (
            <div className="debug-section">
              <div className="debug-section-title"><CheckCircle size={13} /> ML Matched Labels</div>
              <div className="pattern-chips">
                {mlResult.matched_labels.map((l, i) => (
                  <span key={i} className="meta-pill" style={{ background: 'var(--accent-primary)22', color: 'var(--accent-primary)', border: '1px solid var(--accent-primary)44' }}>
                    {capitalize(l)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Main Component ──────────────────────────────────────────────────────────
const Report = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [report, setReport]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [chatOpen, setChatOpen]   = useState(false);

  // Track which tabs have been visited — show skeleton on first render
  const [tabsReady, setTabsReady] = useState({ overview: false, findings: false, evidence: false });

  // Mark a tab as ready after its first paint (one animation frame delay)
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (!tabsReady[tab]) {
      requestAnimationFrame(() =>
        setTabsReady(prev => ({ ...prev, [tab]: true }))
      );
    }
  };

  // Email notification state
  const [emailStatus, setEmailStatus] = useState(null); // null | 'sending' | 'sent' | 'error'
  const [emailMsg, setEmailMsg]       = useState('');

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting]               = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteReport(id);
      navigate('/', { replace: true });
    } catch (e) {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
      alert(`Failed to delete report: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const handleSendAlert = async () => {
    setEmailStatus('sending');
    try {
      await sendAlertEmail(id);
      setEmailStatus('sent');
      setEmailMsg('Alert email sent');
    } catch (e) {
      setEmailStatus('error');
      setEmailMsg(e?.response?.data?.detail || 'Failed to send alert');
    }
    setTimeout(() => setEmailStatus(null), 4000);
  };

  const handleSendSummary = async () => {
    setEmailStatus('sending');
    try {
      await sendSummaryEmail(id);
      setEmailStatus('sent');
      setEmailMsg('Summary email sent');
    } catch (e) {
      setEmailStatus('error');
      setEmailMsg(e?.response?.data?.detail || 'Failed to send summary');
    }
    setTimeout(() => setEmailStatus(null), 4000);
  };

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const data = await getReport(id);
        setReport(data);
        // Overview is the default tab — mark it ready after data arrives
        requestAnimationFrame(() =>
          setTabsReady(prev => ({ ...prev, overview: true }))
        );
      } catch (err) {
        console.error('Failed to fetch report', err);
      } finally {
        setLoading(false);
      }
    };
    fetchReport();
  }, [id]);

  if (loading) return (
    <div className="report-loading">
      <div className="loading-spinner" />
      <span>Loading analysis report...</span>
    </div>
  );

  if (!report) return (
    <div className="report-loading">
      <XCircle size={40} style={{ color: 'var(--status-high)' }} />
      <span>Report not found.</span>
    </div>
  );

  const scoreColor = getScoreColor(report.risk_score);
  const radius = 88;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - ((report.risk_score || 0) / 100) * circumference;

  const findings = Array.isArray(report.findings) ? report.findings : [];
  const evidence = Array.isArray(report.evidence) ? report.evidence : [];
  const stats = report.stats || {};

  // Chart data — backend sends stats.categories (not category_breakdown)
  const categoryData = (stats.categories || stats.category_breakdown)
    ? Object.entries(stats.categories || stats.category_breakdown)
        .map(([name, points]) => ({ name: capitalize(name), points }))
        .sort((a, b) => b.points - a.points)
    : [];

  const radarData = categoryData.slice(0, 6).map(d => ({
    subject: d.name.split(' ')[0],
    score: d.points
  }));

  const severityDist = findings.reduce((acc, f) => {
    const bucket = f.severity || (f.confidence >= 0.7 ? 'High' : f.confidence >= 0.4 ? 'Medium' : 'Low');
    acc[bucket] = (acc[bucket] || 0) + 1;
    return acc;
  }, {});
  const pieData = Object.entries(severityDist).map(([name, value]) => ({ name, value }));
  const PIE_COLORS = ['#b91c1c', '#ef4444', '#f59e0b', '#3b82f6', '#10b981'];

  // ── New analytics derived data ───────────────────────────────────────────

  // Context type distribution (from stored stats or computed from findings)
  const ctxDistRaw = stats.context_type_distribution
    || findings.reduce((acc, f) => {
        const ctx = f.context_type || f.context?.primary;
        if (ctx) acc[ctx] = (acc[ctx] || 0) + 1;
        return acc;
      }, {});
  const CTX_PIE_COLORS = ['var(--status-critical)', 'var(--accent-primary)', 'var(--status-safe)', 'var(--text-tertiary)', 'var(--status-moderate)'];
  const ctxDistData = Object.entries(ctxDistRaw).map(([name, count]) => ({ name: capitalize(name), count }));

  // Confidence histogram (from stored stats or computed)
  const confHistRaw = stats.confidence_histogram || (() => {
    const h = { '0-25': 0, '25-50': 0, '50-75': 0, '75-100': 0 };
    findings.forEach(f => {
      const pct = ((f.confidence || f.max_confidence || 0)) * 100;
      if (pct <= 25) h['0-25']++;
      else if (pct <= 50) h['25-50']++;
      else if (pct <= 75) h['50-75']++;
      else h['75-100']++;
    });
    return h;
  })();
  const CONF_COLORS = ['var(--text-tertiary)', 'var(--status-low)', 'var(--status-moderate)', 'var(--status-high)'];
  const confHistData = Object.entries(confHistRaw).map(([range, count]) => ({ range: range + '%', count }));

  // Speaker breakdown
  const speakerRaw = stats.speaker_distribution
    || findings.reduce((acc, f) => {
        if (f.speaker) acc[f.speaker] = (acc[f.speaker] || 0) + 1;
        return acc;
      }, {});
  const speakerData = Object.entries(speakerRaw)
    .map(([speaker, count]) => ({ speaker, count }))
    .sort((a, b) => b.count - a.count);

  // Findings timeline scatter (from stored stats or computed)
  const timelineScatter = (stats.findings_timeline || findings
    .filter(f => f.timestamp != null && (f.confidence || f.max_confidence) != null)
    .map(f => ({
      timestamp: Math.round(f.timestamp),
      confidence: f.confidence || f.max_confidence || 0,
      category: (f.categories?.[0] || f.category || 'unknown'),
    }))
  );

  // ML agreement
  const mlAgreed    = findings.filter(f => (f.ml || f.ml_result)?.agreement === true).length;
  const mlDisagreed = findings.filter(f => (f.ml || f.ml_result)?.disagreement_flag === true).length;
  const mlNoSignal  = findings.filter(f => {
    const ml = f.ml || f.ml_result;
    return ml && !ml.error && ml.agreement == null && !ml.disagreement_flag;
  }).length;
  const mlAgreementData = [
    { name: 'Agreed', value: mlAgreed },
    { name: 'Disagreed', value: mlDisagreed },
    { name: 'No Signal', value: mlNoSignal },
  ].filter(d => d.value > 0);
  const mlAgreementRate = (mlAgreed + mlDisagreed) > 0
    ? mlAgreed / (mlAgreed + mlDisagreed)
    : null;

  // Timeline
  const timeline = Array.isArray(report.timeline) ? report.timeline : [];
  // Build a set of flagged text snippets for highlighting
  const flaggedTexts = new Set(findings.map(f => (f.evidence || f.text || '').toLowerCase().trim()));

  return (
    <div className="report-wrapper">
      {/* ── Header ── */}
      <div className="report-header animate-slide-up delay-100">
        <div className="report-header-left">
          <button className="btn btn-icon" onClick={() => navigate('/')} title="Back to Dashboard">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="report-title text-gradient">Analysis Report</h1>
            <p className="report-filename" title={report.filename}>{report.filename}</p>
          </div>
        </div>
        <div className="report-header-right">
          <div className="report-header-score">
            <span style={{ color: scoreColor, fontSize: '2rem', fontWeight: 700 }}>{(report.risk_score || 0).toFixed(0)}</span>
            <span className="report-header-label">Risk Score</span>
          </div>
          <span className={`badge badge-${(report.severity || 'safe').toLowerCase()}`}>{report.severity}</span>
          <a href={downloadPdfUrl(id)} target="_blank" rel="noreferrer" className="btn btn-primary">
            <Download size={16} /> PDF Report
          </a>
          <button
            className="btn btn-secondary"
            onClick={handleSendAlert}
            disabled={emailStatus === 'sending'}
            title="Send red-alert email to configured recipients"
          >
            <Bell size={16} style={{ color: 'var(--status-high)' }} />
            {emailStatus === 'sending' ? 'Sending…' : 'Send Alert'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleSendSummary}
            disabled={emailStatus === 'sending'}
            title="Send full analysis summary email"
          >
            <Mail size={16} />
            {emailStatus === 'sending' ? 'Sending…' : 'Email Summary'}
          </button>
          <button className="btn btn-secondary" onClick={() => setChatOpen(o => !o)}>
            <MessageSquare size={16} /> {chatOpen ? 'Close Chat' : 'Ask AI'}
          </button>
          <button
            className="btn"
            style={{
              background: 'transparent',
              border: '1px solid var(--status-high)',
              color: 'var(--status-high)',
              display: 'flex', alignItems: 'center', gap: '0.4rem',
            }}
            onClick={() => setShowDeleteConfirm(true)}
            title="Delete this report"
          >
            <Trash2 size={15} /> Delete
          </button>

          {/* Email toast */}
          {emailStatus && emailStatus !== 'sending' && (
            <div style={{
              position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
              background: emailStatus === 'sent' ? 'var(--status-safe)' : 'var(--status-high)',
              color: '#fff', padding: '10px 18px', borderRadius: 8,
              fontSize: '0.85rem', fontWeight: 600,
              boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              animation: 'fadeIn 0.2s ease',
            }}>
              {emailStatus === 'sent' ? <CheckCircle size={15} /> : <XCircle size={15} />}
              {emailMsg}
            </div>
          )}
        </div>
      </div>

      {/* ── Top Stats Bar ── */}
      <div className="report-stats-bar glass-panel animate-slide-up delay-200">
        <StatPill label="Total Findings" value={findings.length} color="var(--text-primary)" />
        <div className="stats-bar-divider" />
        <StatPill label="Evidence Items" value={evidence.length} color="var(--accent-primary)" />
        <div className="stats-bar-divider" />
        <StatPill label="Words Analyzed" value={stats.word_count || '—'} color="var(--text-primary)" />
        <div className="stats-bar-divider" />
        <StatPill label="Risk Categories" value={categoryData.length} color="var(--accent-secondary)" />
        <div className="stats-bar-divider" />
        <StatPill label="Timeline Segments" value={timeline.length} color="var(--text-primary)" />
        <div className="stats-bar-divider" />
        <StatPill label="Severity" value={report.severity} color={scoreColor} />
      </div>

      {/* ── Main Layout ── */}
      <div className={`report-main-layout ${chatOpen ? 'chat-open' : ''}`}>
        <div className="report-content">
          {/* Tab Navigation */}
          <div className="report-tabs glass-panel animate-slide-up delay-300">
            <TabButton active={activeTab === 'overview'}  onClick={() => handleTabChange('overview')}  icon={Activity}    label="Overview" />
            <TabButton active={activeTab === 'findings'}  onClick={() => handleTabChange('findings')}  icon={ShieldAlert} label="Findings Debugger" count={findings.length} />
            <TabButton active={activeTab === 'evidence'}  onClick={() => handleTabChange('evidence')}  icon={Eye}         label="Evidence Log" count={evidence.length} />
            <TabButton active={activeTab === 'timeline'}  onClick={() => handleTabChange('timeline')}  icon={Clock}       label="Timeline" count={timeline.length} />
            <TabButton active={activeTab === 'analytics'} onClick={() => handleTabChange('analytics')} icon={TrendingUp}  label="Analytics" />
            <TabButton active={activeTab === 'raw'}       onClick={() => handleTabChange('raw')}       icon={Database}    label="Raw Data" />
          </div>

          {/* ─────────────── TAB: OVERVIEW ─────────────── */}
          {activeTab === 'overview' && (
            <div className="tab-content animate-fade-in">
              <div className="overview-top-grid">
                {/* Risk Ring */}
                <div className="glass-panel risk-ring-panel hover-lift-3d">
                  <h3 className="panel-heading">Overall Risk Score</h3>
                  <div className="risk-ring-wrap">
                    <svg width="210" height="210" style={{ transform: 'rotate(-90deg)' }}>
                      <defs>
                        <filter id="glow">
                          <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                          <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
                        </filter>
                      </defs>
                      <circle cx="105" cy="105" r={radius} fill="none" stroke="var(--border-color)" strokeWidth="14" />
                      <circle
                        cx="105" cy="105" r={radius}
                        fill="none" stroke={scoreColor} strokeWidth="14"
                        strokeDasharray={circumference} strokeDashoffset={strokeDashoffset}
                        strokeLinecap="round" filter="url(#glow)"
                        style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)' }}
                      />
                    </svg>
                    <div className="risk-ring-inner">
                      <span className="risk-ring-score" style={{ color: scoreColor }}>{(report.risk_score || 0).toFixed(0)}</span>
                      <span className="risk-ring-label">out of 100</span>
                      <span className={`badge badge-${(report.severity || 'safe').toLowerCase()}`} style={{ marginTop: '0.5rem' }}>
                        {report.severity}
                      </span>
                    </div>
                  </div>
                  {/* Mini stats */}
                  <div className="risk-mini-stats">
                    <div className="risk-mini-item">
                      <span className="risk-mini-label">Findings</span>
                      <span className="risk-mini-val">{findings.length}</span>
                    </div>
                    <div className="risk-mini-item">
                      <span className="risk-mini-label">Evidence</span>
                      <span className="risk-mini-val">{evidence.length}</span>
                    </div>
                    <div className="risk-mini-item">
                      <span className="risk-mini-label">Categories</span>
                      <span className="risk-mini-val">{categoryData.length}</span>
                    </div>
                  </div>
                </div>

                {/* Summaries */}
                <div className="summaries-col">
                  {/* LLM Summary */}
                  <div className="glass-panel summary-panel hover-lift-3d">
                    <div className="panel-heading-row">
                      <Brain size={18} style={{ color: 'var(--accent-primary)' }} />
                      <h3 className="panel-heading">AI Executive Summary</h3>
                      <span className="summary-badge">LLaMA 3.1</span>
                    </div>
                    <div className="summary-text">{report.llm_summary || 'LLM summary not available.'}</div>
                  </div>
                  {/* Rule-Based Summary */}
                  <div className="glass-panel summary-panel hover-lift-3d">
                    <div className="panel-heading-row">
                      <Info size={18} style={{ color: 'var(--accent-secondary)' }} />
                      <h3 className="panel-heading">Rule-Based Summary</h3>
                      <span className="summary-badge secondary">Pipeline</span>
                    </div>
                    <div className="summary-text secondary">{report.summary || 'Summary not available.'}</div>
                  </div>
                </div>
              </div>

              {/* Top Category Bar Chart */}
              {categoryData.length > 0 && (
                <div className="glass-panel chart-panel hover-lift-3d">
                  <div className="panel-heading-row">
                    <BarChart2 size={18} style={{ color: 'var(--accent-primary)' }} />
                    <h3 className="panel-heading">Risk Category Breakdown</h3>
                  </div>
                  <div style={{ width: '100%', height: 320 }}>
                    <ResponsiveContainer>
                      <BarChart data={categoryData} layout="vertical" margin={{ top: 5, right: 40, left: 140, bottom: 5 }}>
                        <XAxis type="number" stroke="var(--text-tertiary)" fontSize={12} />
                        <YAxis dataKey="name" type="category" width={135} stroke="var(--text-secondary)" fontSize={12} tick={{ fill: 'var(--text-secondary)' }} />
                        <Tooltip
                          cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                          contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }}
                        />
                        <Bar dataKey="points" radius={[0, 6, 6, 0]}>
                          {categoryData.map((entry, i) => (
                            <Cell key={i} fill={i === 0 ? 'var(--status-critical)' : i === 1 ? 'var(--status-high)' : i < 4 ? 'var(--status-moderate)' : 'var(--status-low)'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ─────────────── TAB: FINDINGS DEBUGGER ─────────────── */}
          {activeTab === 'findings' && (
            <div className="tab-content animate-fade-in">
              <div className="findings-toolbar glass-panel">
                <span className="findings-count">{findings.length} findings</span>
                <span className="findings-hint">Click any finding to expand the full ML and regex breakdown</span>
              </div>
              {!tabsReady.findings ? (
                <FindingsSkeleton />
              ) : findings.length === 0 ? (
                <div className="empty-state glass-panel">
                  <CheckCircle size={40} style={{ color: 'var(--status-safe)' }} />
                  <p>No concerning findings detected by the pipeline.</p>
                </div>
              ) : (
                <div className="findings-debug-list">
                  {findings.map((finding, i) => (
                    <FindingCard key={i} finding={finding} index={i} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ─────────────── TAB: EVIDENCE LOG ─────────────── */}
          {activeTab === 'evidence' && (
            <div className="tab-content animate-fade-in">
              {!tabsReady.evidence ? (
                <EvidenceSkeleton />
              ) : evidence.length === 0 ? (
                <div className="empty-state glass-panel">
                  <CheckCircle size={40} style={{ color: 'var(--status-safe)' }} />
                  <p>No extracted evidence found.</p>
                </div>
              ) : (
                <div className="evidence-list">
                  {evidence.map((ev, i) => {
                    const sColor = getSeverityColor(ev.severity);
                    return (
                      <div key={i} className="evidence-card glass-panel hover-lift-3d" style={{ borderLeftColor: sColor }}>
                        <div className="evidence-header">
                          <div className="evidence-cats">
                            {(ev.categories || []).map((c, ci) => (
                              <span key={ci} className="cat-tag">{capitalize(c)}</span>
                            ))}
                          </div>
                          <div className="evidence-meta-right">
                            <span className="meta-pill" style={{ background: `${sColor}22`, color: sColor, border: `1px solid ${sColor}44` }}>
                              {fmtPct(ev.confidence)} confidence
                            </span>
                            {ev.severity && <span className={`badge badge-${ev.severity.toLowerCase()}`}>{ev.severity}</span>}
                          </div>
                        </div>
                        <blockquote className="evidence-quote">"{ev.evidence || ev.text || ''}"</blockquote>
                        <div className="evidence-details-grid">
                          {ev.context_type && (
                            <div className="evidence-detail"><span>Context</span><strong style={{ color: 'var(--accent-primary)' }}>{ev.context_type}</strong></div>
                          )}
                          {ev.speaker && (
                            <div className="evidence-detail"><span>Speaker</span><strong>{ev.speaker}</strong></div>
                          )}
                          {ev.base_confidence != null && (
                            <div className="evidence-detail"><span>Base Regex</span><strong>{fmtPct(ev.base_confidence)}</strong></div>
                          )}
                          {ev.context_multiplier != null && (
                            <div className="evidence-detail"><span>Context Mult.</span><strong>×{ev.context_multiplier?.toFixed(2)}</strong></div>
                          )}
                          {ev.is_joke != null && (
                            <div className="evidence-detail"><span>Joke</span><strong>{ev.is_joke ? 'Yes ⚠' : 'No'}</strong></div>
                          )}
                          {ev.is_negation != null && (
                            <div className="evidence-detail"><span>Negation</span><strong>{ev.is_negation ? 'Yes ⚠' : 'No'}</strong></div>
                          )}
                        </div>
                        {ev.confidence != null && (
                          <div style={{ marginTop: '0.75rem' }}>
                            <ConfidenceBar value={ev.confidence} color={sColor} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ─────────────── TAB: TIMELINE ─────────────── */}
          {activeTab === 'timeline' && (
            <div className="tab-content animate-fade-in">
              <div className="glass-panel" style={{ padding: 'var(--spacing-lg)', marginBottom: 'var(--spacing-md)' }}>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                  <strong style={{ color: 'var(--status-high)' }}>Red segments</strong> contain flagged text.
                  Timestamps show Whisper's transcription timing.
                </p>
              </div>
              {timeline.length === 0 ? (
                <div className="glass-panel" style={{ padding: 'var(--spacing-xl)' }}>
                  <p style={{ color: 'var(--text-secondary)' }}>No timeline segments available. Showing full transcript instead:</p>
                  <div className="transcript-box">{report.transcript || '—'}</div>
                </div>
              ) : (
                <div className="timeline-list">
                  {timeline.map((seg, i) => {
                    const textLower = (seg.text || '').toLowerCase().trim();
                    const isFlagged = [...flaggedTexts].some(ft => textLower.includes(ft.slice(0, 30)));
                    return (
                      <div key={i} className={`timeline-segment glass-panel ${isFlagged ? 'flagged' : ''}`}>
                        <div className="timeline-ts">
                          <Clock size={12} />
                          <span>{typeof seg.start === 'number' ? `${seg.start.toFixed(1)}s` : seg.start}</span>
                          <span className="ts-arrow">→</span>
                          <span>{typeof seg.end === 'number' ? `${seg.end.toFixed(1)}s` : seg.end}</span>
                        </div>
                        <p className="timeline-text">{seg.text}</p>
                        {isFlagged && (
                          <span className="flagged-badge"><AlertTriangle size={11} /> Flagged</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ─────────────── TAB: ANALYTICS ─────────────── */}
          {activeTab === 'analytics' && (
            <div className="tab-content animate-fade-in">
              {/* Stats Cards */}
              <div className="analytics-stats-grid">
                {[
                  { label: 'Risk Score', value: `${(report.risk_score || 0).toFixed(1)}`, color: scoreColor },
                  { label: 'Total Words', value: stats.word_count || '—' },
                  { label: 'Flagged Sentences', value: stats.flagged_sentences || findings.length },
                  { label: 'Unique Categories', value: stats.unique_categories ?? categoryData.length },
                  { label: 'High Conf Matches', value: stats.high_confidence_count ?? findings.filter(f => (f.confidence || f.max_confidence || 0) >= 0.7).length, color: 'var(--status-high)' },
                  { label: 'ML Disagreements', value: findings.filter(f => (f.ml || f.ml_result)?.disagreement_flag).length, color: 'var(--status-moderate)' },
                  { label: 'Avg Confidence', value: stats.confidence_stats?.average != null ? `${(stats.confidence_stats.average * 100).toFixed(1)}%` : '—', color: 'var(--accent-primary)' },
                  { label: 'Unique Speakers', value: Object.keys(stats.speaker_distribution || {}).length || '—' },
                ].map((s, i) => (
                  <div key={i} className="analytics-stat-card glass-panel">
                    <span className="analytics-stat-label">{s.label}</span>
                    <span className="analytics-stat-val" style={{ color: s.color || 'var(--text-primary)' }}>{s.value}</span>
                  </div>
                ))}
              </div>

              <div className="analytics-charts-grid">
                {/* Radar */}
                {radarData.length > 2 && (
                  <div className="glass-panel chart-panel">
                    <div className="panel-heading-row">
                      <Activity size={16} style={{ color: 'var(--accent-primary)' }} />
                      <h3 className="panel-heading">Risk Radar</h3>
                    </div>
                    <div style={{ height: 300 }}>
                      <ResponsiveContainer>
                        <RadarChart data={radarData}>
                          <PolarGrid stroke="var(--border-color)" />
                          <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                          <Radar name="Risk" dataKey="score" stroke="var(--accent-primary)" fill="var(--accent-primary)" fillOpacity={0.2} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Severity Pie */}
                {pieData.length > 0 && (
                  <div className="glass-panel chart-panel">
                    <div className="panel-heading-row">
                      <TrendingUp size={16} style={{ color: 'var(--accent-secondary)' }} />
                      <h3 className="panel-heading">Severity Distribution</h3>
                    </div>
                    <div style={{ height: 300 }}>
                      <ResponsiveContainer>
                        <PieChart>
                          <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                            {pieData.map((entry, i) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }} />
                          <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Context Type Distribution */}
                {ctxDistData.length > 0 && (
                  <div className="glass-panel chart-panel">
                    <div className="panel-heading-row">
                      <Eye size={16} style={{ color: 'var(--accent-primary)' }} />
                      <h3 className="panel-heading">Context Type Distribution</h3>
                    </div>
                    <div style={{ height: 300 }}>
                      <ResponsiveContainer>
                        <BarChart data={ctxDistData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                          <XAxis dataKey="name" stroke="var(--text-tertiary)" fontSize={11} />
                          <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                          <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                          <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Findings">
                            {ctxDistData.map((entry, i) => (
                              <Cell key={i} fill={CTX_PIE_COLORS[i % CTX_PIE_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Confidence Histogram */}
                {confHistData.some(d => d.count > 0) && (
                  <div className="glass-panel chart-panel">
                    <div className="panel-heading-row">
                      <BarChart2 size={16} style={{ color: 'var(--accent-secondary)' }} />
                      <h3 className="panel-heading">Confidence Distribution</h3>
                    </div>
                    <div style={{ height: 300 }}>
                      <ResponsiveContainer>
                        <BarChart data={confHistData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                          <XAxis dataKey="range" stroke="var(--text-tertiary)" fontSize={11} />
                          <YAxis stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                          <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                          <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Findings">
                            {confHistData.map((entry, i) => (
                              <Cell key={i} fill={CONF_COLORS[i % CONF_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Speaker Breakdown */}
                {speakerData.length > 0 && (
                  <div className="glass-panel chart-panel">
                    <div className="panel-heading-row">
                      <Users size={16} style={{ color: 'var(--accent-primary)' }} />
                      <h3 className="panel-heading">Findings by Speaker</h3>
                    </div>
                    <div style={{ height: 300 }}>
                      <ResponsiveContainer>
                        <BarChart data={speakerData} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
                          <XAxis type="number" stroke="var(--text-tertiary)" fontSize={11} allowDecimals={false} />
                          <YAxis dataKey="speaker" type="category" width={75} stroke="var(--text-secondary)" fontSize={11} tick={{ fill: 'var(--text-secondary)' }} />
                          <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                          <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Findings" fill="var(--accent-secondary)" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* ML Agreement Pie */}
                {mlAgreementData.length > 0 && (
                  <div className="glass-panel chart-panel">
                    <div className="panel-heading-row">
                      <Brain size={16} style={{ color: 'var(--accent-primary)' }} />
                      <h3 className="panel-heading">ML vs Regex Agreement</h3>
                    </div>
                    <div style={{ height: 300 }}>
                      <ResponsiveContainer>
                        <PieChart>
                          <Pie data={mlAgreementData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                            <Cell fill="var(--status-safe)" />
                            <Cell fill="var(--status-high)" />
                            <Cell fill="var(--text-tertiary)" />
                          </Pie>
                          <Tooltip contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }} />
                          <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    {mlAgreementRate != null && (
                      <div style={{ textAlign: 'center', marginTop: '0.5rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                        Agreement rate: <strong style={{ color: 'var(--status-safe)' }}>{(mlAgreementRate * 100).toFixed(1)}%</strong>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Findings Timeline Scatter */}
              {timelineScatter.length > 0 && (
                <div className="glass-panel chart-panel" style={{ marginTop: 'var(--spacing-lg)' }}>
                  <div className="panel-heading-row">
                    <Clock size={16} style={{ color: 'var(--accent-primary)' }} />
                    <h3 className="panel-heading">Findings Over Time (Confidence vs Sentence Index)</h3>
                  </div>
                  <div style={{ height: 280 }}>
                    <ResponsiveContainer>
                      <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                        <CartesianGrid stroke="var(--border-color)" strokeDasharray="3 3" />
                        <XAxis dataKey="timestamp" name="Sentence" stroke="var(--text-tertiary)" fontSize={11} label={{ value: 'Sentence Index', position: 'insideBottom', offset: -5, fill: 'var(--text-tertiary)', fontSize: 11 }} />
                        <YAxis dataKey="confidence" name="Confidence" domain={[0, 1]} stroke="var(--text-tertiary)" fontSize={11} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
                        <ZAxis range={[40, 40]} />
                        <Tooltip
                          cursor={{ strokeDasharray: '3 3' }}
                          contentStyle={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)', fontSize: '0.82rem' }}
                          formatter={(value, name) => [name === 'Confidence' ? `${(value * 100).toFixed(1)}%` : value, name]}
                        />
                        <Scatter data={timelineScatter} fill="var(--accent-primary)" fillOpacity={0.7} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Full stats object */}
              {Object.keys(stats).length > 0 && (
                <div className="glass-panel chart-panel" style={{ marginTop: 'var(--spacing-lg)' }}>
                  <div className="panel-heading-row">
                    <Database size={16} style={{ color: 'var(--text-tertiary)' }} />
                    <h3 className="panel-heading">Full Stats Object</h3>
                  </div>
                  <div className="stats-kv-grid">
                    {Object.entries(stats)
                      .filter(([k]) => !['category_breakdown', 'categories', 'severity_distribution', 'context_type_distribution', 'speaker_distribution', 'confidence_histogram', 'ml_stats', 'findings_timeline', 'confidence_stats'].includes(k))
                      .map(([k, v]) => (
                        <div key={k} className="debug-row">
                          <span>{capitalize(k)}</span>
                          <strong>{typeof v === 'number' ? v.toFixed(2) : String(v)}</strong>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ─────────────── TAB: RAW DATA ─────────────── */}
          {activeTab === 'raw' && (
            <div className="tab-content animate-fade-in">
              <div className="glass-panel raw-panel">
                <div className="panel-heading-row">
                  <Code size={16} style={{ color: 'var(--accent-primary)' }} />
                  <h3 className="panel-heading">Full Report JSON</h3>
                  <button className="btn btn-secondary" style={{ marginLeft: 'auto', fontSize: '0.8rem', padding: '0.3rem 0.8rem' }}
                    onClick={() => navigator.clipboard.writeText(JSON.stringify(report, null, 2))}>
                    Copy JSON
                  </button>
                </div>
                <pre className="raw-json">{JSON.stringify(report, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>

        {/* Chatbot Sidebar */}
        {chatOpen && (
          <div className="report-chat-sidebar animate-fade-in">
            <Chatbot reportId={id} />
          </div>
        )}
      </div>

      {/* ── Delete confirmation modal ─────────────────────────────────────── */}
      {showDeleteConfirm && createPortal(
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '1rem',
            overflowY: 'auto',
          }}
          onClick={() => !isDeleting && setShowDeleteConfirm(false)}
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
              {!isDeleting && (
                <button
                  className="btn-icon"
                  onClick={() => setShowDeleteConfirm(false)}
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  <X size={18} />
                </button>
              )}
            </div>

            {/* Body */}
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
              Are you sure you want to permanently delete this report?
            </p>
            <div style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: '0.75rem 1rem',
              marginBottom: '1rem',
              fontSize: '0.85rem',
            }}>
              <div style={{ color: 'var(--text-tertiary)', marginBottom: '0.2rem' }}>#{report.id}</div>
              <div style={{ color: 'var(--text-primary)', fontWeight: 500, wordBreak: 'break-all' }}>
                {report.filename}
              </div>
              <div style={{ marginTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className={`badge badge-${(report.severity || 'safe').toLowerCase()}`}>
                  {report.severity}
                </span>
                <span style={{ color: scoreColor, fontWeight: 600, fontSize: '0.82rem' }}>
                  Score: {(report.risk_score || 0).toFixed(0)}
                </span>
              </div>
            </div>
            <p style={{ color: 'var(--text-tertiary)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>
              This will permanently delete the database record and the PDF report from disk. This action cannot be undone.
            </p>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={isDeleting}
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
                  opacity: isDeleting ? 0.7 : 1,
                  cursor: isDeleting ? 'not-allowed' : 'pointer',
                }}
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? (
                  <>
                    <div style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                    Deleting…
                  </>
                ) : (
                  <><Trash2 size={14} /> Delete</>
                )}
              </button>
            </div>
          </div>
        </div>
      , document.body
      )}
    </div>
  );
};

export default Report;
