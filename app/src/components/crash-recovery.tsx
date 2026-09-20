import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, RotateCcw, Trash2, Bug } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

interface CrashReport {
  id: string;
  error: Error;
  timestamp: string;
  componentStack?: string;
}

interface CrashRecoveryDialogProps {
  open: boolean;
  reports: CrashReport[];
  onRecover: () => void;
  onDiscard: () => void;
  onReport?: (reports: CrashReport[]) => void;
}

export function CrashRecoveryDialog({
  open,
  reports,
  onRecover,
  onDiscard,
  onReport,
}: CrashRecoveryDialogProps) {
  const { t } = useTranslation("commonUi");
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <Dialog open={open} onOpenChange={() => onDiscard()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            {t("crash.title")}
          </DialogTitle>
          <DialogDescription>{t("crash.desc", { count: reports.length })}</DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-60">
          <div className="space-y-2">
            {reports.map((report) => (
              <div key={report.id} className="rounded-lg border p-3">
                <button
                  className="flex w-full items-center justify-between text-sm font-medium"
                  onClick={() => setExpanded(expanded === report.id ? null : report.id)}
                >
                  <span className="truncate">{report.error.message}</span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(report.timestamp).toLocaleTimeString()}
                  </span>
                </button>
                {expanded === report.id && (
                  <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs text-muted-foreground">
                    {report.error.stack}
                    {report.componentStack && `\n\nComponent:\n${report.componentStack}`}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>

        <DialogFooter className="gap-2">
          <Button onClick={onDiscard} variant="ghost" size="sm">
            <Trash2 className="mr-2 h-4 w-4" />
            {t("crash.discard")}
          </Button>
          <Button onClick={onRecover} variant="outline" size="sm">
            <RotateCcw className="mr-2 h-4 w-4" />
            {t("crash.recover")}
          </Button>
          {onReport && (
            <Button onClick={() => onReport(reports)} size="sm">
              <Bug className="mr-2 h-4 w-4" />
              {t("crash.reportAll")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
