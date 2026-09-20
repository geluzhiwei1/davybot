import { useState, useEffect, useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { toExperts } from "@/lib/experts";
import { useMarketTeamsStore } from "@/lib/market-teams-store";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/experts")({
  head: () => ({
    meta: [
      { title: "法律专家广场 — NormNomos" },
      {
        name: "description",
        content: "12 位法律合规 AI 专家：制裁合规、出口管制、数据合规、境外投资、反垄断、ESG 等。",
      },
    ],
  }),
  component: ExpertsPage,
});

function ExpertsPage() {
  const { t } = useTranslation("routesA");
  const marketTeams = useMarketTeamsStore((s) => s.teams);
  const fetchTeams = useMarketTeamsStore((s) => s.fetchTeams);
  const allExperts = useMemo(() => toExperts(marketTeams), [marketTeams]);

  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

  const categories = useMemo(
    () => Array.from(new Set(allExperts.map((e) => e.category).filter(Boolean))),
    [allExperts],
  );
  const [active, setActive] = useState<string>("all");

  const visible = active === "all" ? allExperts : allExperts.filter((e) => e.category === active);

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight">
            {t("experts.titlePrefix")}
            <span className="text-gradient-brand">{t("experts.titleSuffix")}</span>
          </h1>
          <p className="text-muted-foreground mt-2">{t("experts.subtitle")}</p>
        </div>

        <div className="sticky top-0 z-10 -mx-6 px-6 py-3 bg-background/80 backdrop-blur border-b border-border mb-6">
          <Tabs value={active} onValueChange={setActive}>
            <TabsList className="bg-transparent p-0 h-auto gap-1 flex-wrap justify-start">
              <TabsTrigger
                value="all"
                className="data-[state=active]:bg-brand/10 data-[state=active]:text-brand data-[state=active]:border-brand/40 border border-transparent rounded-full px-3 py-1 text-xs"
              >
                {t("experts.all")} · {allExperts.length}
              </TabsTrigger>
              {categories.map((c) => (
                <TabsTrigger
                  key={c}
                  value={c}
                  className="data-[state=active]:bg-brand/10 data-[state=active]:text-brand data-[state=active]:border-brand/40 border border-transparent rounded-full px-3 py-1 text-xs"
                >
                  {c} · {allExperts.filter((e) => e.category === c).length}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visible.map((e) => (
            <Link
              key={e.id}
              to="/experts/$expertId"
              params={{ expertId: e.id }}
              className="group bg-gradient-card border border-border rounded-2xl p-5 hover:border-brand/40 hover:shadow-card transition"
            >
              <div className="flex items-start justify-between mb-4">
                <ExpertIcon emoji={e.icon} hue={getCategoryHue(e.category)} size="lg" />
              </div>
              <div className="font-semibold text-base">{e.name}</div>
              <p className="text-sm text-muted-foreground/90 mt-3 leading-relaxed line-clamp-3">
                {e.description}
              </p>
              <div className="text-[10px] text-muted-foreground/70 mt-3 uppercase tracking-wider">
                {e.category}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
