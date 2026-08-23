import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Single-origin by design (ADR-0006): in dev, Vite only fronts the app for
// HMR and proxies API calls to FastAPI — it's never a permanent second
// origin, so no CORS middleware is added on the backend.
const API_PATHS = ['/auth', '/verify', '/evidence-card', '/explain', '/search', '/skills']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((path) => [path, { target: 'http://localhost:8000', changeOrigin: true }]),
    ),
  },
})
