/**
 * 公开只读报告页（PRD §10 #5 报告分享链接）
 *
 * 路由: /shared-report/$token → GET /api/deep-research/share/{token}
 * 免登录（__root.tsx 公共路径豁免）；report.html 在 sandbox iframe 中渲染
 * （后端 md_to_html 已做 XSS 转义，sandbox="" 再加一层禁脚本兜底）。
 */
import { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import { sharedReportApi, type SharedReport } from "@/lib/api/shared-report";
import { BRAND_NAME } from "@/lib/brand";

export const Route = createFileRoute("/shared-report/$token")({
  head: () => ({ meta: [{ title: `调研报告 · 只读分享 — ${BRAND_NAME}` }] }),
  component: SharedReportPage,
});

function SharedReportPage() {
  const { token } = useParams({ from: "/shared-report/$token" });
  const [report, setReport] = useState<SharedReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    sharedReportApi
      .getSharedReport(token)
      .then((r) => setReport(r))
      .catch(() => setError("报告不存在或分享链接已失效"))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="h-screen flex items-center justify-center bg-background px-4">
        <div className="max-w-md text-center">
          <h1 className="text-4xl font-bold text-gradient-brand">404</h1>
          <p className="mt-3 text-sm text-muted-foreground">{error || "报告不存在"}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="flex items-center gap-3 px-6 py-3 border-b border-border/50 shrink-0">
        <Badge className="bg-brand/15 text-brand border-0 text-[11px] shrink-0">
          {report.pipeline.name}
        </Badge>
        <h1 className="text-lg font-bold tracking-tight truncate">{report.topic}</h1>
        <span className="ml-auto text-xs text-muted-foreground shrink-0">
          🔒 只读分享
          {report.shared_at ? ` · ${new Date(report.shared_at).toLocaleString("zh-CN")}` : ""}
        </span>
      </header>
      <iframe
        srcDoc={report.report_html}
        sandbox=""
        title={report.topic}
        className="flex-1 w-full border-0 bg-white"
      />
    </div>
  );
}
