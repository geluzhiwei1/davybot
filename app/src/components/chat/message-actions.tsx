/**
 * Per-message action buttons: copy / export markdown / export PDF.
 * Rendered below a chat bubble; revealed on hover/focus of the parent .group.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, FileText, Printer, Check } from "lucide-react";
import { toast } from "sonner";
import type { ChatMessage } from "@/lib/types";
import {
  copyMessageMarkdown,
  exportMarkdownFile,
  printMessagePdf,
  hasExportableContent,
} from "@/lib/message-export";
import { cn } from "@/lib/utils";

interface Props {
  message: ChatMessage;
  /** Align actions row to the message side. */
  align?: "start" | "end";
}

const BTN_CLS =
  "inline-flex items-center justify-center rounded-md p-1 text-muted-foreground/80 " +
  "hover:bg-muted hover:text-foreground transition-colors " +
  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function MessageActions({ message, align = "start" }: Props) {
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation("chatUi");

  if (!hasExportableContent(message)) return null;

  const onCopy = async () => {
    const ok = await copyMessageMarkdown(message);
    if (ok) {
      setCopied(true);
      toast.success(t("messageActions.copied"));
      setTimeout(() => setCopied(false), 1400);
    } else {
      toast.error(t("messageActions.copyFailed"));
    }
  };

  const onMd = () => {
    try {
      exportMarkdownFile(message);
      toast.success(t("messageActions.mdExported"));
    } catch {
      toast.error(t("messageActions.exportFailed"));
    }
  };

  const onPdf = () => {
    try {
      printMessagePdf(message);
    } catch {
      toast.error(t("messageActions.pdfFailed"));
    }
  };

  return (
    <div
      className={cn("flex items-center gap-0.5", align === "end" ? "justify-end" : "justify-start")}
    >
      <button
        type="button"
        onClick={onCopy}
        title={t("messageActions.copyTitle")}
        aria-label={t("messageActions.copyTitle")}
        className={BTN_CLS}
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-green-500" />
        ) : (
          <Copy className="w-3.5 h-3.5" />
        )}
      </button>
      <button
        type="button"
        onClick={onMd}
        title={t("messageActions.exportMd")}
        aria-label={t("messageActions.exportMd")}
        className={BTN_CLS}
      >
        <FileText className="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        onClick={onPdf}
        title={t("messageActions.exportPdf")}
        aria-label={t("messageActions.exportPdf")}
        className={BTN_CLS}
      >
        <Printer className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
