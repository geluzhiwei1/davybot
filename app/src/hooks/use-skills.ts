import { useState, useCallback } from "react";
import type { Skill, SkillFilter } from "@/lib/types/skills";
import i18n from "@/lib/i18n";

/** Demo skills — resolved at call time so language switches take effect. */
function buildDemoSkills(): Skill[] {
  const t = (key: string) => i18n.t(key, { ns: "hooksUi" });
  return [
    {
      name: "sanctions-screening",
      description: t("skills.sanctionsScreening"),
      category: "compliance",
      scope: "system",
      mode: "plan",
      has_instructions: true,
      resource_count: 5,
    },
    {
      name: "contract-review",
      description: t("skills.contractReview"),
      category: "contracts",
      scope: "workspace",
      mode: "do",
      has_instructions: true,
      resource_count: 3,
    },
    {
      name: "legal-research",
      description: t("skills.legalResearch"),
      category: "research",
      scope: "user",
      mode: "plan",
      has_instructions: true,
    },
    {
      name: "regulatory-intelligence",
      description: t("skills.regulatoryIntelligence"),
      category: "compliance",
      scope: "system",
      mode: "check",
    },
    {
      name: "due-diligence",
      description: t("skills.dueDiligence"),
      category: "compliance",
      scope: "workspace",
      mode: "do",
      has_instructions: true,
      resource_count: 8,
    },
    {
      name: "case-search",
      description: t("skills.caseSearch"),
      category: "research",
      scope: "user",
      mode: "do",
    },
  ];
}

export function useSkills() {
  const [skills] = useState<Skill[]>(buildDemoSkills);
  const [loading] = useState(false);
  const [filter, setFilter] = useState<SkillFilter>({ mode: "", scope: "", search: "" });

  const filteredSkills = skills.filter((s) => {
    if (filter.mode && s.mode !== filter.mode) return false;
    if (filter.scope && s.scope !== filter.scope) return false;
    if (filter.search) {
      const q = filter.search.toLowerCase();
      return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
    }
    return true;
  });

  const updateFilter = useCallback((patch: Partial<SkillFilter>) => {
    setFilter((prev) => ({ ...prev, ...patch }));
  }, []);

  return { skills: filteredSkills, allSkills: skills, loading, filter, updateFilter };
}
