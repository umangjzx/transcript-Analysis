import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Lock } from 'lucide-react';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'adminMW' && password === 'admin@MW') {
      localStorage.setItem('isAuthenticated', 'true');
      navigate('/');
    } else {
      setError('Invalid username or password');
    }
  };

  return (
    <div className="auth-container">
      <div className="glass-panel auth-card animate-fade-in">
        <div className="auth-header">
          <div className="flex-center" style={{ marginBottom: '1rem' }}>
            <Shield className="brand-icon" size={48} />
          </div>
          <h1 className="heading-2 text-gradient auth-title">AuraSafety</h1>
          <p className="text-secondary">Sign in to access your dashboard</p>
        </div>

        {error && <div className="auth-error animate-fade-in">{error}</div>}

        <form onSubmit={handleLogin} className="auth-form">
          <div className="auth-input-group">
            <label className="auth-label" htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              className="auth-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              required
            />
          </div>

          <div className="auth-input-group">
            <label className="auth-label" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
            />
          </div>

          <button type="submit" className="btn btn-primary auth-btn">
            <Lock size={18} /> Login securely
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;
