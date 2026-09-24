// Web SPA config — plain client-side routing, no TanStack Start SSR.
// For Tauri desktop app, see vite.config.tauri.ts
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import tsConfigPaths from "vite-tsconfig-paths";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

/**
 * Dev middleware: serve index.html for all SPA routes so client-side routing works.
 * Default base path is /app-ui/ (formerly /legalbot-ui/).
 * Legacy /legalbot-ui/* requests are redirected to /app-ui/*.
 */
function spaDevIndex(): Plugin {
  return {
    name: "spa-dev-index",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split("?")[0] || "/";
        const base = server.config.base || "/";

        // --- Legacy redirect: /legalbot-ui/* -> /app-ui/* ---
        if (url === "/legalbot-ui" || url === "/legalbot-ui/" || url.startsWith("/legalbot-ui/")) {
          const newPath = url.replace("/legalbot-ui", "/app-ui");
          res.statusCode = 301;
          res.setHeader("Location", newPath);
          res.end();
          return;
        }

        // --- SPA fallback for base path (now /app-ui/) ---
        const urlWithoutBase =
          base !== "/" && url.startsWith(base) ? url.slice(base.length - 1) : url;
        if (
          urlWithoutBase.startsWith("/@") ||
          (urlWithoutBase !== "/" && /\.[a-zA-Z0-9]+$/.test(urlWithoutBase))
        ) {
          return next();
        }
        if (
          url.startsWith("/api") ||
          url.startsWith("/legalbot-api") ||
          url.startsWith("/sanctions") ||
          url.startsWith("/kb-searcher") ||
          url.startsWith("/nn-kb-searcher") ||
          url.startsWith("/normflow") ||
          url.startsWith("/ws")
        ) {
          return next();
        }
        const htmlContent = readFileSync(resolve(__dirname, "index.html"), "utf-8");
        server
          .transformIndexHtml(url, htmlContent)
          .then((transformed) => {
            res.statusCode = 200;
            res.setHeader("Content-Type", "text/html");
            res.end(transformed);
          })
          .catch(next);
      });
    },
  };
}

/**
 * Demo-only: downlevel built CSS for old Android WebViews (Chromium 92 —
 * Huawei/Honor 12.x) so the remotely-served demo works when loaded by
 * light-app Android / old-WebView browsers. Mirrors the mobile-build pass
 * in vite.config.tauri.ts; see scripts/mobile-css-downlevel.mjs.
 */
function demoCssDownlevel(): Plugin {
  return {
    name: "demo-css-downlevel",
    apply: "build",
    closeBundle() {
      const scriptUrl = pathToFileURL(resolve(__dirname, "scripts/mobile-css-downlevel.mjs")).href;
      void import(scriptUrl)
        .then(({ downlevelCssDir }) => downlevelCssDir(resolve(__dirname, "dist/assets")))
        .then((rs) => {
          for (const r of rs)
            console.log(`[demo-css] ${r.bytes ? "downleveled" : "skipped"} ${r.file}`);
        });
    },
  };
}

/**
 * Server 自包含构建(--mode server)品牌词:页面 <title> 与 PWA manifest 换为 davybot。
 * 组件/译文中的品牌词由 src/lib/brand.ts + i18n 后处理器按 SERVER_BUILD 切换;
 * 此处只兜底 HTML 入口与 public/ 静态资产(构建期原样拷贝,不经源码)。
 */
function brandServer(): Plugin {
  return {
    name: "brand-server",
    transformIndexHtml(html) {
      return html.replace(/<title>[^<]*<\/title>/, "<title>davybot — AI 智能体平台</title>");
    },
    closeBundle() {
      const manifest = resolve(__dirname, "dist/manifest.webmanifest");
      if (!existsSync(manifest)) return;
      writeFileSync(
        manifest,
        readFileSync(manifest, "utf-8")
          // 完整 slogan 先替换(与 <title> 一致:davybot — AI 智能体平台)
          .replace(/NormNomos — AI 法律智能体平台/g, "davybot — AI 智能体平台")
          .replace(/NormNomos/g, "davybot"),
      );
    },
  };
}

