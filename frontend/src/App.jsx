import React, { Suspense, lazy, useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom';
import { Home, UploadCloud, LogOut, HardDrive, GitCompare, BarChart2 } from 'lucide-react';
import Login from './pages/Login';
import ErrorBoundary from './components/ErrorBoundary';
import { NotificationProvider, NotificationBell } from './components/NotificationProvider';
import CommandPalette from './components/CommandPalette';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { getToken, getStoredUser, logout, getHistory } from './api';
import { Toaster } from 'react-hot-toast';
import './App.css';

// ── Lazy-loaded page components ───────────────────────────────────────────────
const Dashboard   = lazy(() => import('./pages/Dashboard'));
const Upload      = lazy(() => import('./pages/Upload'));
const Report      = lazy(() => import('./pages/Report'));
const GoogleDrive = lazy(() => import('./pages/GoogleDrive'));
const Compare     = lazy(() => import('./pages/Compare'));
const Analytics   = lazy(() => import('./pages/Analytics'));

// ── Loading fallback ──────────────────────────────────────────────────────────
const PageLoader = () => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
    <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
      <div className="spinner" style={{ width: 32, height: 32, border: '3px solid var(--border-color)', borderTopColor: 'var(--accent-primary)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 1rem' }} />
      <p>Loading...</p>
    </div>
  </div>
);

// ── Navigation bar ────────────────────────────────────────────────────────────

const Navigation = () => {
  const location = useLocation();
  const navigate  = useNavigate();
  const isActive  = (path) => location.pathname === path ? 'active' : '';
  const user      = getStoredUser();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <nav className="navbar glass-panel animate-slide-up" style={{ animationName: 'slideDownFade' }}>
      <div className="navbar-brand">
        <img src="/unnamed.png" alt="MelodyWings" className="brand-logo" style={{ height: '32px', width: 'auto', marginRight: '8px' }} />
        <span className="brand-text heading-3" style={{ color: 'var(--text-primary)', fontWeight: '700' }}>Melody Wings Safety</span>
      </div>

      <div className="navbar-links">
        <Link to="/" className={`nav-link ${isActive('/')}`}>
          <Home size={18} /> Dashboard
        </Link>
        <Link to="/upload" className={`nav-link ${isActive('/upload')}`}>
          <UploadCloud size={18} /> Analyze Audio
        </Link>
        <Link to="/google-drive" className={`nav-link ${isActive('/google-drive')}`}>
          <HardDrive size={18} /> Google Drive
        </Link>
        <Link to="/analytics" className={`nav-link ${isActive('/analytics')}`}>
          <BarChart2 size={18} /> Analytics
        </Link>
        <Link to="/compare" className={`nav-link ${isActive('/compare')}`}>
          <GitCompare size={18} /> Compare
        </Link>
      </div>

      <div className="navbar-actions">
        {/* Username badge */}
        {user?.username && (
          <span style={{
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
            padding: '0.25rem 0.6rem',
            background: 'rgba(255,255,255,0.06)',
            borderRadius: 'var(--radius-full)',
            border: '1px solid var(--border-color)',
          }}>
            {user.username}
          </span>
        )}

        {/* Notification Bell */}
        <NotificationBell />

        <button
          className="btn-icon"
          onClick={handleLogout}
          title="Sign out"
          aria-label="Sign out"
        >
          <LogOut size={20} />
        </button>

        {/* Avatar initials */}
        <div className="avatar" title={user?.username || 'Admin'}>
          {(user?.username || 'AD').slice(0, 2).toUpperCase()}
        </div>
      </div>
    </nav>
  );
};

// ── Protected route guard ─────────────────────────────────────────────────────

const ProtectedRoute = ({ children }) => {
  const token = getToken();
  return token ? children : <Navigate to="/login" replace />;
};

// ── App Shell with Keyboard Shortcuts ─────────────────────────────────────────

const AppShell = ({ children }) => {
  const navigate = useNavigate();
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);
  const [reports, setReports] = useState([]);

  // Load reports for command palette search
  const loadReports = useCallback(() => {
    getHistory(0, 100).then((data) => {
      setReports(Array.isArray(data) ? data : data?.reports || []);
    }).catch(() => {});
  }, []);

  // Load on mount
  React.useEffect(() => { loadReports(); }, [loadReports]);

  useKeyboardShortcuts({
    onSearch: () => setCmdPaletteOpen(true),
    onNewAnalysis: () => navigate('/upload'),
    onEscape: () => setCmdPaletteOpen(false),
  });

  return (
    <>
      {children}
      <CommandPalette
        open={cmdPaletteOpen}
        onClose={() => setCmdPaletteOpen(false)}
        reports={reports}
      />
    </>
  );
};

// ── App ───────────────────────────────────────────────────────────────────────

function App() {
  return (
    <BrowserRouter>
      <Toaster position="bottom-right" toastOptions={{ style: { background: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' } }} />
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />

        {/* Protected — everything else */}
        <Route path="*" element={
          <ProtectedRoute>
            <NotificationProvider>
              <AppShell>
                <div className="app-container">
                  <Navigation />
                  <main className="main-content">
                    <ErrorBoundary>
                      <Suspense fallback={<PageLoader />}>
                        <Routes>
                          <Route path="/"              element={<Dashboard />} />
                          <Route path="/upload"        element={<Upload />} />
                          <Route path="/report/:id"    element={<Report />} />
                          <Route path="/google-drive"  element={<GoogleDrive />} />
                          <Route path="/compare"       element={<Compare />} />
                          <Route path="/analytics"     element={<Analytics />} />
                        </Routes>
                      </Suspense>
                    </ErrorBoundary>
                  </main>
                </div>
              </AppShell>
            </NotificationProvider>
          </ProtectedRoute>
        } />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
