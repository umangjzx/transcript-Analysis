/**
 * CommandPalette — Ctrl+K quick search and navigation.
 *
 * Provides fuzzy search across reports and quick actions.
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  Search, FileAudio, BarChart2, HardDrive, UploadCloud,
  ArrowRight, Command, Hash,
} from 'lucide-react';

const ACTIONS = [
  { id: 'dashboard', label: 'Go to Dashboard', icon: BarChart2, path: '/' },
  { id: 'upload', label: 'Analyze New File', icon: UploadCloud, path: '/upload' },
  { id: 'drive', label: 'Google Drive', icon: HardDrive, path: '/google-drive' },
];

const CommandPalette = ({ open, onClose, reports = [] }) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // Reset on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Filter results
  const results = useMemo(() => {
    const q = query.toLowerCase().trim();
    const items = [];

    // Actions
    const matchedActions = ACTIONS.filter((a) =>
      !q || a.label.toLowerCase().includes(q)
    ).map((a) => ({ type: 'action', ...a }));
    items.push(...matchedActions);

    // Reports
    if (reports.length > 0) {
      const matchedReports = reports
        .filter((r) => !q || (r.filename || '').toLowerCase().includes(q) || String(r.id).includes(q))
        .slice(0, 8)
        .map((r) => ({
          type: 'report',
          id: r.id,
          label: r.filename || `Report #${r.id}`,
          sublabel: `#${r.id} · ${r.severity || 'Unknown'} · Score ${r.risk_score?.toFixed(0) || '—'}`,
          icon: FileAudio,
          path: `/report/${r.id}`,
        }));
      items.push(...matchedReports);
    }

    return items;
  }, [query, reports]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;

    const handleKey = (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const item = results[selectedIndex];
        if (item?.path) {
          navigate(item.path);
          onClose();
        }
      } else if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, results, selectedIndex, navigate, onClose]);

  // Reset selection when query changes
  useEffect(() => setSelectedIndex(0), [query]);

  if (!open) return null;

  return createPortal(
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        paddingTop: '15vh',
      }}
      onClick={onClose}
    >
      <div
        className="glass-panel"
        style={{
          width: '100%', maxWidth: 560,
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          padding: '0.875rem 1.25rem',
          borderBottom: '1px solid var(--border-color)',
        }}>
          <Search size={18} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search reports, navigate..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              flex: 1, background: 'transparent', border: 'none',
              color: 'var(--text-primary)', fontSize: '1rem',
              outline: 'none', fontFamily: 'inherit',
            }}
          />
          <kbd style={{
            fontSize: '0.7rem', padding: '0.15rem 0.4rem',
            background: 'var(--bg-tertiary)', borderRadius: 4,
            color: 'var(--text-tertiary)', border: '1px solid var(--border-color)',
          }}>
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div style={{ maxHeight: 360, overflowY: 'auto', padding: '0.5rem' }}>
          {results.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.9rem' }}>
              No results found
            </div>
          ) : (
            results.map((item, i) => {
              const Icon = item.icon;
              const isSelected = i === selectedIndex;
              return (
                <div
                  key={item.id || i}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.75rem',
                    padding: '0.6rem 0.875rem',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                    background: isSelected ? 'rgba(56, 189, 248, 0.08)' : 'transparent',
                    border: isSelected ? '1px solid rgba(56, 189, 248, 0.2)' : '1px solid transparent',
                    transition: 'all 0.1s',
                  }}
                  onClick={() => { navigate(item.path); onClose(); }}
                  onMouseEnter={() => setSelectedIndex(i)}
                >
                  <Icon size={16} style={{ color: isSelected ? 'var(--accent-primary)' : 'var(--text-tertiary)', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '0.9rem', fontWeight: 500,
                      color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {item.label}
                    </div>
                    {item.sublabel && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: '0.1rem' }}>
                        {item.sublabel}
                      </div>
                    )}
                  </div>
                  {isSelected && <ArrowRight size={14} style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />}
                </div>
              );
            })
          )}
        </div>

        {/* Footer hints */}
        <div style={{
          padding: '0.5rem 1rem', borderTop: '1px solid var(--border-color)',
          display: 'flex', gap: '1rem', fontSize: '0.7rem', color: 'var(--text-tertiary)',
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <kbd style={{ padding: '0.1rem 0.3rem', background: 'var(--bg-tertiary)', borderRadius: 3, border: '1px solid var(--border-color)' }}>↑↓</kbd>
            Navigate
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <kbd style={{ padding: '0.1rem 0.3rem', background: 'var(--bg-tertiary)', borderRadius: 3, border: '1px solid var(--border-color)' }}>↵</kbd>
            Open
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <kbd style={{ padding: '0.1rem 0.3rem', background: 'var(--bg-tertiary)', borderRadius: 3, border: '1px solid var(--border-color)' }}>N</kbd>
            New Analysis
          </span>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default CommandPalette;
