import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReasoningContentBlock } from "@/lib/types";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Lightbulb, ChevronDown, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { renderMarkdown } from "./markdown";

interface Props {
  block: ReasoningContentBlock;
  /** Whether the reasoning panel starts expanded (default: false = collapsed) */
  defaultOpen?: boolean;
}

export function ReasoningContent({ block, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation("chatUi");

  const handleCopy = () => {
    navigator.clipboard.writeText(block.reasoning);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-lg bg-muted/30 border border-border/60 my-1">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-center gap-2 px-3 py-2">
          <Lightbulb className="w-3.5 h-3.5 text-amber-500 shrink-0" />
          <CollapsibleTrigger asChild>
            <button className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition flex-1 min-w-0">
              <span className="truncate">{t("reasoning.title")}</span>
              <ChevronDown
                className={cn("w-3 h-3 shrink-0 transition-transform", open && "rotate-180")}
              />
            </button>
          </CollapsibleTrigger>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setShowRaw(!showRaw)}
              className="text-[10px] text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-muted transition"
            >
              {showRaw ? "Markdown" : t("reasoning.raw")}
            </button>
            <button
              onClick={handleCopy}
              className="text-muted-foreground hover:text-foreground p-0.5 rounded hover:bg-muted transition"
            >
              {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
        </div>
        <CollapsibleContent>
          <div className="px-3 pb-3 text-xs text-muted-foreground border-t border-border/40 pt-2">
            {showRaw ? (
              <pre className="whitespace-pre-wrap font-mono leading-relaxed">{block.reasoning}</pre>
            ) : (
              <div className="prose-sm">{renderMarkdown(block.reasoning)}</div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
