import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ToolResultContentBlock } from "@/lib/types";
import { CheckCircle2, XCircle, AlertTriangle, Expand, Loader2, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  isResultTruncated,
  formatGovernanceInfo,
  detectResultFormat,
  formatToolResult,
  expandSnapshot,
} from "@/lib/governance";
import { BlobWindowRenderer } from "./blob-window-renderer";
import { ListPageRenderer } from "./list-page-renderer";

interface Props {
  block: ToolResultContentBlock;
}

export function ToolResultContent({ block }: Props) {
  const [expandedResult, setExpandedResult] = useState<unknown>(null);
  const [expanding, setExpanding] = useState(false);
  const { t } = useTranslation("chatUi");

  const truncated = isResultTruncated(block.governance);
  const resultFormat = detectResultFormat(block.result);

  async function handleExpand() {
    if (!block.governance?.snapshot_id) return;
    setExpanding(true);
    try {
      const full = await expandSnapshot(block.governance.snapshot_id);
      setExpandedResult(full);
    } catch {
      console.error("Failed to expand snapshot:", block.governance?.snapshot_id);
    } finally {
      setExpanding(false);
    }
  }

  return (
    <div
      className={cn(
        "rounded-lg border my-1",
        block.isError ? "bg-red-500/5 border-red-500/30" : "bg-green-500/5 border-green-500/30",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 text-xs">
        {block.isError ? (
          <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
        )}
        <span className="font-medium truncate">{block.toolName}</span>
        <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
          {block.isError ? t("toolResult.failed") : t("toolResult.success")}
        </span>
        {block.executionTime != null && (
          <span className="text-[10px] text-muted-foreground shrink-0">
            {(block.executionTime / 1000).toFixed(1)}s
          </span>
        )}
      </div>

      <div className="px-3 pb-2">
        {/* Governance truncation banner */}
        {truncated && (
          <div className="flex items-center gap-2 py-1 mb-1">
            <AlertTriangle className="w-3 h-3 text-yellow-500 shrink-0" />
            <span className="text-[10px] text-yellow-600 dark:text-yellow-500">
              {block.governance && formatGovernanceInfo(block.governance)}
            </span>
            {block.governance?.snapshot_id && !expandedResult && (
              <button
                onClick={handleExpand}
                disabled={expanding}
                className="flex items-center gap-1 text-[10px] text-primary hover:underline disabled:opacity-50 shrink-0"
              >
                {expanding ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Expand className="w-3 h-3" />
                )}
                {t("toolResult.expandFull")}
              </button>
            )}
          </div>
        )}

        {/* Expanded result */}
        {expandedResult !== null && (
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-medium text-primary">
                {t("toolResult.fullResult")}
              </span>
              <button
                onClick={() => setExpandedResult(null)}
                className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
              >
                <ChevronUp className="w-3 h-3" />
                {t("toolResult.collapse")}
              </button>
            </div>
            <pre className="text-[11px] bg-muted/60 rounded-md p-2 overflow-x-auto font-mono max-h-60 overflow-y-auto">
              {formatToolResult(expandedResult)}
            </pre>
          </div>
        )}

        {/* Normal / truncated result */}
        {expandedResult === null && (
          <>
            {/* Structured: blob_window */}
            {resultFormat === "blob_window" && (
              <BlobWindowRenderer data={block.result as Record<string, unknown> as never} />
            )}

            {/* Structured: list_page */}
            {resultFormat === "list_page" && (
              <ListPageRenderer data={block.result as Record<string, unknown> as never} />
            )}

            {/* Plain text result */}
            {resultFormat === "plain" && (
              <pre className="text-[11px] bg-muted/60 rounded-md p-2 overflow-x-auto font-mono max-h-40 overflow-y-auto">
                {typeof block.result === "string"
                  ? block.result
                  : JSON.stringify(block.result, null, 2)}
              </pre>
            )}
          </>
        )}

        {block.errorMessage && (
          <p className="text-[11px] text-red-600 mt-1">{block.errorMessage}</p>
        )}
      </div>
    </div>
  );
}
