'use client';

/**
 * useKeyboardShortcuts — Global keyboard shortcuts for the app.
 * (Unchanged from the original; only the 'use client' directive added.)
 *
 * Shortcuts:
 * - Ctrl+K / Cmd+K → command palette
 * - N (when not in input) → new analysis
 * - Esc → close modals/chat
 * - Arrow keys → navigate table rows
 */

import { useEffect, useCallback } from 'react';

export function useKeyboardShortcuts(handlers = {}, enabled = true) {
  const handleKeyDown = useCallback((e) => {
    if (!enabled) return;

    const target = e.target;
    const isInput =
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT' ||
      target.isContentEditable;

    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      handlers.onSearch?.();
      return;
    }

    if (e.key === 'Escape') {
      handlers.onEscape?.();
      return;
    }

    if (isInput) return;

    if (e.key === 'n' || e.key === 'N') {
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        handlers.onNewAnalysis?.();
        return;
      }
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      handlers.onArrowUp?.();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      handlers.onArrowDown?.();
      return;
    }

    if (e.key === 'Enter') {
      handlers.onEnter?.();
      return;
    }

    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (!isInput) {
        handlers.onDelete?.();
        return;
      }
    }

    if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
      if (!isInput) {
        e.preventDefault();
        handlers.onSelectAll?.();
        return;
      }
    }
  }, [handlers, enabled]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

export default useKeyboardShortcuts;
