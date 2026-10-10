import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

// The engine (engine/api/server.py) serves the API at its root; the app calls it under /api.
const ENGINE = process.env.MIRAGE_API ?? 'http://localhost:8000'
const CHAT = process.env.MIRAGE_CHAT_API ?? 'http://localhost:8001'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    proxy: {
      '/chat': { target: CHAT, changeOrigin: true },
      '/api': { target: ENGINE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
