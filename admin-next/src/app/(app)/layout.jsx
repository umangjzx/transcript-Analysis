'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Home, UploadCloud, LogOut, HardDrive, GitCompare, BarChart2 } from 'lucide-react';
import ErrorBoundary from '@/components/ErrorBoundary';
import { NotificationProvider, NotificationBell } from '@/components/NotificationProvider';
import CommandPalette from '@/components/CommandPalette';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { getToken, getStoredUser, logout } from '@/lib/api';
import { useDataStore, useDataStoreInit } from '@/store/dataStore';

// ── Navigation bar ────────────────────────────────────────────────────────────

const Navigation = () => {
  const pathname = usePathname();
  const router = useRouter();
  const isActive = (path) => (pathname === path ? 'active' : '');
  const user = getStoredUser();

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <nav className="navbar glass-panel animate-slide-up" style={{ animationName: 'slideDownFade' }}>
      <div className="navbar-brand">
        <img src="/unnamed.png" alt="MelodyWings" className="brand-logo" style={{ height: '32px', width: 'auto', marginRight: '8px' }} />
        <span className="brand-text heading-3" style={{ color: 'var(--text-primary)', fontWeight: '700' }}>Melody Wings Safety</span>
      </div>

      <div className="navbar-links">
        <Link href="/" className={`nav-link ${isActive('/')}`}>
          <Home size={18} /> Dashboard
        </Link>
        <Link href="/upload" className={`nav-link ${isActive('/upload')}`}>
          <UploadCloud size={18} /> Analyze Audio
        </Link>
        <Link href="/google-drive" className={`nav-link ${isActive('/google-drive')}`}>
          <HardDrive size={18} /> Google Drive
        </Link>
        <Link href="/analytics" className={`nav-link ${isActive('/analytics')}`}>
          <BarChart2 size={18} /> Analytics
        </Link>
        <Link href="/compare" className={`nav-link ${isActive('/compare')}`}>
          <GitCompare size={18} /> Compare
        </Link>
      </div>

      <div className="navbar-actions">
        {user?.username && (
          <span style={{
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
            padding: '0.25rem 0.6rem',
            background: 'rgba(15,23,42,0.06)',
            borderRadius: 'var(--radius-full)',
            border: '1px solid var(--border-color)',
          }}>
            {user.username}
          </span>
        )}

        <NotificationBell />

        <button className="btn-icon" onClick={handleLogout} title="Sign out" aria-label="Sign out">
          <LogOut size={20} />
        </button>

        <div className="avatar" title={user?.username || 'Admin'}>
          {(user?.username || 'AD').slice(0, 2).toUpperCase()}
        </div>
      </div>
    </nav>
  );
};

// ── App shell ───────────────────────────────────────────────────────────────

export default function AppLayout({ children }) {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);

  // Client-side auth guard (mirrors the original ProtectedRoute).
  // For server-enforced protection in the host app, add a middleware.ts
  // that checks the httpOnly `access_token` cookie — see README.
  useEffect(() => {
    if (!getToken()) {
      router.replace('/login');
    } else {
      setAuthChecked(true);
    }
  }, [router]);

  // Kick off shared data loading + background polling once.
  useDataStoreInit();

  const reports = useDataStore((s) => s.history);

  useKeyboardShortcuts({
    onSearch: () => setCmdPaletteOpen(true),
    onNewAnalysis: () => router.push('/upload'),
    onEscape: () => setCmdPaletteOpen(false),
  });

  if (!authChecked) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div className="spinner" style={{ width: 32, height: 32, border: '3px solid var(--border-color)', borderTopColor: 'var(--accent-primary)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <NotificationProvider>
      <div className="app-container">
        <Navigation />
        <main className="main-content">
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
      <CommandPalette
        open={cmdPaletteOpen}
        onClose={() => setCmdPaletteOpen(false)}
        reports={reports}
      />
    </NotificationProvider>
  );
}
