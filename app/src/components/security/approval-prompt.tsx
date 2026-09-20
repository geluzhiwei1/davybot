/**
 * ApprovalPrompt — human-in-the-loop tool approval dialog (P2.2).
 *
 * Listens for backend `tool_approval_request` WebSocket messages and shows an
 * AlertDialog. The user approves/denies; the reply is sent back as
 * `tool_approval_response`. If the user doesn't respond within the server-set
 * timeout, the client auto-denies (the backend also times out — both are safe).
 *
 * Mounted globally (AppDrawers host) so it works across all conversations.
 */
import { useEffect, useRef, useState } from "react";
import { ShieldAlert } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { useTranslation } from "react-i18next";
import { wsClient } from "@/lib/ws-client";
import type { WsMessage } from "@/lib/types";

type PendingApproval = {
  request_id: string;
  tool_name: string;
  risk: string;
  tool_input: Record<string, unknown>;
  timeout_seconds: number;
};

const RISK_VARIANT: Record<string, "destructive" | "secondary" | "outline"> = {
  critical: "destructive",
  high: "destructive",
  medium: "secondary",
  low: "outline",
};

export function ApprovalPrompt() {
  const { t } = useTranslation("miscUi");
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [remaining, setRemaining] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Keep the latest pending id in a ref so the countdown closer resolves correctly.
  const pendingRef = useRef<PendingApproval | null>(null);
  pendingRef.current = pending;

  // Subscribe to tool_approval_request messages.
  useEffect(() => {
    const listener = (msg: WsMessage) => {
      if (msg.type === "tool_approval_request" && msg.request_id) {
        setPending({
          request_id: msg.request_id,
          tool_name: msg.tool_name ?? "(unknown)",
          risk: msg.risk ?? "medium",
          tool_input: msg.tool_input ?? {},
          timeout_seconds: msg.timeout_seconds ?? 120,
        });
      }
    };
    wsClient.addMessageListener(listener);
    return () => wsClient.removeMessageListener(listener);
  }, []);

  // Countdown + client-side auto-deny.
  useEffect(() => {
    if (!pending) return;
    const startedAt = Date.now();
    setRemaining(Math.round(pending.timeout_seconds));
    timerRef.current = setInterval(() => {
      const left = Math.max(
        0,
        Math.round(pending.timeout_seconds - (Date.now() - startedAt) / 1000),
      );
      setRemaining(left);
      if (left <= 0) respond(false);
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending?.request_id]);

  function respond(approved: boolean) {
    const p = pendingRef.current;
    if (!p) return;
    wsClient.sendToolApprovalResponse(p.request_id, approved);
    if (timerRef.current) clearInterval(timerRef.current);
    setPending(null);
  }

  return (
    <AlertDialog
      open={pending !== null}
      onOpenChange={(open) => {
        if (!open) respond(false); // dialog dismissed (Esc / overlay) = deny
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-destructive" />
            {t("security.approvalTitle")}
            {pending && (
              <Badge variant={RISK_VARIANT[pending.risk] ?? "secondary"} className="ml-1">
                {pending.risk}
              </Badge>
            )}
          </AlertDialogTitle>
          <AlertDialogDescription>{t("security.approvalDesc")}</AlertDialogDescription>
        </AlertDialogHeader>

        {pending && (
          <div className="text-xs space-y-2 py-2 border-y">
            <div className="flex gap-2">
              <span className="text-muted-foreground shrink-0">{t("security.approvalTool")}</span>
              <span className="font-medium">{pending.tool_name}</span>
            </div>
            <div>
              <div className="text-muted-foreground mb-1">{t("security.approvalParams")}</div>
              <pre className="bg-muted/40 rounded p-2 overflow-auto max-h-40 font-mono text-[11px]">
                {JSON.stringify(pending.tool_input, null, 2)}
              </pre>
            </div>
            <div className="text-muted-foreground">
              {t("security.approvalAutoDeny", { seconds: remaining })}
            </div>
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => respond(false)}>{t("security.deny")}</AlertDialogCancel>
          <AlertDialogAction onClick={() => respond(true)}>
            {t("security.allowExecution")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
