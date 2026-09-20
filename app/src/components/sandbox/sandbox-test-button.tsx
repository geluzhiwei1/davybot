/**
 * SandboxTestButton — "测试连接" 按钮 + 结果展示 (§14.3)
 * 内部 useState
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Zap, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { sandboxTestApi } from "@/lib/api/sandbox";
import type { ProviderType } from "@/lib/types/sandbox";

interface SandboxTestButtonProps {
  provider: ProviderType;
  onResult?: (ok: boolean, latencyMs?: number, error?: string) => void;
}

export function SandboxTestButton({ provider, onResult }: SandboxTestButtonProps) {
  const { t } = useTranslation("sandbox");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; latency?: number; error?: string } | null>(
    null,
  );

  async function handleTest() {
    setLoading(true);
    setResult(null);
    try {
      const res = await sandboxTestApi.testConnection(provider);
      const r = res.result;
      setResult({ ok: r.ok, latency: r.latency_ms, error: r.error });
      onResult?.(r.ok, r.latency_ms, r.error);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("test.failed");
      setResult({ ok: false, error: msg });
      onResult?.(false, undefined, msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button variant="outline" size="sm" onClick={handleTest} disabled={loading}>
        {loading ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Zap className="mr-2 h-4 w-4" />
        )}
        {t("test.button")}
      </Button>

      {result && (
        <div className="flex items-center gap-2">
          {result.ok ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <Badge variant="secondary">{t("test.success")}</Badge>
              {result.latency !== undefined && (
                <span className="text-sm text-muted-foreground">{result.latency}ms</span>
              )}
            </>
          ) : (
            <>
              <XCircle className="h-4 w-4 text-destructive" />
              <Badge variant="destructive">{t("test.error")}</Badge>
              {result.error && (
                <span className="text-sm text-muted-foreground">{result.error}</span>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
