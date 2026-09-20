/**
 * SidecarOverlay — full-screen gate shown while the bundled dawei sidecar is
 * starting or has failed to start. Renders null in the web build and once the
 * sidecar reports ready.
 *
 * Starting screen: spinner + live health-check progress (第 N/M 次 · 已等待 Xs)
 * with a thin progress bar, and a collapsible log panel (tailed from the sidecar
 * log file) — collapsed by default so it's clean for users, one click for devs.
 * Failed screen: the error, the log tail auto-expanded, and restart /
 * open-log-folder / copy-log actions. The "重启应用" button relaunches the whole
 * app, which re-runs spawn_sidecar cleanly (fresh port, fresh health check).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSidecarStatus } from "@/hooks/use-sidecar";
import { useSidecarStore } from "@/lib/stores/sidecar-store";
import { IS_DESKTOP } from "@/lib/platform";

export function SidecarOverlay() {
  const { t } = useTranslation("commonUi");
  useSidecarStatus();
  const stage = useSidecarStore((s) => s.stage);
  const message = useSidecarStore((s) => s.message);
  const port = useSidecarStore((s) => s.port);
  const attempt = useSidecarStore((s) => s.attempt);
  const maxAttempts = useSidecarStore((s) => s.maxAttempts);
  const elapsedMs = useSidecarStore((s) => s.elapsedMs);
  const logs = useSidecarStore((s) => s.logs);

  const [restarting, setRestarting] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  // Auto-expand details on failure so the log tail is visible immediately.
  useEffect(() => {
    if (stage === "failed") setDetailsOpen(true);
  }, [stage]);

  // Auto-scroll the log panel to the newest line as it streams in.
  useEffect(() => {
    if (detailsOpen && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs, detailsOpen]);

  // MUST stay above the early return — hooks can't sit below a conditional
  // return (React error #300: "rendered fewer hooks than expected").
  const logText = useMemo(() => logs.map((l) => l.text).join("\n"), [logs]);

  // Web build or sidecar healthy → no overlay.
  if (!IS_DESKTOP || stage === "ready") return null;

  const hasProgress = typeof attempt === "number" && typeof maxAttempts === "number";
  const elapsedSec = typeof elapsedMs === "number" ? Math.round(elapsedMs / 1000) : 0;
  const pct =
    hasProgress && maxAttempts
      ? Math.min(100, Math.round(((attempt as number) / maxAttempts) * 100))
      : 0;

  const restart = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      setRestarting(true);
      await invoke("restart_app");
    } catch (e) {
      console.error("[sidecar] restart failed", e);
      setRestarting(false);
    }
  };

  const openLogFolder = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("reveal_sidecar_log", { port: port ?? null });
    } catch (e) {
      console.error("[sidecar] open log folder failed", e);
    }
  };

  const copyLogs = async () => {
    try {
      const text = message ? `${message}\n\n${logText}` : logText;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.error("[sidecar] copy logs failed", e);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <div className="flex w-full max-w-md flex-col items-center gap-4 px-6 text-center">
        {stage === "starting" ? (
          <>
            <div className="w-10 h-10 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
            <div className="w-full">
              <p className="text-base font-semibold">{t("sidecar.starting")}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {hasProgress
                  ? t("sidecar.healthCheck", {
                      attempt: attempt as number,
                      max: maxAttempts as number,
                      sec: elapsedSec,
                    })
                  : t("sidecar.firstStart")}
              </p>
              {hasProgress && (
                <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-brand transition-[width] duration-300 ease-out"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="text-3xl">⚠️</div>
            <div>
              <p className="text-base font-semibold text-destructive">{t("sidecar.startFailed")}</p>
              <p className="mt-1 text-sm text-muted-foreground whitespace-pre-line">
                {message || t("sidecar.cannotConnect")}
              </p>
            </div>
          </>
        )}

        {/* Collapsible sidecar log — collapsed during starting, open on failure. */}
        <details
          open={detailsOpen}
          onToggle={(e) => setDetailsOpen((e.currentTarget as HTMLDetailsElement).open)}
          className="w-full text-left"
        >
          <summary className="cursor-pointer select-none text-xs text-muted-foreground hover:text-foreground">
            {detailsOpen ? t("sidecar.hideDetails") : t("sidecar.showDetails")}
            {logs.length > 0 && (
              <span className="ml-1">{t("sidecar.logLines", { count: logs.length })}</span>
            )}
          </summary>
          <div
            ref={logRef}
            className="mt-2 h-48 overflow-auto rounded-md border border-border bg-muted/50 p-3 font-mono text-[10px] leading-relaxed text-muted-foreground"
          >
            {logs.length === 0 ? (
              <span className="text-muted-foreground/60">{t("sidecar.noLogs")}</span>
            ) : (
              logs.map((l) => (
                <div key={l.id} className="whitespace-pre-wrap break-all">
                  {l.text}
                </div>
              ))
            )}
          </div>
        </details>

        {stage === "failed" && (
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button
              onClick={restart}
              disabled={restarting}
              className="inline-flex items-center rounded-md bg-gradient-brand text-brand-foreground px-4 py-2 text-sm font-medium shadow-brand disabled:opacity-60"
            >
              {restarting ? t("sidecar.restarting") : t("sidecar.restartApp")}
            </button>
            <button
              onClick={openLogFolder}
              className="inline-flex items-center rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted"
            >
              {t("sidecar.openLogFolder")}
            </button>
            <button
              onClick={copyLogs}
              disabled={logs.length === 0 && !message}
              className="inline-flex items-center rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
            >
              {copied ? t("sidecar.copied") : t("sidecar.copyLogs")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
