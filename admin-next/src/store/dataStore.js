'use client';

/**
 * dataStore — Global state for history + analytics, ported from the Context-based
 * DataStore to Zustand (matches the host platform's state-management stack).
 *
 * Behaviour preserved from the original:
 *   - One central fetch shared by all pages.
 *   - Optimistic add/remove/update mutations for instant UI feedback.
 *   - WebSocket-driven refresh hooks (addReport / updateReport / refresh).
 *   - Background polling (every 30s) while any report is PROCESSING.
 *   - Analytics fetch debounced to once per minute.
 *
 * Usage:
 *   const { history, analytics, loading, refresh, removeReport, addReport } = useDataStore();
 *   useDataStoreInit();   // call once in a top-level client component to kick off loading
 */

import { create } from 'zustand';
import { getHistory, getAnalyticsSummary } from '@/lib/api';
import { useEffect, useMemo, useRef } from 'react';

const POLL_INTERVAL_MS = 30_000;
const ANALYTICS_TTL_MS = 60_000;
const PAGE_SIZE = 200;

export const useDataStore = create((set, get) => ({
  // ── State ──────────────────────────────────────────────────────────────────
  history: [],
  analytics: null,
  loading: true,
  refreshing: false,
  totalReports: 0,
  error: null,

  // Internal timestamps (not React state, but fine to keep on the store)
  _lastHistoryFetch: 0,
  _lastAnalyticsFetch: 0,

  // ── Core fetch ───────────────────────────────────────────────────────────────
  fetchHistory: async (silent = false) => {
    set(silent ? { refreshing: true } : { loading: true });
    try {
      const data = await getHistory(0, PAGE_SIZE);
      const reports = Array.isArray(data) ? data : (data?.reports ?? []);
      const total = Array.isArray(data) ? data.length : (data?.total ?? reports.length);
      set({
        history: reports,
        totalReports: total,
        error: null,
        _lastHistoryFetch: Date.now(),
      });
    } catch {
      if (!silent) set({ error: 'Failed to load reports' });
    } finally {
      set({ loading: false, refreshing: false });
    }
  },

  fetchAnalytics: async () => {
    if (Date.now() - get()._lastAnalyticsFetch < ANALYTICS_TTL_MS) return;
    try {
      const data = await getAnalyticsSummary();
      set({ analytics: data, _lastAnalyticsFetch: Date.now() });
    } catch {
      // analytics is non-fatal — keep stale value
    }
  },

  refresh: async (silent = false) => {
    await Promise.all([get().fetchHistory(silent), get().fetchAnalytics()]);
  },

  // ── Optimistic mutations ─────────────────────────────────────────────────────
  removeReport: (id) => {
    set((s) => ({
      history: s.history.filter((r) => r.id !== id),
      totalReports: Math.max(0, s.totalReports - 1),
    }));
    setTimeout(() => get().fetchAnalytics(), 1500);
  },

  addReport: (report) => {
    set((s) => {
      const exists = s.history.some((r) => r.id === report.id);
      const history = exists
        ? s.history.map((r) => (r.id === report.id ? { ...r, ...report } : r))
        : [report, ...s.history];
      return { history, totalReports: exists ? s.totalReports : s.totalReports + 1 };
    });
    setTimeout(() => get().fetchAnalytics(), 1500);
  },

  updateReport: (id, patch) => {
    set((s) => ({
      history: s.history.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }));
  },
}));

// ── Derived stats selector hook ────────────────────────────────────────────────

export const useDataStoreStats = () => {
  const history = useDataStore((s) => s.history);
  return useMemo(() => {
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
};

// ── Init hook — call ONCE in a top-level client component ───────────────────────

export const useDataStoreInit = () => {
  const refresh = useDataStore((s) => s.refresh);
  const fetchHistory = useDataStore((s) => s.fetchHistory);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    refresh(false); // initial full load

    // Background poll for PROCESSING jobs
    const timer = setInterval(() => {
      const hasProcessing = useDataStore
        .getState()
        .history.some((r) => (r.status || '').toUpperCase() === 'PROCESSING');
      if (hasProcessing) fetchHistory(true);
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [refresh, fetchHistory]);
};
