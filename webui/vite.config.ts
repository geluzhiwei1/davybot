import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

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
  // Use relative path for both Web and Tauri builds
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // Stub Tauri plugins for web development
      '@tauri-apps/plugin-clipboard-manager': fileURLToPath(new URL('./src/stubs/tauri-clipboard-stub.ts', import.meta.url)),
    },
  },
  // Define global constants for environment detection
  define: {
    __TAURI__: JSON.stringify(false), // Default to false, will be overridden by Tauri
  },
  // Externalize Tauri packages in web mode to prevent build errors
  // These are only available in Tauri context, not in browser
  optimizeDeps: {
    exclude: [
      '@tauri-apps/api',
      '@tauri-apps/plugin-clipboard-manager',
    ],
  },
  server: {
    // 监听所有接口以支持IPv4和IPv6访问
    host: '0.0.0.0', // 监听所有IPv4接口
    port: 8460, // 前端端口固定为 8460
    strictPort: true, // 严格端口模式：端口被占用时立即失败，不允许自动更改
    // HMR 配置
    hmr: {
      // Let Vite auto-detect the host - works better for local development
      // host: '10.168.1.122', // Hard-coded IP removed
      port: 8460, // HMR 端口固定为 8460
      protocol: 'ws',
      overlay: true,
      clientPort: 8460, // 客户端端口固定为 8460
    },
    // 添加缓存控制
    headers: {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8465',
        changeOrigin: true,
        secure: false,
        ws: true // 支持 WebSocket 代理
      },
      '/ws': {
        target: 'http://127.0.0.1:8465',
        changeOrigin: true,
        secure: false,
        ws: true // WebSocket 代理
      }
    },
    // Use polling to avoid ENOSPC errors with large projects
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
  // Ensure Tauri can find the build output
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // 生产环境移除console语句，提升性能
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        pure_funcs: ['console.log', 'console.info', 'console.debug', 'console.warn'],
      },
    },
    // Externalize Tauri packages for web builds
    // These are only available in Tauri context, not in browser
    rollupOptions: {
      external: [
        '@tauri-apps/api',
        '@tauri-apps/plugin-clipboard-manager',
      ],
    },
  },
  // Optimize for Tauri
  clearScreen: false,
})