/**
 * 运行模式统一 API (多模式统一方案 §L3)
 * GET /api/runtime-info — mode + deployment_class + capabilities
 */
import { request } from "./client";

export type RuntimeMode = "saas" | "desktop" | "server" | "tui";

export interface RuntimeInfo {
  mode: RuntimeMode;
  deployment_class: "local" | "saas";
  capabilities: string[];
}

export const runtimeApi = {
  getRuntimeInfo: () => request<RuntimeInfo>("/api/runtime-info"),
};
