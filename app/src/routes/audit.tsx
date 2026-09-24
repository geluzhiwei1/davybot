/**
 * 操作审计页面 — 展示用户操作日志
 */
import { useState, useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { ScrollText, Trash2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useAuditStore, AUDIT_ACTION_LABELS, type AuditAction } from "@/lib/audit-store";
import { BRAND_NAME } from "@/lib/brand";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/audit")({
  head: () => ({ meta: [{ title: `操作审计 — ${BRAND_NAME}` }] }),
  component: AuditPage,
});

const PAGE_SIZE = 50;

function AuditPage() {
  const { t } = useTranslation("routesA");
  const entries = useAuditStore((s) => s.entries);
  const clearAuditEntries = useAuditStore((s) => s.clearAuditEntries);

  const [filterAction, setFilterAction] = useState<string>("all");
  const [filterKeyword, setFilterKeyword] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    let result = entries;
    if (filterAction !== "all") {
      result = result.filter((e) => e.action === filterAction);
    }
    if (filterKeyword.trim()) {
      const kw = filterKeyword.trim().toLowerCase();
      result = result.filter(
        (e) =>
          e.target.toLowerCase().includes(kw) || (e.detail && e.detail.toLowerCase().includes(kw)),
      );
    }
    return result;
  }, [entries, filterAction, filterKeyword]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleFilterChange = (value: string) => {
    setFilterAction(value);
    setPage(0);
  };

  const handleKeywordChange = (value: string) => {
    setFilterKeyword(value);
    setPage(0);
  };

  const handleClear = () => {
    clearAuditEntries();
    setPage(0);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b shrink-0">
        <ScrollText className="w-4 h-4 text-muted-foreground" />
        <h1 className="text-sm font-semibold">{t("audit.title")}</h1>
        <span className="text-xs text-muted-foreground ml-1">
          {t("audit.recordCount", { count: filtered.length })}
        </span>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          {/* Keyword search */}
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              placeholder={t("audit.searchPlaceholder")}
              value={filterKeyword}
              onChange={(e) => handleKeywordChange(e.target.value)}
              className="h-7 w-48 pl-7 text-xs"
            />
          </div>
          {/* Action filter */}
          <Select value={filterAction} onValueChange={handleFilterChange}>
            <SelectTrigger className="h-7 w-32 text-xs">
              <SelectValue placeholder={t("audit.actionType")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("audit.allTypes")}</SelectItem>
              {(Object.entries(AUDIT_ACTION_LABELS) as [AuditAction, string][]).map(
                ([key, label]) => (
                  <SelectItem key={key} value={key}>
                    {label}
                  </SelectItem>
                ),
              )}
            </SelectContent>
          </Select>
          {/* Clear */}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-destructive hover:text-destructive"
                disabled={entries.length === 0}
              >
                <Trash2 className="w-3.5 h-3.5 mr-1" />
                {t("audit.clear")}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t("audit.clearConfirmTitle")}</AlertDialogTitle>
                <AlertDialogDescription>
                  {t("audit.clearConfirmDesc", { count: entries.length })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t("audit.cancel")}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleClear}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {t("audit.clear")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
            <ScrollText className="w-10 h-10 opacity-30" />
            <p className="text-sm">{t("audit.empty")}</p>
            <p className="text-xs">{t("audit.emptyHint")}</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-44 text-xs">{t("audit.colTime")}</TableHead>
                    <TableHead className="w-28 text-xs">{t("audit.colAction")}</TableHead>
                    <TableHead className="w-48 text-xs">{t("audit.colTarget")}</TableHead>
                    <TableHead className="text-xs">{t("audit.colDetail")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paged.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="text-xs text-muted-foreground font-mono">
                        {formatTimestamp(entry.timestamp)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-[10px] font-normal">
                          {AUDIT_ACTION_LABELS[entry.action] ?? entry.action}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs max-w-48 truncate">{entry.target}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                        {entry.detail ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 py-3 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  {t("audit.prevPage")}
                </Button>
                <span className="text-xs text-muted-foreground">
                  {page + 1} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  {t("audit.nextPage")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Format ISO timestamp to readable local string */
function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  } catch {
    return iso;
  }
}
