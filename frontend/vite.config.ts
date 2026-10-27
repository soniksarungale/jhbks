import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  build: {
    // The echarts chunk is ~600 kB minified (~190 kB gzipped) even tree-shaken.
    chunkSizeWarningLimit: 700,
    rolldownOptions: {
      output: {
        // ECharts is most of the bundle and changes far less often than app code.
        codeSplitting: {
          groups: [{ name: 'echarts', test: /node_modules[\\/](echarts|zrender)[\\/]/ }],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://127.0.0.1:4600',
    },
  },
  test: {
    environment: 'node',
  },
})
