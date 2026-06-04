/**
 * DataStore — Global singleton state for history and analytics.
 *
 * WHY THIS EXISTS:
 * Every page (Dashboard, Upload, Analytics, GoogleDrive) was independently
 * fetching /history and /analytics/summary on mount. This meant:
 *   - Slow apparent performance (repeated round trips)
 *   - Dashboard didn't update after upload/delete without a manual refresh
 *   - Analytics showed stale counts
 *
 * HOW IT WORKS:
 *   1. One central fetch — first component to mount triggers the load.
 *      All others share the same in-memory state.
 *   2. Optimistic updates — delete/upload mutate local state instantly,
 *      so the UI feels immediate even before the server confirms.
 *   3. WebSocket-driven refresh — when analysis:completed fires over WS,
 *      the store prepends the new report and refreshes analytics silently.
 *   4. Invalidation — any component can call `refresh()` to force a refetch.
 *   5. Background polling — every 30 s the store checks for PROCESSING
 *      reports and refreshes if any are found, so in-progress jobs update.
 *
 * USAGE:
 *   const { history, analytics, loading, refresh, removeReport, addReport } = useDataStore();
 */

import React, {
  createContext, useContext, useCallback,
  useEffect, useRef, useState, useMemo,
} from 'react';
import { getHistory, getAnalyticsSummary } from '../api';

// ── Context ───────────────────────────────────────────────────────────────────

const DataStoreContext = createContext(null);

export const useDataStore = () => {
  const ctx = useContext(DataStoreContext);
  if (!ctx) throw new Error('useDataStore must be used inside <DataStoreProvider>');
  return ctx;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS   = 30_000;   // check for PROCESSING jobs every 30s
const ANALYTICS_TTL_MS   = 60_000;   // don't re-fetch analytics more than once/min
const PAGE_SIZE          = 200;      // load up to 200 reports into the store

// ── Provider ──────────────────────────────────────────────────────────────────

export const DataStoreProvider = ({ children }) => {
  const [history, setHistory]         = useState([]);
  const [analytics, setAnalytics]     = useState(null);
  const [loading, setLoading]         = useState(true);         // first load
  const [refreshing, setRefreshing]   = useState(false);        // background refresh
  const [totalReports, setTotalReports] = useState(0);
  const [error, setError]             = useState(null);

  // Timestamps to avoid redundant fetches
  const lastHistoryFetch   = useRef(0);
  const lastAnalyticsFetch = useRef(0);
  const pollTimer          = useRef(null);
  const mountedRef         = useRef(true);

  // ── Core fetch ─────────────────────────────────────────────────────────────

  const fetchHistory = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);

    try {
      const data = await getHistory(0, PAGE_SIZE);
      if (!mountedRef.current) return;

      const reports = Array.isArray(data) ? data : (data?.reports ?? []);
      const total   = Array.isArray(data) ? data.length : (data?.total ?? reports.length);

      setHistory(reports);
      setTotalReports(total);
      lastHistoryFetch.current = Date.now();
      setError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      if (!silent) setError('Failed to load reports');
    } finally {
      if (!mountedRef.current) return;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    // Debounce: don't fetch if we fetched within the TTL
    if (Date.now() - lastAnalyticsFetch.current < ANALYTICS_TTL_MS) return;
    try {
      const data = await getAnalyticsSummary();
      if (!mountedRef.current) return;
      setAnalytics(data);
      lastAnalyticsFetch.current = Date.now();
    } catch {
      // analytics is non-fatal — keep stale value
    }
  }, []);

  // Full refresh (history + analytics in parallel)
  const refresh = useCallback(async (silent = false) => {
    await Promise.all([fetchHistory(silent), fetchAnalytics()]);
  }, [fetchHistory, fetchAnalytics]);

  // ── Optimistic mutations ───────────────────────────────────────────────────

  /**
   * Instantly remove a report from local state.
   * The actual server delete is fired by the caller — this just makes
   * the UI feel immediate.
   */
  const removeReport = useCallback((id) => {
    setHistory(prev => prev.filter(r => r.id !== id));
    setTotalReports(prev => Math.max(0, prev - 1));
    // Quietly refresh analytics after a short delay
    setTimeout(() => fetchAnalytics(), 1500);
  }, [fetchAnalytics]);

  /**
   * Prepend a new/updated report to local state.
   * Used when an upload completes or a WS event fires.
   */
  const addReport = useCallback((report) => {
    setHistory(prev => {
      // Replace if it already exists (e.g. status update), else prepend
      const exists = prev.some(r => r.id === report.id);
      if (exists) return prev.map(r => r.id === report.id ? { ...r, ...report } : r);
      return [report, ...prev];
    });
    setTotalReports(prev => prev + 1);
    // Refresh analytics to reflect new report
    setTimeout(() => fetchAnalytics(), 1500);
  }, [fetchAnalytics]);

  /**
   * Update a specific report's fields in place (e.g. status change).
   */
  const updateReport = useCallback((id, patch) => {
    setHistory(prev => prev.map(r => r.id === id ? { ...r, ...patch } : r));
  }, []);

  // ── Background polling for PROCESSING jobs ─────────────────────────────────

  const startPolling = useCallback(() => {
    if (pollTimer.current) return; // already running
    pollTimer.current = setInterval(() => {
      if (!mountedRef.current) return;
      // Only poll if there are jobs still processing
      setHistory(current => {
        const hasProcessing = current.some(r =>
          (r.status || '').toUpperCase() === 'PROCESSING'
        );
        if (hasProcessing) {
          fetchHistory(true); // silent background refresh
        }
        return current; // no state change here — just checking
      });
    }, POLL_INTERVAL_MS);
  }, [fetchHistory]);

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;
    refresh(false);     // initial full load
    startPolling();     // start background poll

    return () => {
      mountedRef.current = false;
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    };
  }, [refresh, startPolling]);

  // ── Derived stats (memoized so consumers don't recompute) ──────────────────

  const stats = useMemo(() => {
    let highRisk = 0, safeCount = 0, avgScore = 0;
    for (const h of history) {
      const sev = (h.severity || '').toLowerCase();
      if (sev === 'high' || sev === 'critical') highRisk++;
      if (sev === 'safe' || sev === 'low') safeCount++;
      avgScore += h.risk_score || 0;
    }
    return {
      highRisk,
      safeCount,
      avgScore: history.length ? avgScore / history.length : 0,
    };
  }, [history]);

  // ── Context value ──────────────────────────────────────────────────────────

  const value = {
    // State
    history,
    analytics,
    loading,
    refreshing,
    totalReports,
    error,
    stats,

    // Actions
    refresh,
    removeReport,
    addReport,
    updateReport,
  };

  return (
    <DataStoreContext.Provider value={value}>
      {children}
    </DataStoreContext.Provider>
  );
};

export default DataStoreProvider;
