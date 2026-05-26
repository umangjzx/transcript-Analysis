import React from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom';
import { Shield, Home, UploadCloud, Settings, Bell, LogOut } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Report from './pages/Report';
import Login from './pages/Login';
import ErrorBoundary from './components/ErrorBoundary';
import './App.css';

const Navigation = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const isActive = (path) => location.pathname === path ? 'active' : '';

  const handleLogout = () => {
    localStorage.removeItem('isAuthenticated');
    navigate('/login');
  };

  return (
    <nav className="navbar glass-panel animate-slide-up" style={{ animationName: 'slideDownFade' }}>
      <div className="navbar-brand">
        <Shield className="brand-icon" size={28} />
        <span className="brand-text text-gradient heading-3">AuraSafety</span>
      </div>
      <div className="navbar-links">
        <Link to="/" className={`nav-link ${isActive('/')}`}>
          <Home size={18} /> Dashboard
        </Link>
        <Link to="/upload" className={`nav-link ${isActive('/upload')}`}>
          <UploadCloud size={18} /> Analyze Audio
        </Link>
      </div>
      <div className="navbar-actions">
        <button className="btn-icon"><Bell size={20} /></button>
        <button className="btn-icon" onClick={handleLogout} title="Logout"><LogOut size={20} /></button>
        <div className="avatar">AD</div>
      </div>
    </nav>
  );
};

const ProtectedRoute = ({ children }) => {
  const isAuthenticated = localStorage.getItem('isAuthenticated') === 'true';
  return isAuthenticated ? children : <Navigate to="/login" replace />;
};

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={
          <ProtectedRoute>
            <div className="app-container">
              <Navigation />
              <main className="main-content">
                <ErrorBoundary>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/upload" element={<Upload />} />
                    <Route path="/report/:id" element={<Report />} />
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
