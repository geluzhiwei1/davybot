/**
 * CSVEditor — Table-based CSV viewer/editor.
 * Parses CSV with PapaParse and renders editable table.
 */
import { useMemo, useState, useCallback } from "react";
import Papa from "papaparse";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";

interface CSVEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
}

const PAGE_SIZE = 100;

export function CSVEditor({ value, onChange, readOnly = false }: CSVEditorProps) {
  const { t } = useTranslation("editorUi");
  const [page, setPage] = useState(0);

  const parsed = useMemo(() => {
    const result = Papa.parse<string[]>(value.trim(), {
      skipEmptyLines: true,
    });
    return {
      headers: result.data[0] ?? [],
      rows: result.data.slice(1),
    };
  }, [value]);

  const totalPages = Math.max(1, Math.ceil(parsed.rows.length / PAGE_SIZE));
  const pageRows = parsed.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleCellChange = useCallback(
    (rowIdx: number, colIdx: number, newVal: string) => {
      if (readOnly || !onChange) return;
      const globalIdx = page * PAGE_SIZE + rowIdx;
      const newRows = [...parsed.rows];
      newRows[globalIdx] = [...newRows[globalIdx]];
      newRows[globalIdx][colIdx] = newVal;
      const csv = Papa.unparse({ fields: parsed.headers, data: newRows });
      onChange(csv);
    },
    [readOnly, onChange, parsed, page],
  );

  const handleExport = () => {
    const blob = new Blob([value], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "export.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/60 shrink-0">
        <span className="text-xs text-muted-foreground">
          {t("csv.rowsCols", { rows: parsed.rows.length, cols: parsed.headers.length })}
        </span>
        <Button variant="ghost" size="sm" className="h-6 text-xs gap-1" onClick={handleExport}>
          <Download className="w-3 h-3" />
          {t("csv.export")}
        </Button>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm z-10">
            <tr>
              <th className="px-2 py-1.5 text-left text-muted-foreground font-medium border-b border-r border-border/60 w-10">
                #
              </th>
              {parsed.headers.map((h, i) => (
                <th
                  key={i}
                  className="px-2 py-1.5 text-left font-medium border-b border-r border-border/60 whitespace-nowrap"
                >
                  {h || t("csv.column", { index: i + 1 })}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri} className="hover:bg-muted/30">
                <td className="px-2 py-1 text-muted-foreground border-r border-border/40 text-center">
                  {page * PAGE_SIZE + ri + 1}
                </td>
                {parsed.headers.map((_, ci) => (
                  <td key={ci} className="px-1 py-0.5 border-r border-border/20">
                    {readOnly ? (
                      <span className="px-1">{row[ci] ?? ""}</span>
                    ) : (
                      <input
                        type="text"
                        value={row[ci] ?? ""}
                        onChange={(e) => handleCellChange(ri, ci, e.target.value)}
                        className="w-full bg-transparent px-1 py-0.5 outline-none hover:bg-brand/5 focus:bg-brand/10 rounded"
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 px-3 py-1.5 border-t border-border/60 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            {t("csv.prevPage")}
          </Button>
          <span className="text-xs text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          >
            {t("csv.nextPage")}
          </Button>
        </div>
      )}
    </div>
  );
}
