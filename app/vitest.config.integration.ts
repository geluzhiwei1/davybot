import { defineConfig } from "vitest/config";
import tsConfigPaths from "vite-tsconfig-paths";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));

/**
 * Integration test config — Part B (client ↔ live backend contract).
 *
 * Run with:  pnpm test:integration   (= vitest run --mode integration --config this)
 *
 * Kept separate from the unit-test vitest.config.ts so that:
 *   - `pnpm test` stays fast and offline (unit only)
 *   - integration tests are opt-in and self-skip when the backend is down
 *
 * `--mode integration` loads .env.integration, which points VITE_API_BASE_URL /
 * VITE_WS_BASE_URL at the local dawei (default http://localhost:8431). The required
 * external-service VITE_* vars are inherited from .env, satisfying env.ts's guard.
 */
export default defineConfig({
  plugins: [tsConfigPaths()],
  resolve: {
    // Explicit @ → src alias so tests under tests/ resolve app modules identically
    // to the production vite build (tsConfigPaths alone doesn't always apply to files
    // outside tsconfig's `include`).
    alias: { "@": resolve(root, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/integration/**/*.test.ts"],
    setupFiles: ["./src/test-setup.ts"],
    testTimeout: 30_000,
    hookTimeout: 30_000,
    // Surface which target the suite is hitting; override via INTEGRATION_TARGET.
    env: {
      INTEGRATION_TARGET: process.env.INTEGRATION_TARGET ?? "http://localhost:8010",
    },
  },
});
