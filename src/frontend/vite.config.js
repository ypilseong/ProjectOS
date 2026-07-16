import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendPort = process.env.BACKEND_PORT || '14006'
const backendUrl = process.env.VITE_BACKEND_URL || process.env.BACKEND_URL || `http://localhost:${backendPort}`

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': backendUrl,
      '/health': backendUrl,
    }
  }
})
