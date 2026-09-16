import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { host: '127.0.0.1', port: 5180, strictPort: true, proxy: {
    '/api': 'http://127.0.0.1:8010', '/auth': 'http://127.0.0.1:8010', '/users': 'http://127.0.0.1:8010',
  } },
})
