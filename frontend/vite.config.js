import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Disable Vite telemetry (prevents /collect 404s on the backend)
  analytics: false,
  server: {
    proxy: {
      // WebSocket for real-time progress updates
      '/ws': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      // Google Drive routes keep their full /api/v1/google-drive prefix on the backend
      '/api/v1/google-drive': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Analytics routes keep their full /api/v1/analytics prefix on the backend
      '/api/v1/analytics': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // All other /api/v1/* routes — strip the /api/v1 prefix
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/v1/, '')
      },
      // Auth routes live on the root backend (no /api/v1 prefix)
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
