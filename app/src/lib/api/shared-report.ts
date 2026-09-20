/**
 * 公开分享报告 API 下沉(拆库方案 §5.2 解倒挂)。
 *
 * deepResearchApi 随 B2 迁入 biz/deep-research,但 /shared-report/$token 路由
 * 属核心公共页(免登录);核心不得 import biz,故将该端点与类型下沉核心。
 * metrics 原为 WorkspaceMetrics | Record<string, unknown> | null(WorkspaceMetrics
 * 定义在 biz 侧),此处收敛为 Record 宽型——核心唯一消费方(路由)不读 metrics。
 */
import { request } from "./client";

export interface SharedReport {
  pipeline: { slug: string; name: string; team: string };
  workspace_id: string;
  topic: string;
  template_name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  shared_at: string | null;
  metrics: Record<string, unknown> | null;
  report_md: string;
  report_html: string;
}

export const sharedReportApi = {
  /** GET /api/deep-research/share/{token} — 免登录公开端点 */
  getSharedReport: (token: string) => request<SharedReport>(`/api/deep-research/share/${token}`),
};
