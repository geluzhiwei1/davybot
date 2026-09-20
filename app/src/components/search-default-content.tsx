/**
 * SearchDefaultContent — default content shown when no search query is active.
 * Loads system stats + knowledge bases from nn-kb-searcher and displays them
 * alongside suggested search tags.
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Database, FileText, Hash, BookOpen, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { uniSearcherApi } from "@/lib/unisearcher-service";
import type { LegalSystemStats, LegalKnowledgeBase } from "@/lib/unisearcher-service";

interface Props {
  suggestions: string[];
  onSuggestionClick?: (tag: string) => void;
}

const DOC_TYPE_LABEL_KEYS: Record<string, string> = {
  NORMATIVE: "searchDefault.docType.NORMATIVE",
  CASE: "searchDefault.docType.CASE",
  STANDARD: "searchDefault.docType.STANDARD",
  ANCILLARY: "searchDefault.docType.ANCILLARY",
  LAW: "searchDefault.docType.LAW",
  REG_ADMIN: "searchDefault.docType.REG_ADMIN",
  REG_LOCAL: "searchDefault.docType.REG_LOCAL",
  RULE_DEPT: "searchDefault.docType.RULE_DEPT",
  JUDICIAL: "searchDefault.docType.JUDICIAL",
};

export function SearchDefaultContent({ suggestions, onSuggestionClick }: Props) {
  const { t } = useTranslation("commonUi");
  const [stats, setStats] = useState<LegalSystemStats | null>(null);
  const [kbs, setKbs] = useState<LegalKnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      uniSearcherApi.getSystemStats().catch((e) => {
        toast.error(t("searchDefault.loadStatsFailed"), { description: String(e) });
        return null;
      }),
      uniSearcherApi.listKnowledgeBases().catch((e) => {
        toast.error(t("searchDefault.loadKbFailed"), { description: String(e) });
        return null;
      }),
    ]).then(([s, kbRes]) => {
      if (s) setStats(s);
      if (kbRes) setKbs(kbRes.knowledge_bases || kbRes.data || []);
      setLoading(false);
    });
  }, []);

  // Compute summary numbers
  const docCounts = stats?.documents || {};
  const totalDocs = Object.values(docCounts).reduce(
    (a, b) => a + (typeof b === "number" ? b : 0),
    0,
  );
  const domainCounts = stats?.domains || {};
  const totalDomains = Object.keys(domainCounts).length;

  return (
    <div className="space-y-4">
      {/* Stats overview */}
      {loading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          <span className="text-xs">{t("searchDefault.loadingOverview")}</span>
        </div>
      ) : stats ? (
        <div className="grid grid-cols-3 gap-2">
          <StatCard
            icon={<FileText className="w-3.5 h-3.5" />}
            label={t("searchDefault.totalDocs")}
            value={totalDocs}
          />
          <StatCard
            icon={<Database className="w-3.5 h-3.5" />}
            label={t("searchDefault.kbCount")}
            value={kbs.length}
          />
          <StatCard
            icon={<Hash className="w-3.5 h-3.5" />}
            label={t("searchDefault.domains")}
            value={totalDomains}
          />
        </div>
      ) : null}

      {/* Document type breakdown */}
      {stats && Object.keys(docCounts).length > 0 && (
        <Card>
          <CardHeader className="pb-1.5 pt-2.5 px-3">
            <CardTitle className="text-[11px] font-medium text-muted-foreground">
              {t("searchDefault.docTypeDistribution")}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-2.5">
            <div className="space-y-1.5">
              {Object.entries(docCounts)
                .filter(([, v]) => typeof v === "number" && v > 0)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .slice(0, 6)
                .map(([type, count]) => {
                  const pct = totalDocs > 0 ? ((count as number) / totalDocs) * 100 : 0;
                  return (
                    <div key={type} className="flex items-center gap-2">
                      <span className="text-[11px] min-w-[56px] text-muted-foreground">
                        {DOC_TYPE_LABEL_KEYS[type] ? t(DOC_TYPE_LABEL_KEYS[type]) : type}
                      </span>
                      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-brand/60 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-muted-foreground tabular-nums w-10 text-right">
                        {count as number}
                      </span>
                    </div>
                  );
                })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Knowledge bases */}
      {kbs.length > 0 && (
        <Card>
          <CardHeader className="pb-1.5 pt-2.5 px-3">
            <CardTitle className="text-[11px] font-medium text-muted-foreground">
              {t("searchDefault.kbList")}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-2.5">
            <div className="space-y-1">
              {kbs.slice(0, 5).map((kb) => (
                <div key={kb.id} className="flex items-center justify-between text-[11px] py-0.5">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <BookOpen className="w-3 h-3 text-brand shrink-0" />
                    <span className="truncate">{kb.name}</span>
                  </div>
                  <span className="text-muted-foreground shrink-0 ml-2 tabular-nums">
                    {t("searchDefault.docCount", {
                      count: kb.document_count ?? kb.stats?.documents ?? 0,
                    })}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Domain coverage */}
      {stats && totalDomains > 0 && (
        <Card>
          <CardHeader className="pb-1.5 pt-2.5 px-3">
            <CardTitle className="text-[11px] font-medium text-muted-foreground">
              {t("searchDefault.domainCoverage")}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-2.5">
            <div className="flex flex-wrap gap-1">
              {Object.entries(domainCounts)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .slice(0, 8)
                .map(([domain, count]) => (
                  <Badge key={domain} variant="outline" className="text-[10px] px-1.5 py-0">
                    {domain}
                    <span className="ml-1 text-muted-foreground">{count as number}</span>
                  </Badge>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Suggested searches */}
      {suggestions.length > 0 && (
        <>
          <Separator />
          <div>
            <p className="text-[11px] text-muted-foreground mb-2">
              {t("searchDefault.hotSearches")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((tag) => (
                <Badge
                  key={tag}
                  variant="outline"
                  className="text-[10px] cursor-pointer hover:bg-brand/10 hover:text-brand transition"
                  onClick={() => onSuggestionClick?.(tag)}
                >
                  {tag}
                </Badge>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-2.5 text-center">
      <div className="flex items-center justify-center gap-1 text-brand mb-1">{icon}</div>
      <p className="text-base font-semibold leading-none">{value}</p>
      <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}
