import React from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom';
import { Shield, Home, UploadCloud, LogOut, HardDrive } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Report from './pages/Report';
import Login from './pages/Login';
import GoogleDrive from './pages/GoogleDrive';
import ErrorBoundary from './components/ErrorBoundary';
import { getToken, getStoredUser, logout } from './api';
import { Toaster } from 'react-hot-toast';
import './App.css';

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
            <div className="app-container">
              <Navigation />
              <main className="main-content">
                <ErrorBoundary>
                  <Routes>
                    <Route path="/"              element={<Dashboard />} />
                    <Route path="/upload"        element={<Upload />} />
                    <Route path="/report/:id"    element={<Report />} />
                    <Route path="/google-drive"  element={<GoogleDrive />} />
                  </Routes>
                </ErrorBoundary>
              </main>
            </div>
          </ProtectedRoute>
        } />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
