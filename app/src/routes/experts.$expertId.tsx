import { useEffect, useMemo } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { toExperts, getExpert } from "@/lib/experts";
import { useMarketTeamsStore } from "@/lib/market-teams-store";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Plus } from "lucide-react";
import { useStore } from "@/lib/store";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/experts/$expertId")({
  component: ExpertDetailPage,
  notFoundComponent: () => (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <ExpertNotFound />
      </div>
    </div>
  ),
});

function ExpertNotFound() {
  const { t } = useTranslation("routesA");
  return (
    <>
      <p className="text-muted-foreground">{t("expertDetail.notFound")}</p>
      <Button asChild className="mt-4">
        <Link to="/experts">{t("expertDetail.backToPlaza")}</Link>
      </Button>
    </>
  );
}

function ExpertDetailPage() {
  const { t } = useTranslation("routesA");
  const { expertId } = Route.useParams();
  const navigate = useNavigate();
  const createTask = useStore((s) => s.createTask);

  const marketTeams = useMarketTeamsStore((s) => s.teams);
  const fetchTeams = useMarketTeamsStore((s) => s.fetchTeams);
  const allExperts = useMemo(() => toExperts(marketTeams), [marketTeams]);

  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

  const expert = getExpert(allExperts, expertId);

  if (!expert) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <ExpertNotFound />
        </div>
      </div>
    );
  }

  const related = allExperts.filter((e) => e.category === expert.category && e.id !== expert.id);

  const start = async () => {
    const t = await createTask({
      workspaceId: null,
      expertId: expert.id,
      title: `咨询${expert.name}`,
    });
    navigate({ to: "/temp/$taskId", params: { taskId: t.id } });
  };

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-4xl mx-auto px-6 py-10">
        <Link
          to="/experts"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-brand mb-6"
        >
          <ArrowLeft className="w-3 h-3" /> {t("expertDetail.backToPlaza")}
        </Link>

        <div className="bg-gradient-card border border-border rounded-3xl p-8 shadow-card">
          <div className="flex items-start gap-6">
            <ExpertIcon
              emoji={expert.icon}
              hue={getCategoryHue(expert.category)}
              size="lg"
              className="!w-20 !h-20"
            />
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold">{expert.name}</h1>
              <p className="text-base mt-4 leading-relaxed text-foreground/90">
                {expert.description}
              </p>
              <div className="mt-6 flex gap-3">
                <Button
                  onClick={start}
                  disabled={!expert.enabled}
                  className="bg-gradient-brand text-brand-foreground shadow-brand"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  {expert.enabled ? t("expertDetail.consultNow") : t("expertDetail.unavailable")}
                </Button>
              </div>
            </div>
          </div>
        </div>

        {related.length > 0 && (
          <section className="mt-10">
            <h2 className="text-lg font-semibold mb-3">
              {t("expertDetail.related", { category: expert.category })}
            </h2>
            <div className="grid sm:grid-cols-2 gap-3">
              {related.map((e) => (
                <Link
                  key={e.id}
                  to="/experts/$expertId"
                  params={{ expertId: e.id }}
                  className="bg-card/40 hover:bg-card border border-border rounded-xl p-4 flex items-center gap-3 transition"
                >
                  <ExpertIcon emoji={e.icon} hue={getCategoryHue(e.category)} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">{e.name}</div>
                    <div className="text-xs text-muted-foreground truncate">{e.description}</div>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
