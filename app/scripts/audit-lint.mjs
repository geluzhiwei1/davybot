#!/usr/bin/env node
/**
 * Lint ratchet 门禁(方案 Phase 4 治理:清完 72 处 no-explicit-any 错误后,
 * 剩余 211 条 warnings 全量修复有行为回归风险,采用只许降不许升的棘轮)。
 *
 * 规则:
 *  - errors   > 0            → 永远 fail(新代码零容忍,FAST FAIL)
 *  - warnings 按规则计数     → 任一规则超过基线 → fail;低于基线 → 提示收口
 *
 * 用法:
 *  - npm run audit:lint              # 审计:有新增 error/warning 即 exit 1
 *  - npm run audit:lint -- --update  # 有意接纳现状/清理后重新生成基线
 *
 * 基线:scripts/lint-baseline.json(总数 + 分规则计数)
 */
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const BASELINE_FILE = path.join(ROOT, "scripts", "lint-baseline.json");
const UPDATE = process.argv.includes("--update");
const ESLINT = path.join(ROOT, "node_modules", ".bin", "eslint");

// ── 跑 eslint(JSON 输出;warnings 不影响退出码,errors 由脚本自判)──
let raw;
try {
  raw = execFileSync(ESLINT, [".", "--format", "json"], {
    cwd: ROOT,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
    stdio: ["ignore", "pipe", "pipe"],
  });
} catch (e) {
  // eslint 对 error 退出码 1,但 --format json 仍会完整输出;其余崩溃才走这里
  raw = e.stdout?.toString();
  if (!raw) {
    console.error("lint audit: eslint 运行失败\n" + (e.stderr?.toString() ?? e.message));
    process.exit(1);
  }
}

const results = JSON.parse(raw);
let totalErrors = 0;
let totalWarnings = 0;
const byRule = {};
for (const file of results) {
  for (const msg of file.messages) {
    const sev = msg.severity; // 1=warning 2=error
    const rule = msg.ruleId ?? "(parse)";
    byRule[rule] ??= { errors: 0, warnings: 0 };
    if (sev === 2) {
      totalErrors++;
      byRule[rule].errors++;
    } else {
      totalWarnings++;
      byRule[rule].warnings++;
    }
  }
}

// ── 基线对比 ────────────────────────────────────────────────────────
let baseline = { totalWarnings: 0, rules: {} };
try {
  baseline = JSON.parse(readFileSync(BASELINE_FILE, "utf-8"));
} catch {
  // 基线缺失视为 0:首次跑必须 --update 或全绿
}

const fail = [];

if (totalErrors > 0) {
  fail.push(`errors: ${totalErrors}(必须为 0)`);
}

for (const [rule, count] of Object.entries(byRule)) {
  const base = baseline.rules?.[rule] ?? 0;
  const cur = count.warnings;
  if (cur > base) fail.push(`${rule}: ${cur} > 基线 ${base}(+${cur - base})`);
}

if (UPDATE) {
  const rules = {};
  for (const [rule, count] of Object.entries(byRule)) {
    if (count.warnings > 0 || count.errors > 0) rules[rule] = count.warnings;
  }
  const next = { totalWarnings, rules };
  writeFileSync(BASELINE_FILE, JSON.stringify(next, null, 2) + "\n");
  console.log(`lint audit: 基线已更新 → errors=${totalErrors}, warnings=${totalWarnings}`);
  process.exit(0);
}

const top = Object.entries(byRule)
  .filter(([, c]) => c.warnings > 0)
  .sort((a, b) => b[1].warnings - a[1].warnings)
  .slice(0, 5)
  .map(([r, c]) => `${r}: ${c.warnings}`)
  .join(", ");

console.log(
  `lint audit: errors=${totalErrors}, warnings=${totalWarnings}(基线 ${baseline.totalWarnings})` +
    (top ? `\n  top: ${top}` : ""),
);

if (fail.length > 0) {
  console.error("\nlint ratchet 违规:");
  for (const f of fail) console.error(`  ✖ ${f}`);
  console.error("修复后重跑;有意接纳现状用 `npm run audit:lint -- --update`");
  process.exit(1);
}

if (totalWarnings < baseline.totalWarnings) {
  console.log(
    `lint audit: warnings 已低于基线(${totalWarnings} < ${baseline.totalWarnings}),` +
      `建议运行 npm run audit:lint -- --update 收口棘轮`,
  );
}

process.exit(0);
