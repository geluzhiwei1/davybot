/**
 * Lead score parsing — PRD 02.2.4 §3.2 (LeadAgent 4 维评分模型).
 *
 * The backend score report shape varies by version (dict of numbers, dict of
 * {score, factors}, nested under `score` on the lead detail). This parser
 * normalizes those shapes into a typed report, or returns null when no real
 * dimension breakdown is present — callers MUST fall back to showing the
 * aggregate score honestly instead of synthesizing dimensions (可用性升级 域12:
 * AI 输出不得伪造).
 */

export type LeadScoreDimKey =
  "case_value" | "conversion_probability" | "strategic_value" | "risk_level";

export interface LeadScoreDimension {
  key: LeadScoreDimKey;
  /** Raw points achieved (e.g. 25 of max 30). */
  score: number;
  /** Dimension weight (PRD §3.2: 30/30/25/15). */
  max: number;
  /** Human-readable factor explanations. */
  factors: string[];
}

export interface LeadScoreReport {
  /** Weighted total (0-100). */
  total: number;
  dimensions: LeadScoreDimension[];
  priority?: string;
  suggestedAttorney?: string;
  reason?: string;
}

/** PRD 02.2.4 §3.2 weights: 案件价值 30 + 转化概率 30 + 战略价值 25 + 风险评估 15. */
export const LEAD_SCORE_MAX: Record<LeadScoreDimKey, number> = {
  case_value: 30,
  conversion_probability: 30,
  strategic_value: 25,
  risk_level: 15,
};

const DIM_KEYS = Object.keys(LEAD_SCORE_MAX) as LeadScoreDimKey[];

function toNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    // Tolerate "25", "25/30", " 25 分"
    const m = v.match(/-?\d+(\.\d+)?/);
    if (m) return Number(m[0]);
  }
  return null;
}

function parseFactors(v: unknown): string[] {
  if (Array.isArray(v)) {
    return v.filter((f): f is string => typeof f === "string" && f.trim().length > 0);
  }
  if (v && typeof v === "object") {
    // { estimated_fee: "…", case_complexity: "…" } → values
    return Object.values(v).filter(
      (f): f is string => typeof f === "string" && f.trim().length > 0,
    );
  }
  return [];
}

/**
 * Normalize one dimension value. Accepts:
 *   25 | "25/30" | { score: 25, factors: [...] | {...} }
 */
function parseDimension(key: LeadScoreDimKey, v: unknown): LeadScoreDimension | null {
  const max = LEAD_SCORE_MAX[key];
  if (v == null) return null;
  if (typeof v === "number" || typeof v === "string") {
    const score = toNumber(v);
    if (score == null) return null;
    return { key, score, max, factors: [] };
  }
  if (typeof v === "object") {
    const obj = v as Record<string, unknown>;
    const score = toNumber(obj.score ?? obj.value ?? obj.points);
    if (score == null) return null;
    return { key, score, max, factors: parseFactors(obj.factors ?? obj.reasons) };
  }
  return null;
}

/**
 * Parse a raw lead score payload into a report.
 * Returns null when no dimension breakdown is available (caller must NOT
 * fabricate one).
 */
export function parseLeadScoreReport(raw: unknown): LeadScoreReport | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;

  // Score report may be nested (lead detail: { score: { dimensions, … } })
  const container =
    obj.dimensions != null
      ? obj
      : obj.score && typeof obj.score === "object"
        ? (obj.score as Record<string, unknown>)
        : null;
  if (!container || container.dimensions == null || typeof container.dimensions !== "object") {
    return null;
  }

  const dimsObj = container.dimensions as Record<string, unknown>;
  const dimensions: LeadScoreDimension[] = [];
  for (const key of DIM_KEYS) {
    const dim = parseDimension(key, dimsObj[key]);
    if (dim) dimensions.push(dim);
  }
  if (dimensions.length === 0) return null;

  const sum = dimensions.reduce((acc, d) => acc + d.score, 0);
  const totalRaw = toNumber(
    container.total_score ?? obj.total_score ?? obj.priority_score ?? container.total,
  );
  const total = totalRaw != null ? totalRaw : sum;

  const rec =
    container.recommendation && typeof container.recommendation === "object"
      ? (container.recommendation as Record<string, unknown>)
      : obj.recommendation && typeof obj.recommendation === "object"
        ? (obj.recommendation as Record<string, unknown>)
        : null;

  return {
    total: Math.round(total),
    dimensions,
    priority: typeof rec?.priority === "string" ? rec.priority : undefined,
    suggestedAttorney:
      typeof rec?.suggested_attorney === "string" ? rec.suggested_attorney : undefined,
    reason: typeof rec?.reason === "string" ? rec.reason : undefined,
  };
}
