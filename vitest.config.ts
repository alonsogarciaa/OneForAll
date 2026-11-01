import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    include: ['app/**/*.test.ts', 'ui/src/**/*.test.{ts,tsx}'],
    environment: 'node',
    environmentMatchGlobs: [['ui/**', 'jsdom']],
    setupFiles: ['ui/src/test/setup.ts']
  }
})
