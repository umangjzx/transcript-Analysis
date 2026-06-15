/** @type {import('next').NextConfig} */

// Backend origin — where FastAPI is running.
// In the standalone app this proxies the same paths the original dev server did.
// When integrating into the live platform, point this at your FastAPI gateway.
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',

  // Allow large file uploads through rewrites proxy (audio 300MB, video 500MB)
  experimental: {
    middlewareClientMaxBodySize: '500mb',
    serverActions: {
      bodySizeLimit: '500mb',
    },
  },

  async rewrites() {
    return [
      // Google Drive — full /api/v1/google-drive prefix preserved on the backend
      {
        source: '/api/v1/google-drive/:path*',
        destination: `${BACKEND_URL}/api/v1/google-drive/:path*`,
      },
      // Analytics — full /api/v1/analytics prefix preserved on the backend
      {
        source: '/api/v1/analytics/:path*',
        destination: `${BACKEND_URL}/api/v1/analytics/:path*`,
      },
      // Chat — full /api/v1/chat prefix preserved on the backend
      {
        source: '/api/v1/chat',
        destination: `${BACKEND_URL}/api/v1/chat`,
      },
      // Notifications — full /api/v1/notify prefix preserved
      {
        source: '/api/v1/notify/:path*',
        destination: `${BACKEND_URL}/api/v1/notify/:path*`,
      },
      // All other /api/v1/* — strip the /api/v1 prefix (e.g. /api/v1/analyze -> /analyze)
      {
        source: '/api/v1/:path*',
        destination: `${BACKEND_URL}/:path*`,
      },
      // Auth routes live on the root backend (no /api/v1 prefix)
      {
        source: '/auth/:path*',
        destination: `${BACKEND_URL}/auth/:path*`,
      },
    ];
  },
};

export default nextConfig;
