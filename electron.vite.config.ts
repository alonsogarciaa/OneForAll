import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'

const CSP =
  "default-src 'self'; script-src 'self'; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*; " +
  "img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:"

// Dev server needs inline scripts for React refresh, so the CSP is only added to the production build.
const cspPlugin = (): Plugin => ({
  name: 'oneforall-csp',
  apply: 'build',
  transformIndexHtml: (html) =>
    html.replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`)
})

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { rollupOptions: { input: { index: resolve(__dirname, 'app/main/index.ts') } } }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: { rollupOptions: { input: { index: resolve(__dirname, 'app/preload/index.ts') } } }
  },
  renderer: {
    root: resolve(__dirname, 'ui'),
    plugins: [react(), cspPlugin()],
    build: { rollupOptions: { input: { index: resolve(__dirname, 'ui/index.html') } } }
  }
})
