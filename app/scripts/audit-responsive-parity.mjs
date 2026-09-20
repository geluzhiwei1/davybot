#!/usr/bin/env node
/**
 * 响应式审计(方案 Phase 4 治理:ratchet 门禁,防退化)。
 *
 * 三项扫描(src 下 .ts/.tsx;排除 locales 文案 / *.gen.* 生成物 / 测试文件):
 *  1. bare   裸固定宽度 arbitrary 类(w/min-w/max-w-[Npx|Nrem] 且无断点前缀)
 *            —— 手机上直接钉死宽度是横向溢出的头号成因;表单托底等有意保留的
 *            例外进基线白名单
 *  2. touch  触控目标高危(h-6/h-7/size-6/size-7 无前缀出现在疑似可点元素行)
 *            —— Phase 1 按钮基线为 <md 40px,新增 h-6/h-7 可点元素视为回退
 *  3. routes routes/ 下 className 密集(≥10 处)却零断点前缀的页面
 *            —— 新页面必须带响应式断点(small 屏幕 DNA)
 *
 * 存量违规冻结在 scripts/responsive-baseline.json(只许降不许升):
 *  - npm run audit:responsive              # 审计:出现新增违规 exit 1
 *  - npm run audit:responsive -- --update  # 有意接纳现状/清理后重新生成基线
 */
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const SRC = path.join(ROOT, "src");
const BASELINE_FILE = path.join(ROOT, "scripts", "responsive-baseline.json");
const UPDATE = process.argv.includes("--update");

const SKIP_DIRS = new Set(["locales"]); // src/lib/locales:纯文案,无样式类
const SKIP_FILE = /\.(test|spec)\.(ts|tsx)$|\.gen\.(ts|tsx)$/;

function walk(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) {
      if (!SKIP_DIRS.has(e.name)) walk(path.join(dir, e.name), out);
    } else if (/\.(ts|tsx)$/.test(e.name) && !SKIP_FILE.test(e.name)) {
      out.push(path.join(dir, e.name));
    }
  }
  return out;
}

// 无断点前缀的固定宽度(sm:w-[520px] 之类被 lookbehind 排除;动态 `${}` 模板天然不匹配)
const BARE_W = /(?<![\w:.\\/-])(?:min-|max-)?w-\[\d+(?:\.\d+)?(?:px|rem)\]/g;
// 无前缀的小尺寸(触控目标 < 32px);md:h-6 之类仅桌面收缩,不构成移动端风险
const SMALL_SIZE = /(?<![\w:.\\/-])(?:h|size)-[67]\b/;
// 疑似可点元素(行级启发;配合 ratchet 只拦新增,误报压力为零)
const INTERACTIVE =
  /onClick|<Button|<Link|role="button"|<DropdownMenuItem|<SelectTrigger|<TabsTrigger/;
// 断点前缀(须像类名:前面是空白/引号,后面是字母或 [)
const BP_PREFIX = /(?:^|[\s"'`])(?:min-|max-)?(?:sm|md|lg|xl|2xl):[\w[]/;

const files = walk(SRC).sort();
const bare = {};
const touch = {};
const routesUnresponsive = [];
const examples = { bare: {}, touch: {} };

for (const abs of files) {
  const rel = path.relative(ROOT, abs).split(path.sep).join("/");
  const src = readFileSync(abs, "utf-8");
  const lines = src.split("\n");

  let bareCount = 0;
  let touchCount = 0;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const m of line.matchAll(BARE_W)) {
      bareCount++;
      if ((examples.bare[rel] ??= []).length < 3) examples.bare[rel].push(`${i + 1}: ${m[0]}`);
    }
    if (SMALL_SIZE.test(line) && INTERACTIVE.test(line)) {
      touchCount++;
      if ((examples.touch[rel] ??= []).length < 3)
        examples.touch[rel].push(`${i + 1}: ${line.trim().slice(0, 72)}`);
    }
  }
  if (bareCount) bare[rel] = bareCount;
  if (touchCount) touch[rel] = touchCount;

  if (
    rel.startsWith("src/routes/") &&
    (src.match(/className/g) ?? []).length >= 10 &&
    !BP_PREFIX.test(src)
  ) {
    routesUnresponsive.push(rel);
  }
}

// ── 基线对比(ratchet:计数只许降不许升)─────────────────────────
let baseline = { bare: {}, touch: {}, routesUnresponsive: [] };
try {
  baseline = JSON.parse(readFileSync(BASELINE_FILE, "utf-8"));
} catch {
  if (!UPDATE) {
    console.error("✗ 基线文件缺失,先运行:npm run audit:responsive -- --update");
    process.exit(1);
  }
}

const violations = [];
const fmt = (n) => `+${n}`;
for (const [rel, count] of Object.entries(bare)) {
  const delta = count - (baseline.bare[rel] ?? 0);
  if (delta > 0)
    violations.push({ file: rel, kind: "bare固定宽度", delta: fmt(delta), ex: examples.bare[rel] });
}
for (const [rel, count] of Object.entries(touch)) {
  const delta = count - (baseline.touch[rel] ?? 0);
  if (delta > 0)
    violations.push({
      file: rel,
      kind: "触控高危(h-6/h-7 可点)",
      delta: fmt(delta),
      ex: examples.touch[rel],
    });
}
for (const rel of routesUnresponsive) {
  if (!baseline.routesUnresponsive.includes(rel))
    violations.push({ file: rel, kind: "routes 零断点页面", delta: "+1", ex: [] });
}

if (UPDATE) {
  writeFileSync(
    BASELINE_FILE,
    JSON.stringify(
      {
        $comment:
          "响应式审计基线(ratchet)——存量违规冻结,只许降不许升。有意接纳新例外时:npm run audit:responsive -- --update",
        bare,
        touch,
        routesUnresponsive,
      },
      null,
      2,
    ) + "\n",
  );
  console.log(
    `基线已更新:${Object.keys(bare).length} 文件 ${Object.values(bare).reduce((a, b) => a + b, 0)} 处 bare / ` +
      `${Object.keys(touch).length} 文件 ${Object.values(touch).reduce((a, b) => a + b, 0)} 处 touch / ` +
      `${routesUnresponsive.length} 个零断点 routes`,
  );
  process.exit(0);
}

if (violations.length) {
  console.error(`响应式审计失败:${violations.length} 处新增违规(基线外)`);
  for (const v of violations) {
    console.error(`  ✗ ${v.file} [${v.kind}] ${v.delta}`);
    for (const e of v.ex) console.error(`      ${e}`);
  }
  console.error(
    "\n整改(响应式前缀/断点替代裸值),或有意接纳后:npm run audit:responsive -- --update",
  );
  process.exit(1);
}
console.log(
  `响应式审计通过:bare ${Object.values(bare).reduce((a, b) => a + b, 0)} / touch ${Object.values(touch).reduce((a, b) => a + b, 0)} / 零断点 routes ${routesUnresponsive.length} —— 均未超基线`,
);
