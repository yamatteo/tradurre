import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  build: {
    // Built straight into the Python package so the wheel can ship the SPA
    // (see [tool.hatch.build] in pyproject.toml and tradurre/app.py).
    outDir: '../tradurre/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.TRADURRE_API ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
