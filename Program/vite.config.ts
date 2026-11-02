import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Port 5187 and backend 8795 keep Worldsmith clear of Dungeon (5177 and 8785), so both can run at once.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5187,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8795' },
  },
})
