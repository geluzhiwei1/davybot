/**
 * ReconnectBanner — 顶部横幅, 显示 grace 倒计时 (§14.3)
 * 订阅 WebSocket reconnectDeadline
 */
import { useReconnectCountdown } from "@/lib/stores/sandbox-store";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { WifiOff, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";

export function ReconnectBanner() {
  const { t } = useTranslation("sandboxUi");
  const seconds = useReconnectCountdown();

  if (seconds === null) return null;

  const isExpired = seconds <= 0;

  return (
    <Alert
      role="status"
      aria-live="polite"
      variant={isExpired ? "destructive" : "default"}
      className="flex items-center gap-2"
    >
      {isExpired ? (
        <WifiOff className="h-4 w-4 shrink-0" />
      ) : (
        <Clock className="h-4 w-4 shrink-0" />
      )}
      <AlertDescription>
        {isExpired ? (
          <>{t("reconnect.expired")}</>
        ) : (
          <>
            {t("reconnect.countdownPrefix")} <strong>{seconds}s</strong>{" "}
            {t("reconnect.countdownSuffix")}
          </>
        )}
      </AlertDescription>
    </Alert>
  );
}
