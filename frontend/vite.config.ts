import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the UI runs on :5173 and forwards /api calls to FastAPI on :8000.
// In production FastAPI serves the built files itself, so the UI and API share one origin.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
