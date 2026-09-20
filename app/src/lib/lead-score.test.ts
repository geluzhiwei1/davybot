import { describe, expect, it } from "vitest";
import { LEAD_SCORE_MAX, parseLeadScoreReport } from "./lead-score";

describe("parseLeadScoreReport (A5 评分诚实化)", () => {
  it("parses PRD §3.2 shape: dimensions with {score, factors} + weighted total", () => {
    const report = parseLeadScoreReport({
      total_score: 78,
      dimensions: {
        case_value: { score: 25, factors: { estimated_fee: "预计5-10万", complexity: "中等" } },
        conversion_probability: { score: 22, factors: ["客户紧急", "预算匹配"] },
        strategic_value: { score: 18, factors: ["律所优势领域"] },
        risk_level: { score: 13, factors: [] },
      },
      recommendation: { priority: "高", suggested_attorney: "王律师", reason: "专业匹配" },
    });
    expect(report).not.toBeNull();
    expect(report!.total).toBe(78);
    expect(report!.dimensions).toHaveLength(4);
    expect(report!.dimensions[0]).toMatchObject({ key: "case_value", score: 25, max: 30 });
    expect(report!.dimensions[0].factors).toEqual(["预计5-10万", "中等"]);
    expect(report!.dimensions[1].factors).toEqual(["客户紧急", "预算匹配"]);
    expect(report!.suggestedAttorney).toBe("王律师");
    expect(report!.priority).toBe("高");
  });

  it("parses flat numeric dimensions and string scores ('25/30'), sums total when absent", () => {
    const report = parseLeadScoreReport({
      dimensions: { case_value: 25, conversion_probability: "22/30" },
    });
    expect(report!.dimensions).toHaveLength(2);
    expect(report!.total).toBe(47);
  });

  it("unwraps lead-detail nesting: { score: { dimensions, … } }", () => {
    const report = parseLeadScoreReport({
      name: "LEAD-1",
      score: { total_score: 60, dimensions: { case_value: 20, risk_level: 10 } },
    });
    expect(report!.total).toBe(60);
    expect(report!.dimensions.map((d) => d.key)).toEqual(["case_value", "risk_level"]);
  });

  it("returns null when only aggregate score exists (caller must not fabricate)", () => {
    expect(parseLeadScoreReport({ priority_score: 78 })).toBeNull();
    expect(parseLeadScoreReport({ dimensions: {} })).toBeNull();
    expect(parseLeadScoreReport({ dimensions: { case_value: null } })).toBeNull();
    expect(parseLeadScoreReport(null)).toBeNull();
    expect(parseLeadScoreReport("78")).toBeNull();
  });

  it("dimension weights match PRD §3.2 (30/30/25/15 = 100)", () => {
    expect(Object.values(LEAD_SCORE_MAX).reduce((a, b) => a + b, 0)).toBe(100);
  });
});
