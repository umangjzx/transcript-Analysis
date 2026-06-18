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

// ── Mobile Top Bar (brand + user actions for small screens) ───────────────────

const MobileTopBar = ({ user, onLogout }) => (
  <div className="mobile-top-bar">
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <img src="/unnamed.png" alt="MelodyWings" style={{ height: '26px', width: 'auto' }} />
      <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)', fontFamily: 'Outfit, sans-serif' }}>
        Safety
      </span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <NotificationBell />
      <button className="btn-icon" onClick={onLogout} title="Sign out" aria-label="Sign out" style={{ padding: '0.4rem' }}>
        <LogOut size={18} />
      </button>
      <div className="avatar" title={user?.username || 'Admin'} style={{ width: 30, height: 30, fontSize: '0.75rem' }}>
        {(user?.username || 'AD').slice(0, 2).toUpperCase()}
      </div>
    </div>
  </div>
);

// ── Navigation bar ────────────────────────────────────────────────────────────

const Navigation = () => {
  const pathname = usePathname();
  const router = useRouter();
  const isActive = (path) => (pathname === path ? 'active' : '');
  const user = getStoredUser();

  // Detect when embedded in iframe (MW admin panel)
  const [isEmbedded, setIsEmbedded] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      setIsEmbedded(params.get('embed') === 'true' || window.self !== window.top);

      const checkMobile = () => setIsMobile(window.innerWidth <= 768);
      checkMobile();
      window.addEventListener('resize', checkMobile);
      return () => window.removeEventListener('resize', checkMobile);
    }
  }, []);

  // Compact embedded nav — just the page links, no branding/auth
  if (isEmbedded) {
    return (
      <nav className="navbar glass-panel" style={{ padding: '0.5rem 1.5rem', minHeight: 'auto' }}>
        <div className="navbar-links" style={{ gap: '0.25rem' }}>
          <Link href="/" className={`nav-link ${isActive('/')}`}>
            <Home size={16} /> Dashboard
          </Link>
          <Link href="/upload" className={`nav-link ${isActive('/upload')}`}>
            <UploadCloud size={16} /> Analyze
          </Link>
          <Link href="/google-drive" className={`nav-link ${isActive('/google-drive')}`}>
            <HardDrive size={16} /> Drive
          </Link>
          <Link href="/analytics" className={`nav-link ${isActive('/analytics')}`}>
            <BarChart2 size={16} /> Analytics
          </Link>
          <Link href="/compare" className={`nav-link ${isActive('/compare')}`}>
            <GitCompare size={16} /> Compare
          </Link>
        </div>
      </nav>
    );
  }

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <>
      {/* Mobile top bar — only visible on small screens */}
      {isMobile && <MobileTopBar user={user} onLogout={handleLogout} />}

      <nav className="navbar glass-panel animate-slide-up" style={{ animationName: 'slideDownFade' }}>
        <div className="navbar-brand">
          <img src="/unnamed.png" alt="MelodyWings" className="brand-logo" style={{ height: '32px', width: 'auto', marginRight: '8px' }} />
          <span className="brand-text heading-3" style={{ color: 'var(--text-primary)', fontWeight: '700' }}>Melody Wings Safety</span>
        </div>

        <div className="navbar-links">
          <Link href="/" className={`nav-link ${isActive('/')}`}>
            <Home size={isMobile ? 20 : 18} /> {isMobile ? 'Home' : 'Dashboard'}
          </Link>
          <Link href="/upload" className={`nav-link ${isActive('/upload')}`}>
            <UploadCloud size={isMobile ? 20 : 18} /> {isMobile ? 'Analyze' : 'Analyze Audio'}
          </Link>
          <Link href="/google-drive" className={`nav-link ${isActive('/google-drive')}`}>
            <HardDrive size={isMobile ? 20 : 18} /> Drive
          </Link>
          <Link href="/analytics" className={`nav-link ${isActive('/analytics')}`}>
            <BarChart2 size={isMobile ? 20 : 18} /> Analytics
          </Link>
          <Link href="/compare" className={`nav-link ${isActive('/compare')}`}>
            <GitCompare size={isMobile ? 20 : 18} /> Compare
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
    </>
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
