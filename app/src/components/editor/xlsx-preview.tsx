/**
 * XlsxPreview — Render .xlsx files in-browser using SheetJS (xlsx).
 * Supports multiple sheets with tab navigation.
 * For legacy .xls files, the backend converts them to .xlsx first.
 */
import { useEffect, useState, useMemo } from "react";
import * as XLSX from "xlsx";
import { FileSpreadsheet, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

interface XlsxPreviewProps {
  blobUrl?: string;
  filename?: string;
}

export function XlsxPreview({ blobUrl }: XlsxPreviewProps) {
  const { t } = useTranslation("editorUi");
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
  const [activeSheet, setActiveSheet] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!blobUrl) return;
    let cancelled = false;

    setStatus("loading");
    setErrorMsg("");

    (async () => {
      try {
        const res = await fetch(blobUrl);
        if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
        const buf = await res.arrayBuffer();
        const wb = XLSX.read(buf, { type: "array" });
        if (cancelled) return;
        setWorkbook(wb);
        setActiveSheet(0);
        setStatus("ready");
      } catch (e) {
        if (!cancelled) {
          setStatus("error");
          setErrorMsg(e instanceof Error ? e.message : String(e));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [blobUrl]);

  // Render active sheet as HTML table
  const sheetHtml = useMemo(() => {
    if (!workbook || activeSheet >= workbook.SheetNames.length) return "";
    const sheetName = workbook.SheetNames[activeSheet];
    const sheet = workbook.Sheets[sheetName];
    return XLSX.utils.sheet_to_html(sheet, { id: "xlsx-table", editable: false });
  }, [workbook, activeSheet]);

  if (status === "loading") {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
          {t("xlsx.parsing")}
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        <div className="text-center space-y-2">
          <FileSpreadsheet className="w-8 h-8 mx-auto text-muted-foreground/40" />
          <p>{t("xlsx.parseFailed")}</p>
          <p className="text-xs text-muted-foreground/60">{errorMsg}</p>
        </div>
      </div>
    );
  }

  if (!workbook) return null;
  const sheetCount = workbook.SheetNames.length;

  return (
    <div className="flex flex-col h-full">
      {/* Sheet tabs */}
      {sheetCount > 1 && (
        <div className="flex items-center gap-1 px-2 py-1 border-b border-border/60 overflow-x-auto shrink-0 scrollbar-thin bg-muted/20">
          {workbook.SheetNames.map((name, idx) => (
            <button
              key={idx}
              onClick={() => setActiveSheet(idx)}
              className={
                "px-2.5 py-1 text-xs rounded whitespace-nowrap transition-colors " +
                (idx === activeSheet
                  ? "bg-background text-foreground border border-border shadow-sm font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60")
              }
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Sheet content */}
      <div className="flex-1 min-h-0 overflow-auto">
        <div
          className="xlsx-table-wrapper"
          dangerouslySetInnerHTML={{ __html: sheetHtml }}
          style={{ display: "table", margin: "0 auto", padding: "8px" }}
        />
      </div>

      {/* Bottom info bar */}
      <div className="flex items-center justify-between px-3 py-1 border-t border-border/60 shrink-0 text-xs text-muted-foreground bg-muted/10">
        <span>
          {t("xlsx.sheetInfo", {
            current: activeSheet + 1,
            total: sheetCount,
            name: workbook.SheetNames[activeSheet],
          })}
        </span>
        {sheetCount > 1 && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveSheet((s) => Math.max(0, s - 1))}
              disabled={activeSheet === 0}
              className="p-0.5 rounded hover:bg-muted/60 disabled:opacity-30"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setActiveSheet((s) => Math.min(sheetCount - 1, s + 1))}
              disabled={activeSheet === sheetCount - 1}
              className="p-0.5 rounded hover:bg-muted/60 disabled:opacity-30"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
