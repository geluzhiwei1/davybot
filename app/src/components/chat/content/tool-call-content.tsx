import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ToolCallContentBlock, ToolCallInfo } from "@/lib/types";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Wrench, ChevronDown, Loader2, CheckCircle2, XCircle, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { detectResultFormat } from "@/lib/governance";
import { BlobWindowRenderer } from "./blob-window-renderer";
import { ListPageRenderer } from "./list-page-renderer";

interface Props {
  block: ToolCallContentBlock;
}

const STATUS_CONFIG: Record<
  ToolCallInfo["status"],
  { icon: React.ReactNode; labelKey: string; color: string }
> = {
  started: {
    icon: <Loader2 className="w-3 h-3 animate-spin text-blue-500" />,
    labelKey: "toolCall.status.started",
    color: "text-blue-600 bg-blue-500/10",
  },
  in_progress: {
    icon: <Loader2 className="w-3 h-3 animate-spin text-yellow-500" />,
    labelKey: "toolCall.status.inProgress",
    color: "text-yellow-600 bg-yellow-500/10",
  },
  completed: {
    icon: <CheckCircle2 className="w-3 h-3 text-green-500" />,
    labelKey: "toolCall.status.completed",
    color: "text-green-600 bg-green-500/10",
  },
  failed: {
    icon: <XCircle className="w-3 h-3 text-red-500" />,
    labelKey: "toolCall.status.failed",
    color: "text-red-600 bg-red-500/10",
  },
};

export function ToolCallContent({ block }: Props) {
  const { toolCall } = block;
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation("chatUi");
  const statusCfg = STATUS_CONFIG[toolCall.status];

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(toolCall.tool_input, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-lg bg-muted/30 border border-border/60 my-1">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-center gap-2 px-3 py-2">
          <Wrench className="w-3.5 h-3.5 text-blue-500 shrink-0" />
          <CollapsibleTrigger asChild>
            <button className="flex items-center gap-1.5 text-xs text-foreground hover:text-foreground transition flex-1 min-w-0">
              <span className="truncate font-medium">{toolCall.tool_name}</span>
              <ChevronDown
                className={cn("w-3 h-3 shrink-0 transition-transform", open && "rotate-180")}
              />
            </button>
          </CollapsibleTrigger>
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded shrink-0", statusCfg.color)}>
            {t(statusCfg.labelKey)}
          </span>
        </div>

        {/* Progress bar */}
        {toolCall.progress_percentage != null && toolCall.progress_percentage > 0 && (
          <div className="px-3 pb-1">
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              {toolCall.current_step && <span className="truncate">{toolCall.current_step}</span>}
              {toolCall.total_steps && (
                <span className="shrink-0">
                  {toolCall.current_step_index ?? 0}/{toolCall.total_steps}
                </span>
              )}
            </div>
            <div className="h-1 bg-muted rounded-full mt-1 overflow-hidden">
              <div
                className="h-full bg-brand rounded-full transition-all duration-300"
                style={{ width: `${toolCall.progress_percentage}%` }}
              />
            </div>
          </div>
        )}

        <CollapsibleContent>
          <div className="px-3 pb-3 border-t border-border/40 pt-2 space-y-2">
            {/* Input */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-medium text-muted-foreground">
                  {t("toolCall.input")}
                </span>
                <button
                  onClick={handleCopy}
                  className="text-muted-foreground hover:text-foreground p-0.5 rounded hover:bg-muted transition"
                >
                  {copied ? (
                    <Check className="w-3 h-3 text-green-500" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                </button>
              </div>
              <pre className="text-[11px] bg-muted/60 rounded-md p-2 overflow-x-auto font-mono max-h-40 overflow-y-auto">
                {JSON.stringify(toolCall.tool_input, null, 2)}
              </pre>
            </div>

            {/* Output */}
            {toolCall.output !== undefined && (
              <div>
                <span className="text-[10px] font-medium text-muted-foreground">
                  {t("toolCall.output")}
                </span>
                <div className="mt-1">
                  {(() => {
                    const fmt = detectResultFormat(toolCall.output);
                    if (fmt === "blob_window")
                      return (
                        <BlobWindowRenderer
                          data={toolCall.output as Record<string, unknown> as never}
                        />
                      );
                    if (fmt === "list_page")
                      return (
                        <ListPageRenderer
                          data={toolCall.output as Record<string, unknown> as never}
                        />
                      );
                    return (
                      <pre className="text-[11px] bg-muted/60 rounded-md p-2 overflow-x-auto font-mono max-h-40 overflow-y-auto">
                        {typeof toolCall.output === "string"
                          ? toolCall.output
                          : JSON.stringify(toolCall.output, null, 2)}
                      </pre>
                    );
                  })()}
                </div>
              </div>
            )}

            {/* Error */}
            {toolCall.error && (
              <div>
                <span className="text-[10px] font-medium text-red-500">{t("toolCall.error")}</span>
                <pre className="text-[11px] bg-red-500/10 rounded-md p-2 text-red-600 mt-1">
                  {toolCall.error}
                </pre>
              </div>
            )}

            {/* Execution time */}
            {toolCall.execution_time != null && (
              <div className="text-[10px] text-muted-foreground text-right">
                {t("toolCall.duration", { seconds: (toolCall.execution_time / 1000).toFixed(1) })}
              </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
