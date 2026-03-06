import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import fs from 'fs'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: 'auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: 'components.d.ts',
    }),
  ],
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@tauri-apps/plugin-clipboard-manager': fileURLToPath(new URL('./src/stubs/tauri-clipboard-stub.ts', import.meta.url)),
    },
  },
  define: {
    __TAURI__: JSON.stringify(false),
  },
  optimizeDeps: {
    exclude: [
      '@tauri-apps/api',
      '@tauri-apps/plugin-clipboard-manager',
    ],
  },
  publicDir: 'public',
  server: {
    host: '0.0.0.0',
    port: 8460,
    strictPort: true,
    hmr: {
      port: 8460,
      protocol: 'ws',
      overlay: true,
      clientPort: 8460,
    },
    headers: {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    fs: {
      strict: false,
      allow: [
        process.cwd(),
      ],
    },
    middlewares: (config, { app }) => {
      // Serve drawio files directly without Vue Router interception
      app.use((req, res, next) => {
        if (req.url?.startsWith('/drawio/')) {
          const filePath = path.join(process.cwd(), 'public', req.url)
          const ext = path.extname(filePath)
          const contentTypes: Record<string, string> = {
            '.html': 'text/html',
            '.js': 'text/javascript',
            '.css': 'text/css',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
            '.eot': 'application/vnd.ms-fontobject',
          }

          const contentType = contentTypes[ext] || 'application/octet-stream'

          if (fs.existsSync(filePath)) {
            const content = fs.readFileSync(filePath)
            res.setHeader('Content-Type', contentType)
            res.setHeader('Cache-Control', 'no-cache')
            res.end(content)
            return
          }
        }
        next()
      })
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8465',
        changeOrigin: true,
        secure: false,
        ws: true,
        onError(err, req, res) {
          if (err.code === 'EPIPE' || err.code === 'ECONNRESET') {
            console.log('Proxy connection closed by client')
            return
          }
          console.error('Proxy error:', err)
        }
      },
      '/ws': {
        target: 'http://127.0.0.1:8465',
        changeOrigin: true,
        secure: false,
        ws: true,
        agent: new (require('http')).Agent({
          keepAlive: true,
          keepAliveMsecs: 1000,
          maxSockets: 256,
          maxFreeSockets: 256
        }),
        onError(err, req, res) {
          if (err.code === 'EPIPE' || err.code === 'ECONNRESET') {
            console.log('WebSocket connection closed by client')
            return
          }
          console.error('WebSocket proxy error:', err)
        },
        proxyTimeout: 30000,
        timeout: 30000
      }
    },
    watch: {
      usePolling: true,
      interval: 1000,
      ignored: [
        '**/src-tauri/**',
        '**/node_modules/**',
        '**/.git/**'
      ]
    }
  },
  build: {
    outDir: 'src-tauri/resources',
    emptyOutDir: false,
    minify: 'terser',
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      external: [
        '@tauri-apps/api',
        '@tauri-apps/plugin-clipboard-manager',
      ],
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/vue') || id.includes('node_modules/@vue') ||
              id.includes('node_modules/vue-router') || id.includes('node_modules/pinia')) {
            return 'vendor';
          }
          if (id.includes('node_modules/element-plus')) {
            return 'element-plus';
          }
          if (id.includes('node_modules/codemirror') || id.includes('node_modules/@codemirror')) {
            return 'editor';
          }
          if (id.includes('node_modules/axios') || id.includes('node_modules/marked') ||
              id.includes('node_modules/papaparse')) {
            return 'utils';
          }
        },
      },
    },
  },
  clearScreen: false,
})