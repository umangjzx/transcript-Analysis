/**
 * useWebSocket — Real-time WebSocket connection to backend progress events.
 *
 * Connects to ws://localhost:8000/ws/progress and dispatches events:
 * - analysis:started
 * - analysis:progress
 * - analysis:completed
 * - analysis:failed
 *
 * Usage:
 *   const { lastEvent, isConnected, subscribe } = useWebSocket();
 */

import { useEffect, useRef, useState, useCallback } from 'react';

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/progress`;

// Reconnection config
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const RECONNECT_FACTOR = 1.5;

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const reconnectDelay = useRef(RECONNECT_BASE_MS);
  const listenersRef = useRef(new Set());
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
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
          // Notify all registered listeners
          listenersRef.current.forEach((fn) => {
            try { fn(parsed); } catch (e) { /* ignore listener errors */ }
          });
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        // Schedule reconnect with exponential backoff
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(
            reconnectDelay.current * RECONNECT_FACTOR,
            RECONNECT_MAX_MS
          );
          connect();
        }, reconnectDelay.current);
      };

      ws.onerror = () => {
        // onclose will fire after onerror, triggering reconnect
        ws.close();
      };
    } catch {
      // Connection failed, retry
      reconnectTimer.current = setTimeout(connect, reconnectDelay.current);
    }
  }, []);

  // Subscribe to a specific report ID
  const subscribe = useCallback((reportId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ subscribe: reportId }));
    }
  }, []);

  // Register an event listener callback
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
