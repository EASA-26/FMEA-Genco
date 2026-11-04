import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The FastAPI backend serves the built app from frontend/dist, so the base is "/".
// During development every /api call is proxied to the local backend, which keeps
// the session cookie same-origin exactly as in production.
const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: false,
  },
};

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
});
