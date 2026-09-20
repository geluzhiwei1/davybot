import { describe, it, expect, vi } from "vitest";

// i18n 直通 mock:t("apiErrors:key") → "apiErrors:key",断言稳定且不依赖 locale 加载
vi.mock("../i18n", () => ({
  default: { t: (k: string) => k },
}));

import { ApiError } from "./client";
import { apiErrorMessage } from "./errors";

const apiErr = (status: number, body = ""): ApiError => new ApiError(status, "StatusText", body);

describe("apiErrorMessage(智能律所错误翻译层)", () => {
  it("英文 detail 关键词命中映射,不透传技术词", () => {
    expect(apiErrorMessage(apiErr(404, '{"detail":"Lead not found"}'))).toBe("apiErrors:notFound");
    expect(apiErrorMessage(apiErr(409, '{"detail":"Invalid status transition"}'))).toBe(
      "apiErrors:invalidTransition",
    );
    expect(apiErrorMessage(apiErr(403, '{"detail":"Permission denied"}'))).toBe(
      "apiErrors:forbidden",
    );
  });

  it("后端中文业务文案原样透传", () => {
    expect(apiErrorMessage(apiErr(400, '{"detail":"余额不足,无法提现"}'))).toBe(
      "余额不足,无法提现",
    );
  });

  it("无 detail 时按 HTTP 状态类别映射(方向修正的核心:不再直出 ApiError.message)", () => {
    const e = apiErr(422, "");
    expect(e.message).toMatch(/API Error 422/); // 技术串确实存在于 message
    expect(apiErrorMessage(e)).toBe("apiErrors:validation"); // 但翻译层不透传
    expect(apiErrorMessage(apiErr(500))).toBe("apiErrors:server");
    expect(apiErrorMessage(apiErr(403))).toBe("apiErrors:forbidden");
  });

  it("body 非 JSON 时取原文再走映射/中文透传", () => {
    expect(apiErrorMessage(apiErr(404, "Not Found"))).toBe("apiErrors:notFound");
  });

  it("网络类异常统一网络文案", () => {
    const abort = new Error("The operation was aborted");
    abort.name = "AbortError";
    expect(apiErrorMessage(abort)).toBe("apiErrors:network");
    expect(apiErrorMessage(new TypeError("Failed to fetch"))).toBe("apiErrors:network");
    expect(apiErrorMessage(new Error("fetch failed"))).toBe("apiErrors:network");
  });

  it("未知本地异常返回 null,由调用方 i18n 兜底", () => {
    expect(apiErrorMessage(new Error("some local bug"))).toBeNull();
    expect(apiErrorMessage("raw string")).toBeNull();
    expect(apiErrorMessage(null)).toBeNull();
  });
});
