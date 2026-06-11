'use client';

import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * React error boundary — catches render errors in child components and
 * shows a friendly fallback instead of a blank/crashed page.
 * (Unchanged from the original; 'use client' added for Next.js.)
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            gap: '1.5rem',
            padding: '2rem',
            textAlign: 'center',
          }}
        >
          <AlertTriangle size={48} style={{ color: 'var(--status-high, #ef4444)' }} />
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary, #f1f5f9)' }}>
            Something went wrong
          </h2>
          <p style={{ color: 'var(--text-secondary, #94a3b8)', maxWidth: 480 }}>
            {this.state.error?.message || 'An unexpected error occurred while rendering this page.'}
          </p>
          <button
            className="btn btn-primary"
            onClick={() => {
              this.setState({ hasError: false, error: null });
              if (typeof window !== 'undefined') window.location.reload();
            }}
          >
            <RefreshCw size={16} /> Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
