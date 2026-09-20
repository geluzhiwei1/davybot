/**
 * ListPageRenderer — renders backend list_page structured output.
 * Ported from Vue webui ListPageRenderer.vue
 *
 * Data shape: { type: "list_page", items: [...], total, offset, has_more, ... }
 */
import { useTranslation } from "react-i18next";

interface ListPageData {
  type: string;
  items?: unknown[];
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  next_offset?: number | null;
  summary?: string | null;
}

interface Props {
  data: ListPageData;
  maxItemChars?: number;
}

function formatItem(item: unknown, maxChars: number): string {
  if (typeof item === "string") {
    return item.length > maxChars ? item.substring(0, maxChars) + "..." : item;
  }
  if (typeof item === "object" && item !== null) {
    try {
      const json = JSON.stringify(item);
      return json.length > maxChars ? json.substring(0, maxChars) + "..." : json;
    } catch {
      return String(item);
    }
  }
  return String(item);
}

export function ListPageRenderer({ data, maxItemChars = 500 }: Props) {
  const { t } = useTranslation("chatUi");
  const items = data.items ?? [];
  const offset = data.offset ?? 0;

  return (
    <div className="text-[12px] leading-relaxed">
      {/* Summary */}
      {data.summary && (
        <div className="py-1 text-muted-foreground text-[11px] border-b border-border/40 mb-1.5">
          {data.summary}
        </div>
      )}

      {/* Items */}
      <div className="flex flex-col gap-0.5">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex gap-2 py-0.5 font-mono whitespace-pre-wrap break-all hover:bg-muted/40 rounded-sm"
          >
            <span className="text-primary/70 font-semibold min-w-[2rem] text-right shrink-0 select-none">
              {offset + i + 1}
            </span>
            <span className="flex-1 min-w-0 text-foreground">{formatItem(item, maxItemChars)}</span>
          </div>
        ))}
      </div>

      {/* Pagination info */}
      <div className="flex items-center gap-1 mt-1.5 pt-1.5 border-t border-border/40">
        <span className="text-[10px] text-muted-foreground">
          {t("listPage.showing", { shown: items.length, total: data.total ?? 0 })}
        </span>
        {data.has_more && (
          <span className="text-[10px] text-muted-foreground">
            ·{" "}
            {data.next_offset != null
              ? t("listPage.nextPage", { offset: data.next_offset })
              : t("listPage.more")}
          </span>
        )}
      </div>
    </div>
  );
}
