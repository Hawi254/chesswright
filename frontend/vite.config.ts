import path from 'path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // react-plotly.js's published ESM build (dist/index.mjs) does
      // `import Plotly from "plotly.js/dist/plotly"` with no extension --
      // valid for CJS require() (which auto-appends .js) but invalid
      // under strict ESM resolution, so Vite/Vitest fail to resolve it
      // ("Cannot find module ... Did you mean plotly.js/dist/plotly.js?").
      // The CJS build (dist/index.cjs) doesn't have this bug; Vite bundles
      // CJS deps transparently either way.
      'react-plotly.js': path.resolve(__dirname, 'node_modules/react-plotly.js/dist/index.cjs'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
})
