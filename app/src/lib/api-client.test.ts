import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock env before importing api-client
vi.mock("./env", () => ({
  API_BASE_URL: "http://localhost:8465",
  WS_BASE_URL: "ws://localhost:8465",
  SANCTIONS_API_URL: "http://localhost:8910",
  SUPPORT_API_URL: "http://localhost:8766/support/api",
  UNISEARCHER_API_URL: "http://localhost:8930/api/v1/legal",
  MARKET_API_URL: "http://localhost:8766/support/api",
  NORFLOW_API_URL: "http://localhost:8013",
  getApiBaseUrl: () => "http://localhost:8465",
  getWsBaseUrl: () => "ws://localhost:8465",
  STORAGE_KEYS: {
    authToken: "auth_token",
    refreshToken: "refresh_token",
    language: "legent-language",
    displayMode: "normnomos-display-mode",
    lastModel: "normnomos-last-model",
    lastMode: "normnomos-last-mode",
    lastExpert: "normnomos-last-expert",
  },
  WS_RECONNECT_DELAY: 2000,
  WS_MAX_RECONNECT_ATTEMPTS: 10,
}));

// Mock auth-store
vi.mock("./auth-store", () => ({
  useAuthStore: {
    getState: () => ({
      refreshAccessToken: vi.fn().mockResolvedValue(false),
      logout: vi.fn(),
    }),
  },
}));

describe("api-client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  describe("workspaceApi.list", () => {
    it("sends request with auth header when token is present", async () => {
      localStorage.setItem("auth_token", "test-jwt-token");

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, workspaces: [] }),
      });

      const { workspaceApi } = await import("./api-client");
      await workspaceApi.list();

      expect(fetch).toHaveBeenCalledTimes(1);
      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toBe("http://localhost:8465/api/workspaces/list");
      expect((init?.headers as Record<string, string>)["Authorization"]).toBe(
        "Bearer test-jwt-token",
      );
    });

    it("works without auth token", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, workspaces: [] }),
      });

      const { workspaceApi } = await import("./api-client");
      const result = await workspaceApi.list();

      expect(result.success).toBe(true);
      const [, init] = vi.mocked(fetch).mock.calls[0];
      expect((init?.headers as Record<string, string>)["Authorization"]).toBeUndefined();
    });

    it("throws on non-401 error response", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        text: () => Promise.resolve("Server error"),
      });

      const { workspaceApi } = await import("./api-client");
      await expect(workspaceApi.list()).rejects.toThrow("API Error 500");
    });
  });

  describe("collectionApi", () => {
    it("create sends POST with correct body", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            collection: {
              id: "col-1",
              name: "Test",
              description: "desc",
              workspace_ids: [],
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          }),
      });

      const { collectionApi } = await import("./api-client");
      const result = await collectionApi.create({ name: "Test", description: "desc" });

      expect(result.success).toBe(true);
      expect(result.collection.name).toBe("Test");

      const [, init] = vi.mocked(fetch).mock.calls[0];
      expect(init?.method).toBe("POST");
      expect(JSON.parse(init?.body as string)).toEqual({
        name: "Test",
        description: "desc",
      });
    });

    it("delete sends DELETE request", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true }),
      });

      const { collectionApi } = await import("./api-client");
      await collectionApi.delete("col-1");

      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(init?.method).toBe("DELETE");
      expect(url).toContain("/collections/col-1");
    });
  });

  describe("conversationApi", () => {
    it("rename sends POST with title body", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true }),
      });

      const { conversationApi } = await import("./api-client");
      await conversationApi.rename("ws-1", "conv-1", "New Title");

      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toContain("/workspaces/ws-1/conversations/conv-1");
      expect(init?.method).toBe("POST");
      expect(JSON.parse(init?.body as string)).toEqual({ title: "New Title" });
    });

    it("deleteScoped sends DELETE to workspace-scoped URL", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true }),
      });

      const { conversationApi } = await import("./api-client");
      await conversationApi.deleteScoped("ws-1", "conv-1");

      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toContain("/workspaces/ws-1/conversations/conv-1");
      expect(init?.method).toBe("DELETE");
    });
  });

  describe("llmApi", () => {
    it("listGlobalModels calls GET /api/llms", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            availableLLMs: [{ id: "glm", name: "GLM", displayName: "GLM-4", provider: "zhipu" }],
          }),
      });

      const { llmApi } = await import("./api-client");
      const result = await llmApi.listGlobalModels();

      expect(result.availableLLMs).toHaveLength(1);
      expect(result.availableLLMs[0].id).toBe("glm");
      const [url] = vi.mocked(fetch).mock.calls[0];
      expect(url).toContain("/api/llms");
    });
  });
});
