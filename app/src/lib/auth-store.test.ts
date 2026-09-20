import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock SUPPORT_API_URL before importing auth-store
vi.mock("./env", () => ({
  API_BASE_URL: "http://localhost:8465",
  WS_BASE_URL: "ws://localhost:8465",
  SANCTIONS_API_URL: "http://localhost:8910",
  UNISEARCHER_API_URL: "http://localhost:8930/api/v1/legal",
  SUPPORT_API_URL: "http://localhost:8766/support/api",
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

describe("auth-store", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("initial state is unauthenticated", async () => {
    const { useAuthStore } = await import("./auth-store");
    const state = useAuthStore.getState();
    expect(state.authenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.initialized).toBe(false);
  });

  it("login success sets tokens and user", async () => {
    const mockUser = {
      id: "user-1",
      email: "test@example.com",
      nickname: "Test User",
      token_quota: 1000,
      token_used: 0,
      is_active: true,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          access_token: "at-123",
          refresh_token: "rt-456",
          user: mockUser,
        }),
    });

    const { useAuthStore } = await import("./auth-store");
    await useAuthStore.getState().login("test@example.com", "password");

    const state = useAuthStore.getState();
    expect(state.authenticated).toBe(true);
    expect(state.accessToken).toBe("at-123");
    expect(state.refreshToken).toBe("rt-456");
    expect(state.user?.email).toBe("test@example.com");
    expect(localStorage.getItem("auth_token")).toBe("at-123");
    expect(localStorage.getItem("refresh_token")).toBe("rt-456");
  });

  it("login failure throws error and does not authenticate", async () => {
    // Reset store state first to avoid leakage from previous tests
    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({
      authenticated: false,
      accessToken: null,
      refreshToken: null,
      user: null,
    });

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Invalid credentials" }),
    });

    await expect(useAuthStore.getState().login("bad@example.com", "wrong")).rejects.toThrow(
      "Invalid credentials",
    );

    expect(useAuthStore.getState().authenticated).toBe(false);
  });

  it("logout clears state and localStorage", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true });

    localStorage.setItem("auth_token", "at-123");
    localStorage.setItem("refresh_token", "rt-456");

    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({
      accessToken: "at-123",
      refreshToken: "rt-456",
      authenticated: true,
      user: {
        id: "u1",
        email: "test@test.com",
        nickname: "T",
        token_quota: 0,
        token_used: 0,
        is_active: true,
      },
    });

    await useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.authenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
  });

  it("refreshAccessToken returns false when no refreshToken", async () => {
    const { useAuthStore } = await import("./auth-store");
    useAuthStore.setState({ refreshToken: null });
    const result = await useAuthStore.getState().refreshAccessToken();
    expect(result).toBe(false);
  });
});
