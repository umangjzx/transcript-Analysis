/**
 * useKeyboardShortcuts — Global keyboard shortcuts for the app.
 *
 * Shortcuts:
 * - Ctrl+K / Cmd+K → Focus search / open command palette
 * - N (when not in input) → Navigate to new analysis
 * - Esc → Close modals/chat
 * - Arrow keys → Navigate table rows (when table is focused)
 */

import { useEffect, useCallback } from 'react';

/**
 * @param {Object} handlers - Map of action names to handler functions
 * @param {Function} handlers.onSearch - Ctrl+K handler
 * @param {Function} handlers.onNewAnalysis - N key handler
 * @param {Function} handlers.onEscape - Esc handler
 * @param {Function} handlers.onArrowUp - Arrow up handler
 * @param {Function} handlers.onArrowDown - Arrow down handler
 * @param {boolean} enabled - Whether shortcuts are active (default true)
 */
export function useKeyboardShortcuts(handlers = {}, enabled = true) {
  const handleKeyDown = useCallback((e) => {
    if (!enabled) return;

    const target = e.target;
    const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable;

    // Ctrl+K / Cmd+K → Search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      handlers.onSearch?.();
      return;
    }

    // Escape → Close modals/chat
    if (e.key === 'Escape') {
      handlers.onEscape?.();
      return;
    }

    // Skip remaining shortcuts if user is typing in an input
    if (isInput) return;

    // N → New analysis
    if (e.key === 'n' || e.key === 'N') {
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        handlers.onNewAnalysis?.();
        return;
      }
    }

    // Arrow keys → Table navigation
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

    // Enter → Open selected row
    if (e.key === 'Enter') {
      handlers.onEnter?.();
      return;
    }

    // Delete/Backspace → Delete selected
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (!isInput) {
        handlers.onDelete?.();
        return;
      }
    }

    // Ctrl+A / Cmd+A → Select all (when not in input)
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
