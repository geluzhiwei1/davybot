import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ThinkingContentBlock, ThinkingStep } from "@/lib/types";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Brain, CheckCircle2, XCircle, Loader2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  block: ThinkingContentBlock;
}

const STATUS_ICON: Record<ThinkingStep["status"], React.ReactNode> = {
  in_progress: <Loader2 className="w-3 h-3 text-yellow-500 animate-spin" />,
  completed: <CheckCircle2 className="w-3 h-3 text-green-500" />,
  failed: <XCircle className="w-3 h-3 text-red-500" />,
};

const STATUS_LABEL_KEYS: Record<ThinkingStep["status"], string> = {
  in_progress: "thinking.status.inProgress",
  completed: "thinking.status.completed",
  failed: "thinking.status.failed",
};

export function ThinkingContent({ block }: Props) {
  const { t } = useTranslation("chatUi");
  const [open, setOpen] = useState(false);
  const completedCount = block.steps.filter((s) => s.status === "completed").length;
  const hasActive = block.steps.some((s) => s.status === "in_progress");

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition w-full px-1 py-1">
          <Brain className="w-3.5 h-3.5 text-purple-500" />
          <span>
            {t("thinking.title", { completed: completedCount, total: block.steps.length })}
          </span>
          {hasActive && <Loader2 className="w-3 h-3 animate-spin text-yellow-500" />}
          <ChevronDown
            className={cn("w-3 h-3 ml-auto transition-transform", open && "rotate-180")}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 space-y-2 pl-2 border-l-2 border-purple-500/30">
          {block.steps.map((step) => (
            <div key={step.step_id} className="flex items-start gap-2 text-xs">
              <span className="mt-0.5 shrink-0">{STATUS_ICON[step.status]}</span>
              <div className="min-w-0 flex-1">
                <div className="text-foreground">{step.thought}</div>
                <span
                  className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded",
                    step.status === "completed" && "bg-green-500/10 text-green-600",
                    step.status === "in_progress" && "bg-yellow-500/10 text-yellow-600",
                    step.status === "failed" && "bg-red-500/10 text-red-600",
                  )}
                >
                  {t(STATUS_LABEL_KEYS[step.status])}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
