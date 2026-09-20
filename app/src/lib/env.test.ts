import { describe, it, expect, vi, beforeEach } from "vitest";

// Helper: stub all required env vars so env.ts module doesn't throw
function stubAllEnv(overrides: Record<string, string> = {}) {
  const defaults: Record<string, string> = {
    VITE_API_BASE_URL: "http://localhost:8431",
    VITE_WS_BASE_URL: "ws://localhost:8431",
    VITE_SANCTIONS_API_URL: "http://localhost:8910",
    VITE_KB_SEARCHER_API_URL: "http://localhost:8930/api/v1/legal",
    VITE_SUPPORT_API_URL: "http://localhost:8766/support/api",
    VITE_MARKET_API_URL: "http://localhost:8766/support/api",
    VITE_NORFLOW_API_URL: "http://localhost:8013",
  };
  vi.unstubAllEnvs();
  for (const [k, v] of Object.entries({ ...defaults, ...overrides })) {
    vi.stubEnv(k, v);
  }
}

describe("env.ts", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  describe("optional env vars (F1)", () => {
    it("allows empty VITE_SANCTIONS_API_URL (业务集成可选,空=关闭)", async () => {
      stubAllEnv();
      vi.stubEnv("VITE_SANCTIONS_API_URL", "");
      const env = await import("./env");
      expect(env.SANCTIONS_API_URL).toBe("");
    });

    it("allows empty VITE_KB_SEARCHER_API_URL", async () => {
      stubAllEnv();
      vi.stubEnv("VITE_KB_SEARCHER_API_URL", "");
      const env = await import("./env");
      expect(env.UNISEARCHER_API_URL).toBe("");
    });

    it("loads with empty SUPPORT/MARKET/NORFLOW (server 自包含)", async () => {
      stubAllEnv({
        VITE_SUPPORT_API_URL: "",
        VITE_MARKET_API_URL: "",
        VITE_NORFLOW_API_URL: "",
      });
      const env = await import("./env");
      expect(env.SUPPORT_API_URL).toBe("");
      expect(env.MARKET_API_URL).toBe("");
      expect(env.NORFLOW_API_URL).toBe("");
    });

    it("loads successfully when all required vars are set", async () => {
      stubAllEnv();
      const env = await import("./env");
      expect(env.API_BASE_URL).toBe("http://localhost:8431");
      expect(env.WS_BASE_URL).toBe("ws://localhost:8431");
      expect(env.SANCTIONS_API_URL).toBe("http://localhost:8910");
      expect(env.UNISEARCHER_API_URL).toBe("http://localhost:8930/api/v1/legal");
      expect(env.SUPPORT_API_URL).toBe("http://localhost:8766/support/api");
      expect(env.MARKET_API_URL).toBe("http://localhost:8766/support/api");
      expect(env.NORFLOW_API_URL).toBe("http://localhost:8013");
    });

    it("uses env override values", async () => {
      stubAllEnv({
        VITE_API_BASE_URL: "https://custom.api.example.com",
        VITE_SANCTIONS_API_URL: "https://custom-sanctions.example.com",
      });
      const env = await import("./env");
      expect(env.API_BASE_URL).toBe("https://custom.api.example.com");
      expect(env.SANCTIONS_API_URL).toBe("https://custom-sanctions.example.com");
    });
  });

  describe("STORAGE_KEYS", () => {
    it("has all required keys", async () => {
      stubAllEnv();
      const { STORAGE_KEYS } = await import("./env");
      expect(STORAGE_KEYS).toHaveProperty("authToken", "auth_token");
      expect(STORAGE_KEYS).toHaveProperty("refreshToken", "refresh_token");
      expect(STORAGE_KEYS).toHaveProperty("language", "legent-language");
      expect(STORAGE_KEYS).toHaveProperty("displayMode", "normnomos-display-mode");
      expect(STORAGE_KEYS).toHaveProperty("lastModel", "normnomos-last-model");
      expect(STORAGE_KEYS).toHaveProperty("lastMode", "normnomos-last-mode");
      expect(STORAGE_KEYS).toHaveProperty("lastExpert", "normnomos-last-expert");
    });

    it("is deeply readonly (as const)", async () => {
      stubAllEnv();
      const { STORAGE_KEYS } = await import("./env");
      expect(typeof STORAGE_KEYS.authToken).toBe("string");
      expect(STORAGE_KEYS.authToken).toBe("auth_token");
    });
  });

  describe("optional numeric config", () => {
    it("WS_RECONNECT_DELAY defaults to 2000", async () => {
      stubAllEnv();
      const { WS_RECONNECT_DELAY } = await import("./env");
      expect(WS_RECONNECT_DELAY).toBe(2000);
    });

    it("WS_MAX_RECONNECT_ATTEMPTS defaults to unlimited retries", async () => {
      stubAllEnv();
      const { WS_MAX_RECONNECT_ATTEMPTS } = await import("./env");
      expect(WS_MAX_RECONNECT_ATTEMPTS).toBe(0);
    });

    it("WS_RECONNECT_DELAY uses env override", async () => {
      stubAllEnv({ VITE_WS_RECONNECT_DELAY: "5000" });
      const { WS_RECONNECT_DELAY } = await import("./env");
      expect(WS_RECONNECT_DELAY).toBe(5000);
    });
  });
});
