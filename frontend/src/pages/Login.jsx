import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { login, getToken } from '../api';

const Login = () => {
  const [username, setUsername]     = useState('');
  const [password, setPassword]     = useState('');
  const [showPass, setShowPass]     = useState(false);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState('');
  const navigate = useNavigate();

  // Already logged in → go straight to dashboard
  useEffect(() => {
    if (getToken()) navigate('/', { replace: true });
  }, [navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }

    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 401) {
        setError('Invalid username or password.');
      } else if (typeof detail === 'string') {
        setError(detail);
      } else {
        setError('Could not connect to the server. Make sure the backend is running.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="glass-panel auth-card animate-fade-in">

        {/* Header */}
        <div className="auth-header">
          <div className="flex-center" style={{ marginBottom: '0.75rem' }}>
            <img
              src="/unnamed.png"
              alt="Melody Wings Safety"
              style={{ height: '56px', width: 'auto' }}
            />
          </div>
          <h1 className="heading-2 text-gradient auth-title">Melody Wings Safety</h1>
          <p className="text-secondary" style={{ marginTop: '0.4rem' }}>Sign in to access your dashboard</p>
        </div>

        {/* Error */}
        {error && (
          <div className="auth-error animate-fade-in" style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem',
          }}>
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleLogin} className="auth-form">

          {/* Username */}
          <div className="auth-input-group">
            <label className="auth-label" htmlFor="username">Username</label>
            <div style={{ position: 'relative' }}>
              <User
                size={16}
                style={{
                  position: 'absolute', left: '0.75rem',
                  top: '50%', transform: 'translateY(-50%)',
                  color: 'var(--text-tertiary)', pointerEvents: 'none',
                }}
              />
              <input
                id="username"
                type="text"
                className="auth-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                disabled={loading}
                required
                style={{ paddingLeft: '2.25rem' }}
              />
            </div>
          </div>

          {/* Password */}
          <div className="auth-input-group">
            <label className="auth-label" htmlFor="password">Password</label>
            <div style={{ position: 'relative' }}>
              <Lock
                size={16}
                style={{
                  position: 'absolute', left: '0.75rem',
                  top: '50%', transform: 'translateY(-50%)',
                  color: 'var(--text-tertiary)', pointerEvents: 'none',
                }}
              />
              <input
                id="password"
                type={showPass ? 'text' : 'password'}
                className="auth-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                disabled={loading}
                required
                style={{ paddingLeft: '2.25rem', paddingRight: '2.75rem' }}
              />
              <button
                type="button"
                onClick={() => setShowPass((v) => !v)}
                tabIndex={-1}
                style={{
                  position: 'absolute', right: '0.75rem',
                  top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none',
                  color: 'var(--text-tertiary)', cursor: 'pointer',
                  padding: 0, display: 'flex',
                }}
                aria-label={showPass ? 'Hide password' : 'Show password'}
              >
                {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="btn btn-primary auth-btn"
            disabled={loading}
            style={{ marginTop: '0.5rem' }}
          >
            {loading ? (
              <>
                <span style={{
                  width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: '#fff', borderRadius: '50%',
                  display: 'inline-block', animation: 'spin 0.7s linear infinite',
                }} />
                Signing in…
              </>
            ) : (
              <><Lock size={16} /> Sign in</>
            )}
          </button>
        </form>
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        .auth-input:disabled { opacity: 0.6; cursor: not-allowed; }
      `}</style>
    </div>
  );
};

export default Login;
