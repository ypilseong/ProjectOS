import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendUrl = process.env.VITE_BACKEND_URL || 'http://localhost:8001'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': backendUrl,
      '/health': backendUrl,
    }
  }
})
