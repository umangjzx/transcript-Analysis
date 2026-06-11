'use client';

/**
 * NotificationProvider — Listens to WebSocket events and shows toast notifications
 * when analyses complete, fail, or start. Also provides a notification bell.
 *
 * Next.js port: react-router `useNavigate` -> next/navigation `useRouter`,
 * and the DataStore is now the Zustand store.
 */

import React, { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { useRouter } from 'next/navigation';
import { Bell, CheckCircle, AlertTriangle, Loader2, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';
import useWebSocket from '@/hooks/useWebSocket';
import { useDataStore } from '@/store/dataStore';

const NotificationContext = createContext(null);

export const useNotifications = () => useContext(NotificationContext);

const MAX_NOTIFICATIONS = 50;

export const NotificationProvider = ({ children }) => {
  const { isConnected, addListener } = useWebSocket();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const router = useRouter();

  const addReport = useDataStore((s) => s.addReport);
  const updateReport = useDataStore((s) => s.updateReport);
  const refresh = useDataStore((s) => s.refresh);

  const addNotification = useCallback((notification) => {
    setNotifications((prev) => [notification, ...prev].slice(0, MAX_NOTIFICATIONS));
    setUnreadCount((c) => c + 1);
  }, []);

  const clearUnread = useCallback(() => setUnreadCount(0), []);
  const clearAll = useCallback(() => {
    setNotifications([]);
    setUnreadCount(0);
  }, []);

  useEffect(() => {
    const unsubscribe = addListener((msg) => {
      const { event, data } = msg;

      if (event === 'analysis:completed') {
        addReport({
          id: data.report_id,
          filename: data.filename || `Report #${data.report_id}`,
          severity: data.severity || 'Unknown',
          risk_score: data.risk_score ?? 0,
          status: 'COMPLETED',
          created_at: data.created_at || new Date().toISOString(),
        });

        addNotification({
          id: Date.now(),
          type: 'success',
          title: 'Analysis Complete',
          message: `Report #${data.report_id} — ${data.severity} (Score: ${data.risk_score?.toFixed(0)})`,
          reportId: data.report_id,
          timestamp: new Date(),
        });
        toast.success(
          (t) => (
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span>Analysis #{data.report_id} complete — <strong>{data.severity}</strong></span>
              <button
                onClick={() => { toast.dismiss(t.id); router.push(`/report/${data.report_id}`); }}
                style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' }}
              >
                View
              </button>
            </span>
          ),
          { duration: 8000 }
        );
      }

      if (event === 'analysis:failed') {
        updateReport(data.report_id, { status: 'FAILED' });
        addNotification({
          id: Date.now(),
          type: 'error',
          title: 'Analysis Failed',
          message: `Report #${data.report_id} — ${data.error || 'Unknown error'}`,
          reportId: data.report_id,
          timestamp: new Date(),
        });
        toast.error(`Analysis #${data.report_id} failed: ${data.error || 'Unknown error'}`, { duration: 6000 });
      }

      if (event === 'analysis:started') {
        updateReport(data.report_id, { status: 'PROCESSING' });
        addNotification({
          id: Date.now(),
          type: 'info',
          title: 'Analysis Started',
          message: `Report #${data.report_id} is being processed`,
          reportId: data.report_id,
          timestamp: new Date(),
        });
      }

      if (['analysis:completed', 'analysis:failed'].includes(event)) {
        setTimeout(() => refresh(true), 2000);
      }
    });

    return unsubscribe;
  }, [addListener, addNotification, router, addReport, updateReport, refresh]);

  const value = { notifications, unreadCount, isConnected, clearUnread, clearAll };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
};

/**
 * NotificationBell — Dropdown bell icon showing recent notifications.
 */
export const NotificationBell = () => {
  const { notifications, unreadCount, isConnected, clearUnread, clearAll } = useNotifications();
  const [open, setOpen] = useState(false);
  const router = useRouter();

  const handleToggle = () => {
    setOpen((o) => !o);
    if (!open) clearUnread();
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        className="btn-icon"
        onClick={handleToggle}
        title={isConnected ? 'Notifications (live)' : 'Notifications (offline)'}
        aria-label="Notifications"
        style={{ position: 'relative' }}
      >
        <Bell size={20} />
        <span style={{
          position: 'absolute', bottom: 4, right: 4,
          width: 7, height: 7, borderRadius: '50%',
          background: isConnected ? 'var(--status-safe)' : 'var(--text-tertiary)',
          border: '1.5px solid var(--bg-primary)',
        }} />
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute', top: -2, right: -2,
            background: 'var(--status-critical)', color: '#fff',
            fontSize: '0.6rem', fontWeight: 700,
            width: 16, height: 16, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 98 }}
            onClick={() => setOpen(false)}
          />
          <div
            className="glass-panel"
            style={{
              position: 'absolute', top: '100%', right: 0, marginTop: '0.5rem',
              width: 340, maxHeight: 420, overflowY: 'auto', zIndex: 99,
              padding: 0, borderRadius: 'var(--radius-md)',
              boxShadow: '0 12px 40px rgba(0,0,0,0.3)',
            }}
          >
            <div style={{
              padding: '0.75rem 1rem', borderBottom: '1px solid var(--border-color)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Notifications</span>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <span style={{
                  fontSize: '0.7rem', color: isConnected ? 'var(--status-safe)' : 'var(--text-tertiary)',
                  display: 'flex', alignItems: 'center', gap: '0.25rem',
                }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: isConnected ? 'var(--status-safe)' : 'var(--text-tertiary)',
                  }} />
                  {isConnected ? 'Live' : 'Offline'}
                </span>
                {notifications.length > 0 && (
                  <button
                    onClick={clearAll}
                    style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', fontSize: '0.75rem' }}
                  >
                    Clear all
                  </button>
                )}
              </div>
            </div>

            {notifications.length === 0 ? (
              <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>
                No notifications yet
              </div>
            ) : (
              notifications.slice(0, 20).map((n) => (
                <div
                  key={n.id}
                  style={{
                    padding: '0.6rem 1rem', borderBottom: '1px solid var(--border-color)',
                    display: 'flex', gap: '0.6rem', alignItems: 'flex-start',
                    cursor: n.reportId ? 'pointer' : 'default',
                    transition: 'background 0.15s',
                  }}
                  onClick={() => {
                    if (n.reportId) {
                      router.push(`/report/${n.reportId}`);
                      setOpen(false);
                    }
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(15,23,42,0.03)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  {n.type === 'success' && <CheckCircle size={15} style={{ color: 'var(--status-safe)', flexShrink: 0, marginTop: 2 }} />}
                  {n.type === 'error' && <AlertTriangle size={15} style={{ color: 'var(--status-high)', flexShrink: 0, marginTop: 2 }} />}
                  {n.type === 'info' && <Loader2 size={15} style={{ color: 'var(--accent-primary)', flexShrink: 0, marginTop: 2 }} />}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: '0.82rem', marginBottom: '0.15rem' }}>{n.title}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>{n.message}</div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', marginTop: '0.25rem' }}>
                      {n.timestamp.toLocaleTimeString()}
                    </div>
                  </div>
                  {n.reportId && <ExternalLink size={12} style={{ color: 'var(--text-tertiary)', flexShrink: 0, marginTop: 4 }} />}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default NotificationProvider;
