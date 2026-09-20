// Vite config for Tauri desktop app — plain SPA build without TanStack Start SSR.
// Uses TanStack Router file-based routing directly with the same source files.
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import tsConfigPaths from "vite-tsconfig-paths";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { renameSync, readFileSync } from "node:fs";

/** Dev middleware: serve index.tauri.html for all SPA routes so client-side routing works. */
function tauriDevIndex(): Plugin {
  return {
    name: "tauri-dev-index",
    configureServer(server) {
      // Pre-hook: intercept SPA routes before Vite's built-in middleware
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split("?")[0] || "/";
        // Skip Vite internals and requests with file extensions
        if (url.startsWith("/@") || (url !== "/" && /\.[a-zA-Z0-9]+$/.test(url))) {
          return next();
        }
        // Read and transform the SPA entry HTML
        const htmlContent = readFileSync(resolve(__dirname, "index.tauri.html"), "utf-8");
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

/** Rename index.tauri.html → index.html in build output so Tauri finds it. */
function tauriHtmlRename(): Plugin {
  return {
    name: "tauri-html-rename",
    closeBundle() {
      const outDir = resolve(__dirname, "src-tauri/ui-dist");
      const from = resolve(outDir, "index.tauri.html");
      const to = resolve(outDir, "index.html");
      try {
        renameSync(from, to);
      } catch {
        // ignore if file doesn't exist
      }
    },
  };
}

/**
 * Mobile-only: downlevel built CSS for old Android WebViews (Chromium 92 —
 * Huawei WebView 12.x etc.). Flattens @layer, converts oklch()→rgb, unwinds
 * nesting. Runs after the bundle is written; see scripts/mobile-css-downlevel.mjs.
 */
function mobileCssDownlevel(): Plugin {
  return {
    name: "mobile-css-downlevel",
    async closeBundle() {
      // Dynamic import keeps the native lightningcss binary out of desktop builds.
      // Absolute file:// URL: vite rewrites the config into node_modules/.vite-temp,
      // so a relative specifier would resolve against the wrong directory.
      const scriptUrl = pathToFileURL(resolve(__dirname, "scripts/mobile-css-downlevel.mjs")).href;
      const { downlevelCssDir } = await import(scriptUrl);
      const results = downlevelCssDir(resolve(__dirname, "src-tauri/ui-dist/assets"));
      for (const r of results) console.log(`[mobile-css] ${r.bytes ? "downleveled" : "skipped"} ${r.file}`);
    },
  };
}

// Mode "mobile" (Android/iOS via Tauri) builds the same SPA but flags the
// frontend as mobile: IS_DESKTOP stays false so the sidecar overlay / port
// resolution / desktop-only update checks are skipped and API calls fall back
// to the build-time VITE_* values (cloud endpoints from .env).
export default defineConfig(({ mode }) => ({
  define: {
    __APP_TARGET__: JSON.stringify(mode === "mobile" ? "mobile" : "desktop"),
  },
  plugins: [
    TanStackRouterVite({
      quoteStyle: "double",
      routesDirectory: "./src/routes",
      generatedRouteTree: "./src/routeTree.gen.ts",
      // 与 vite.config.ts 保持一致:两份配置共用同一个 routeTree.gen.ts,
      // autoCodeSplitting 开关不同会互相翻转生成产物(桌面端同样受益于懒加载)。
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
    tsConfigPaths(),
    tauriDevIndex(),
    tauriHtmlRename(),
    ...(mode === "mobile" ? [mobileCssDownlevel()] : []),
  ],
  build: {
    outDir: "src-tauri/ui-dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: "./index.tauri.html",
      },
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-radix": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-popover",
            "@radix-ui/react-tooltip",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-scroll-area",
            "@radix-ui/react-separator",
            "@radix-ui/react-slot",
            "@radix-ui/react-toggle",
            "@radix-ui/react-toggle-group",
            "@radix-ui/react-collapsible",
            "@radix-ui/react-hover-card",
            "@radix-ui/react-label",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
          ],
          "vendor-router-state": ["@tanstack/react-router", "zustand"],
          "vendor-icons": ["lucide-react"],
        },
      },
    },
    copyPublicDir: false,
  },
  server: {
    port: 8015,
    strictPort: true,
    allowedHosts: ["dev.a.legal.normnomos.com", "localhost", ".cpolar.top", ".cpolar.cn"],
  },
}));
