/**
 * Expert / Mode type and utilities.
 *
 * Expert data is now loaded dynamically from the nn-user-system market API
 * (via `useMarketTeamsStore`), which scans `team_zh-CN.yaml` at startup.
 *
 * This file provides:
 *  - The Expert type (mapped from TeamHierarchyEntry)
 *  - Conversion and filtering helpers
 *  - Old-ID → slug migration mapping for localStorage backward compat
 */
import type { TeamHierarchyEntry } from "@/lib/market-api";
import type { WorkspaceMode } from "@/lib/store";

// ── Expert type (maps to team_zh-CN.yaml fields) ──────────────────

export interface Expert {
  id: string; // = mode slug, e.g. "sanctions-compliance"
  name: string; // e.g. "🛡️ 制裁合规"
  icon: string; // emoji icon, e.g. "🛡️"
  description: string;
  category: string; // team_type: "compliance" | "intellectual-property" | "law-firm-management"
  priority: number; // sort weight
  enabled: boolean;
}

// ── Status labels (used by status-badge, resource-mention) ────────

export const STATUS_LABEL: Record<string, string> = {
  online: "已上线",
  dev: "研发中",
  custom: "可定制",
};

// ── Old ID → slug migration (for localStorage backward compat) ────

export const OLD_ID_TO_SLUG: Record<string, string> = {
  sanctions: "sanctions-compliance",
  data: "data-compliance",
  ip: "ip-compliance",
  labor: "labor-compliance",
  tax: "overseas-tax-compliance",
};

export function migrateExpertId(oldId: string): string {
  return OLD_ID_TO_SLUG[oldId] ?? oldId;
}

// ── Conversion from TeamHierarchyEntry ─────────────────────────────

export function toExpert(team: TeamHierarchyEntry): Expert {
  // If the team has no explicit slug, derive from name or use empty
  const slug = team.slug ?? team.name ?? "";
  // Some teams may be virtual/display-only — skip those without slug
  return {
    id: slug,
    name: team.name ?? slug,
    icon: team.icon ?? "",
    description: team.description ?? "",
    category: team.team_type ?? team.category ?? "",
    priority: team.priority ?? 5,
    enabled: team.enabled ?? true,
  };
}

export function toExperts(teams: TeamHierarchyEntry[]): Expert[] {
  return teams
    .map(toExpert)
    .filter((e) => e.id) // skip entries without a slug
    .sort((a, b) => b.priority - a.priority);
}

// ── Conversion from WorkspaceMode ──────────────────────────────────

const LEADING_EMOJI_RE = /^(\p{Emoji_Presentation}|\p{Emoji}\uFE0F|\p{Emoji})\s*/u;

/** Extract leading emoji from a string, or return empty string */
function extractEmoji(name: string): string {
  const match = name.match(LEADING_EMOJI_RE);
  return match ? match[1] : "";
}

/** Strip leading emoji so name doesn't duplicate the icon rendered next to it */
function stripEmoji(name: string): string {
  return name.replace(LEADING_EMOJI_RE, "");
}

export function modeToExpert(mode: WorkspaceMode): Expert {
  return {
    id: mode.slug,
    // 下拉/提及列表里 ExpertIcon 已渲染 emoji，name 需去掉前缀避免图标重复显示
    name: stripEmoji(mode.name) || mode.name,
    icon: extractEmoji(mode.name),
    description: mode.description ?? "",
    category: "workspace",
    priority: 5,
    enabled: true,
  };
}

/** System framework mode slugs that are NOT experts (PDCA orchestration modes) */
const FRAMEWORK_MODE_SLUGS = new Set(["orchestrator", "pdca", "plan", "do", "check", "act"]);

export function modesToExperts(modes: WorkspaceMode[]): Expert[] {
  return modes
    .filter((m) => !FRAMEWORK_MODE_SLUGS.has(m.slug)) // 排除框架 mode (orchestrator/pdca), 只保留专家 mode
    .map(modeToExpert)
    .filter((e) => e.id)
    .sort((a, b) => a.name.localeCompare(b.name));
}

// ── Filtering / lookup ─────────────────────────────────────────────

/** Filter experts to only those whose id matches a given set of slugs */
export function filterBySlugs(experts: Expert[], slugs: string[]): Expert[] {
  const set = new Set(slugs);
  return experts.filter((e) => set.has(e.id));
}

/**
 * 按入口专家所属 agent 过滤工作区 modes（专家下拉只显示本团队专家）。
 *
 * agentModes 来自 GET /api/workspaces/{id}/resources 的 agent_modes 字段
 * （安装时各 agent 的 .dawei/agents/<slug>/modes.yaml 归属；安装器会把
 * customModes 拍平进 mode_settings.json，归属只保留在该文件里）。
 *
 * 规则：用 expertId 反查所属 agent，只保留该 agent 的 modes；
 * 无法定位（无映射 / 未选专家 / expertId 不属于任何 agent / 过滤后为空）
 * 一律回退全量，保持旧行为。
 */
export function scopeModesByExpert(
  workspaceModes: WorkspaceMode[],
  agentModes: Record<string, string[]> | undefined,
  expertId: string | undefined | null,
): WorkspaceMode[] {
  if (!agentModes || !expertId) return workspaceModes;
  const ownerSlugs = Object.values(agentModes).find((slugs) => slugs.includes(expertId));
  if (!ownerSlugs) return workspaceModes;
  const scope = new Set(ownerSlugs);
  const filtered = workspaceModes.filter((m) => scope.has(m.slug));
  return filtered.length > 0 ? filtered : workspaceModes;
}

/** Find a single expert by id (slug) */
export function getExpert(experts: Expert[], id: string): Expert | undefined {
  return experts.find((e) => e.id === id);
}
