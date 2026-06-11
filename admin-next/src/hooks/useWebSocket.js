'use client';

/**
 * useWebSocket — Real-time WebSocket connection to backend progress events.
 *
 * Next.js port notes:
 *   - The WS URL is resolved lazily inside connect() (not at module load) so the
 *     module is safe to import during SSR where `window` is undefined.
 *   - Set NEXT_PUBLIC_WS_URL to point at a backend on a different origin;
 *     otherwise it derives ws(s)://<current-host>/ws/progress.
 *
 * Events: analysis:started | analysis:progress | analysis:completed | analysis:failed
 */

import { useEffect, useRef, useState, useCallback } from 'react';

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const RECONNECT_FACTOR = 1.5;

function resolveWsUrl() {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  if (typeof window === 'undefined') return null;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/progress`;
}

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const reconnectDelay = useRef(RECONNECT_BASE_MS);
  const listenersRef = useRef(new Set());
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = resolveWsUrl();
    if (!url) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        reconnectDelay.current = RECONNECT_BASE_MS;
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data);
          setLastEvent(parsed);
          listenersRef.current.forEach((fn) => {
            try { fn(parsed); } catch { /* ignore listener errors */ }
          });
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(
            reconnectDelay.current * RECONNECT_FACTOR,
            RECONNECT_MAX_MS
          );
          connect();
        }, reconnectDelay.current);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimer.current = setTimeout(connect, reconnectDelay.current);
    }
  }, []);

  const subscribe = useCallback((reportId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ subscribe: reportId }));
    }
  }, []);

  const addListener = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected, lastEvent, subscribe, addListener };
}

export default useWebSocket;