export default defineConfig(({ mode }) => {
  // Server-side env (vite.config runs in Node): SANCTIONS_PROXY_TARGET picks
  // where the /sanctions proxy points. Default keeps localhost:8012 (e.g. an
  // SSH/VS Code forward); set it in .env.local to the backend host directly —
  // e.g. http://10.168.1.105:8012 (web02, see
  // project/prod/kb2.normnomos.com/kb2.services.md) — so dev doesn't depend
  // on a manually re-established forward.
  const env = loadEnv(mode, process.cwd(), "");

  return {
    base: "/app-ui/",
    define: {
      __APP_TARGET__: JSON.stringify("web"),
    },
    plugins: [
      ...(mode === "demo" ? [demoCssDownlevel()] : []),
      ...(mode === "server" ? [brandServer()] : []),
      TanStackRouterVite({
        quoteStyle: "double",
        routesDirectory: "./src/routes",
        generatedRouteTree: "./src/routeTree.gen.ts",
        // 路由级自动代码分割(移动端方案 Phase 0):每个 route 的组件与
        // loader 拆成独立 chunk 按需加载。与 manualChunks 不同,共享依赖仍走
        // rollup 默认策略,不引入跨块初始化环;上线前须无头浏览器冒烟(见
        // 下方 2026-08-27 注释)。
        autoCodeSplitting: true,
      }),
      react(),
      tailwindcss(),
      tsConfigPaths(),
      spaDevIndex(),
    ],
    build: {
      rollupOptions: {
        output: {
          // 2026-08-27: 移除全部自定义 manualChunks —— 细粒度分包反复产生跨/块内
          // 初始化环(recharts↔lodash、zustand↔use-sync-external-store、i18n↔locale
          // 合并块),线上 "Cannot access 'X' before initialization" 白屏(三处实锤)。
          // 回归 rollup 默认分包策略,正确性优先;如需重新细分,先跑无头浏览器冒烟。
        },
      },
    },
    server: {
      port: 8015,
      strictPort: true,
      host: "::",
      allowedHosts: [
        "demo.normnomos.com",
        "dev.a.legal.normnomos.com",
        "localhost",
        "normosbot_app",
        "127.0.0.1",
      ],
      // HMR follows window.location — works when accessing Vite directly at :8015.
      // (Previously forced clientPort:8000 which broke HMR when opening :8015 directly,
      // since the nginx gateway on :8000 doesn't proxy the Vite HMR WebSocket.)
      watch: {
        usePolling: true,
        interval: 1000,
        ignored: [
          "**/src-tauri/target/**",
          "**/.git/**",
          "**/node_modules/.vite/**",
          "**/node_modules/.cache/**",
          "**/dist/**",
          "**/.tauri/**",
          "**/docs/**",
          "**/*.pdf",
          "**/*.png",
          "**/*.jpg",
          "**/*.jpeg",
          "**/*.svg",
          "**/*.ico",
        ],
      },
      proxy: {
        "/api": {
          target: "http://localhost:8431",
          changeOrigin: true,
          ws: true,
        },
        "/legalbot-api": {
          target: "http://localhost:8431",
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/legalbot-api/, ""),
        },
        // WebSocket endpoint — backend serves /ws at root (server_app.py includes
        // the websocket router without a prefix). In dev, VITE_WS_BASE_URL is empty
        // so the client derives ws://localhost:8015/ws from window.location; this
        // proxy bridges it to the backend on :8431. Also covers /ws/task.
        "/ws": {
          target: "http://localhost:8431",
          changeOrigin: true,
          ws: true,
        },
        "/sanctions": {
          target: env.SANCTIONS_PROXY_TARGET || "http://localhost:8012",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/sanctions/, ""),
        },
        "/kb-searcher/api": {
          target: "http://localhost:8014",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/kb-searcher\/api/, "/api"),
        },
        "/nn-kb-searcher/api": {
          target: "http://localhost:8014",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/nn-kb-searcher\/api/, "/api/v1/legal"),
        },
        "/normflow": {
          target: "http://localhost:8013",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/normflow/, "/api/v1"),
        },
      },
    },
  };
});
