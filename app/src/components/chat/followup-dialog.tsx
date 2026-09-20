/**
 * Follow-up question dialog — shown when the AI agent needs user input.
 * Displays a question, suggested answers as buttons, and a custom input.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { HelpCircle, Send } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { renderMarkdown } from "@/components/chat/content/markdown";

// ── Types ─────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  question: string;
  suggestions?: string[];
  toolCallId?: string;
  taskId?: string;
  onResponse: (response: string) => void;
  onCancel: () => void;
}

// ── Component ─────────────────────────────────────────────────────

export function FollowupQuestionDialog({
  open,
  onOpenChange,
  question,
  suggestions = [],
  onResponse,
  onCancel,
}: Props) {
  const [customInput, setCustomInput] = useState("");
  const { t } = useTranslation("chatUi");
  const maxLength = 500;

  const handleSelect = (text: string) => {
    onResponse(text);
    setCustomInput("");
    onOpenChange(false);
  };

  const handleCustomSubmit = () => {
    const text = customInput.trim();
    if (!text) return;
    onResponse(text);
    setCustomInput("");
    onOpenChange(false);
  };

  const handleCancel = () => {
    onCancel();
    setCustomInput("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-brand" />
            {t("followup.title")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 flex-1 overflow-y-auto min-h-0">
          {/* Question — rendered as markdown */}
          <div className="rounded-lg bg-muted/40 border border-border px-4 py-3">
            <div className="text-sm leading-relaxed space-y-1">{renderMarkdown(question)}</div>
          </div>

          {/* Suggested answers */}
          {suggestions.length > 0 && (
            <div className="space-y-2">
              <span className="text-[11px] font-medium text-muted-foreground">
                {t("followup.suggested")}
              </span>
              <div className="grid gap-2">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => handleSelect(s)}
                    className={cn(
                      "w-full text-left px-4 py-3 rounded-lg border border-border text-sm",
                      "hover:border-brand/40 hover:bg-brand/5 transition",
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Custom input */}
          <div className="space-y-2">
            <span className="text-[11px] font-medium text-muted-foreground">
              {t("followup.custom")}
            </span>
            <div className="relative">
              <Textarea
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value.slice(0, maxLength))}
                placeholder={t("followup.placeholder")}
                rows={3}
                className="pr-12 resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleCustomSubmit();
                  }
                }}
              />
              <div className="absolute bottom-2 right-2 flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">
                  {customInput.length}/{maxLength}
                </span>
                <Button
                  size="sm"
                  onClick={handleCustomSubmit}
                  disabled={!customInput.trim()}
                  className="h-7 w-7 p-0 rounded-full"
                >
                  <Send className="w-3 h-3" />
                </Button>
              </div>
            </div>
          </div>

          {/* Cancel */}
          <div className="flex justify-end">
            <Button variant="ghost" size="sm" onClick={handleCancel}>
              {t("followup.cancel")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
