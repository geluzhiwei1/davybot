/**
 * useSidecarStatus — keep the sidecar store in sync with the bundled dawei
 * sidecar's lifecycle (Tauri desktop only; no-op in the web build).
 *
 * Two signals feed the store:
 *  1. Rust events — `sidecar-status` (starting/progress/ready/failed) and the
 *     high-frequency `sidecar-log` stream. These fire once, at app launch, from
 *     `spawn_sidecar`.
 *  2. A direct boot-time health probe below.
 *
 * Why the probe: on a webview *reload* the Rust host does NOT re-emit
 * `sidecar-status` (those events only fire during launch-time spawn), so the
 * store resets to "starting" and the overlay would hang forever — exactly the
 * "refresh → stuck on 正在启动本地引擎" symptom. The probe makes "is the sidecar
 * reachable?" the source of truth, so a reload while the engine is already up
 * dismisses the overlay immediately. The events still drive progress/logging
 * during a cold start.
 */
import { useEffect } from "react";
import { useSidecarStore } from "@/lib/stores/sidecar-store";
import { setSidecarBase } from "@/lib/env";
import { IS_DESKTOP } from "@/lib/platform";
import i18n from "@/lib/i18n";

interface SidecarStatusPayload {
  status: string;
  port: number | null;
  message?: string | null;
  attempt?: number | null;
  max_attempts?: number | null;
  elapsed_ms?: number | null;
  logs?: string[] | null;
}

interface SidecarLogPayload {
  line: string;
  ts_ms?: number;
}

/** How long the probe keeps trying before declaring the engine unresponsive. */
const PROBE_TOTAL_MS = 90_000;
const PROBE_INTERVAL_MS = 750;

export function useSidecarStatus(): void {
  const setStarting = useSidecarStore((s) => s.setStarting);
  const setProgress = useSidecarStore((s) => s.setProgress);
  const setReady = useSidecarStore((s) => s.setReady);
  const setFailed = useSidecarStore((s) => s.setFailed);
  const appendLog = useSidecarStore((s) => s.appendLog);

  useEffect(() => {
    if (!IS_DESKTOP) return;
    let unlistenStatus: (() => void) | undefined;
    let unlistenLog: (() => void) | undefined;
    let cancelled = false;

    (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      if (cancelled) return;

      // --- Signal 1: Rust events -----------------------------------------
      try {
        unlistenStatus = await listen<SidecarStatusPayload>("sidecar-status", (e) => {
          const { status, port, message, attempt, max_attempts, elapsed_ms, logs } = e.payload;
          if (status === "ready" && port) {
            setSidecarBase(port);
            setReady(port);
          } else if (status === "starting" && port) {
            setStarting(port);
          } else if (status === "progress") {
            if (typeof attempt === "number" && typeof max_attempts === "number") {
              setProgress(attempt, max_attempts, typeof elapsed_ms === "number" ? elapsed_ms : 0);
            }
          } else if (status === "failed") {
            setFailed(port ?? null, message ?? null, logs ?? null);
          }
        });

        // Live sidecar log stream (one event per appended file line).
        unlistenLog = await listen<SidecarLogPayload>("sidecar-log", (e) => {
          const line = e.payload?.line;
          if (typeof line === "string" && line.trim() !== "") {
            appendLog(line, typeof e.payload?.ts_ms === "number" ? e.payload.ts_ms : Date.now());
          }
        });
      } catch (e) {
        if (cancelled) return;
        // Subscribing failed — the IPC channel is broken (most commonly the CSP
        // blocking ipc.localhost). Fail loudly instead of spinning forever.
        console.error("[sidecar] failed to subscribe to sidecar events", e);
        setFailed(null, i18n.t("sidecar.ipcFailed", { ns: "hooksUi" }));
        return;
      }

      if (cancelled) {
        unlistenStatus?.();
        unlistenLog?.();
        return;
      }

      // --- Signal 2: direct health probe --------------------------------
      // Reachability is the source of truth for "ready", independent of the
      // launch-only events. Closes the reload gap and any missed event.
      probeUntilReady();
    })();

    async function probeUntilReady() {
      const { invoke } = await import("@tauri-apps/api/core");
      const deadline = Date.now() + PROBE_TOTAL_MS;

      // Loop until: healthy (→ ready), stage left "starting" (event resolved it),
      // or the safety deadline elapsed (→ failed with a way out).
      while (!cancelled && Date.now() < deadline) {
        if (useSidecarStore.getState().stage !== "starting") return;

        let port: number | null = null;
        try {
          port = await invoke<number | null>("get_sidecar_port");
        } catch {
          /* host not ready yet — retry */
        }
        if (cancelled) return;

        if (typeof port === "number" && port > 0) {
          try {
            const res = await fetch(`http://localhost:${port}/api/health`, {
              signal: AbortSignal.timeout(2000),
            });
            if (res.ok) {
              setSidecarBase(port);
              setReady(port);
              return;
            }
          } catch {
            /* sidecar not listening yet — retry */
          }
        }

        await new Promise((r) => setTimeout(r, PROBE_INTERVAL_MS));
      }

      // Deadline elapsed and still "starting" — the engine never came up (and
      // no launch-time event rescued us, e.g. on reload after the sidecar died).
      if (!cancelled && useSidecarStore.getState().stage === "starting") {
        setFailed(null, i18n.t("sidecar.timeout", { ns: "hooksUi" }));
      }
    }

    return () => {
      cancelled = true;
      unlistenStatus?.();
      unlistenLog?.();
    };
  }, [setStarting, setProgress, setReady, setFailed, appendLog]);
}
