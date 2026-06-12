import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8788',
      '/v1': 'http://localhost:8788',
      '/shims': 'http://localhost:8788',
      '/install.sh': 'http://localhost:8788',
      '/healthz': 'http://localhost:8788',
      '/llms.txt': 'http://localhost:8788',
      '/robots.txt': 'http://localhost:8788',
    },
  },
})
