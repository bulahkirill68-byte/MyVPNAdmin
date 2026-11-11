import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwind from '@tailwindcss/vite'
export default defineConfig({
  plugins: [vue(), tailwind()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          chart: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
          vue: ['vue'],
        },
      },
    },
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/sub': 'http://127.0.0.1:8000' } },
})
