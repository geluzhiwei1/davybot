/**
 * DocxPreview — Render .docx files in-browser using docx-preview.
 * For legacy .doc files, the backend converts them to .docx first.
 *
 * IMPORTANT: The container div must ALWAYS be in the DOM (even during loading)
 * so that containerRef.current is available when the useEffect runs.
 * Previously the container was only rendered on status==="ready", causing
 * the effect to bail out on !containerRef.current → stuck loading forever.
 */
import { useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";

interface DocxPreviewProps {
  blobUrl?: string;
  filename?: string;
}

/** Timeout for renderAsync — prevents infinite hang on malformed docs. */
const RENDER_TIMEOUT_MS = 30_000;

export function DocxPreview({ blobUrl }: DocxPreviewProps) {
  const { t } = useTranslation("editorUi");
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!blobUrl) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    setStatus("loading");
    setErrorMsg("");

    (async () => {
      try {
        const res = await fetch(blobUrl);
        if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
        const blob = await res.blob();

        if (cancelled) return;

        const container = containerRef.current;
        if (!container) {
          // Should never happen since container is always rendered now,
          // but guard just in case.
          console.warn("[DocxPreview] container not found");
          return;
        }

        container.innerHTML = "";

        // Wrap renderAsync with a timeout to prevent infinite hang.
        await Promise.race([
          renderAsync(blob, container, undefined, {
            className: "docx-container",
            inWrapper: true,
            ignoreWidth: false,
            ignoreHeight: false,
            breakPages: true,
          }),
          new Promise<never>((_, reject) => {
            timer = setTimeout(() => reject(new Error(t("docx.renderTimeout"))), RENDER_TIMEOUT_MS);
          }),
        ]);

        if (!cancelled) setStatus("ready");
      } catch (e) {
        console.error("[DocxPreview] renderAsync failed:", e);
        if (!cancelled) {
          setStatus("error");
          setErrorMsg(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (timer) clearTimeout(timer);
      }
    })();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [blobUrl]);

  return (
    <div className="h-full overflow-auto bg-gray-100 relative">
      {/* Loading overlay — SIBLING of render target, NOT a child.
          renderAsync writes directly to containerRef.innerHTML, so React
          must not manage any children inside it (causes removeChild error). */}
      {status === "loading" && (
        <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
            {t("docx.rendering")}
          </div>
        </div>
      )}

      {/* Error overlay */}
      {status === "error" && (
        <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
          <div className="text-center space-y-2">
            <FileText className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <p>{t("docx.renderFailed")}</p>
            <p className="text-xs text-muted-foreground/60">{errorMsg}</p>
          </div>
        </div>
      )}

      {/* Render target — NO React children. renderAsync owns this DOM. */}
      <div
        ref={containerRef}
        className="docx-container mx-auto bg-white shadow-lg"
        style={{ maxWidth: "900px", minHeight: "100%" }}
      />
    </div>
  );
}
