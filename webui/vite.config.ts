import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import fs from 'fs'
import http from 'http'
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
      // Fix incorrect package.json entry points for vue-office (Vue 3 only)
      '@vue-office/docx': fileURLToPath(new URL('./node_modules/@vue-office/docx/lib/v3/index.js', import.meta.url)),
      '@vue-office/excel': fileURLToPath(new URL('./node_modules/@vue-office/excel/lib/v3/index.js', import.meta.url)),
      // Fix CSS imports for vue-office
      '@vue-office/docx/lib': fileURLToPath(new URL('./node_modules/@vue-office/docx/lib', import.meta.url)),
      '@vue-office/excel/lib': fileURLToPath(new URL('./node_modules/@vue-office/excel/lib', import.meta.url)),
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
    include: [
      '@vue-office/docx',
      '@vue-office/excel',
    ],
  },
  publicDir: 'public',
  server: {
    host: '0.0.0.0',
    port: 8460,
    strictPort: true,
    // 修复 HMR WebSocket 端口冲突
    hmr: {
      // 使用独立的 HMR 端口，避免与主服务器冲突
      port: 24678,
      protocol: 'ws',
      overlay: true,
      clientPort: 24678,
      // 设置超时避免连接挂起
      timeout: 30000,
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
          try {
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
            } else {
              console.warn(`[Vite Middleware] File not found: ${filePath}`)
            }
          } catch (error) {
            console.error('[Vite Middleware] Error serving file:', error)
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
        },
        // Log proxy requests for debugging
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('[Vite Proxy] Forwarding:', req.method, req.url, '→', options.target + proxyReq.path);
          });
        }
      },
      '/ws': {
        target: 'http://127.0.0.1:8465',
        changeOrigin: true,
        secure: false,
        ws: true,
        agent: new http.Agent({
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
        timeout: 30000,
        // Log proxy requests for debugging
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('[Vite Proxy WS] Forwarding:', req.url, '→', options.target + proxyReq.path);
          });
        }
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
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      external: [
        '@tauri-apps/api',
        '@tauri-apps/plugin-clipboard-manager',
      ],
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/vue') || id.includes('node_modules/@vue')) {
            return 'vue-vendor';
          }
          if (id.includes('node_modules/vue-router') || id.includes('node_modules/pinia')) {
            return 'vue-framework';
          }
          if (id.includes('node_modules/element-plus')) {
            return 'element-plus';
          }
          if (id.includes('node_modules/codemirror') || id.includes('node_modules/@codemirror')) {
            return 'editor';
          }
          if (id.includes('node_modules/@lezer')) {
            return 'editor-parser';
          }
          if (id.includes('node_modules/axios')) {
            return 'http';
          }
          if (id.includes('node_modules/marked') || id.includes('node_modules/markdown-it')) {
            return 'markdown';
          }
          if (id.includes('node_modules/papaparse')) {
            return 'csv';
          }
          if (id.includes('node_modules/echarts')) {
            return 'charts';
          }
          if (id.includes('node_modules/vditor')) {
            return 'vditor';
          }
          if (id.includes('node_modules/dayjs')) {
            return 'date';
          }
          if (id.includes('node_modules/js-yaml')) {
            return 'yaml';
          }
          if (id.includes('node_modules/zod')) {
            return 'validation';
          }
          if (id.includes('node_modules/uuid')) {
            return 'uuid';
          }
          if (id.includes('node_modules/@vueuse/core')) {
            return 'vueuse';
          }
          if (id.includes('node_modules/vue-web-terminal')) {
            return 'terminal';
          }
          if (id.includes('node_modules/@lljj/vue3-form-element')) {
            return 'form';
          }
          if (id.includes('node_modules/@element-plus/icons-vue') ||
              id.includes('node_modules/@heroicons/vue')) {
            return 'icons';
          }
        },
      },
    },
  },
  clearScreen: false,
})