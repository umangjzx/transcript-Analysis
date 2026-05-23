import React from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Shield, Home, UploadCloud, Settings, Bell } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Report from './pages/Report';
import './App.css';

const Navigation = () => {
  const location = useLocation();
  const isActive = (path) => location.pathname === path ? 'active' : '';

  return (
    <nav className="navbar glass-panel">
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
        <button className="btn-icon"><Settings size={20} /></button>
        <div className="avatar">AD</div>
      </div>
    </nav>
  );
};

function App() {
  return (
    <BrowserRouter>
      <div className="app-container">
        <Navigation />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/report/:id" element={<Report />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
