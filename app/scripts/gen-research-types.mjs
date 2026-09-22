#!/usr/bin/env node
/**
 * 从 apps/gelu-research-flow/openapi.json 生成 src/lib/research/types.ts(设计 §5/§8 P5:OpenAPI types CI 门禁)。
 *
 * 用法:
 *   node scripts/gen-research-types.mjs           # 生成/更新 types.ts(banner 前置)
 *   node scripts/gen-research-types.mjs --check   # CI 门禁:重生成到临时文件与入仓文件比对,漂移 exit 1
 *
 * 约定:后端改路由/模型后,先在 apps/gelu-research-flow 执行
 *   uv run python scripts/export_openapi.py
 * 再回到本目录执行 npm run gen:research-types 提交两侧产物。
 */
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const SPEC = join(ROOT, "..", "gelu-research-flow", "openapi.json");
const OUT = join(ROOT, "src", "lib", "research", "types.ts");
const BANNER = `// AUTO-GENERATED from apps/gelu-research-flow/openapi.json — DO NOT EDIT.
// Regenerate: cd apps/gelu-research-flow && uv run python scripts/export_openapi.py && \\
//             cd ../davybot/app && npm run gen:research-types
`;

if (!existsSync(SPEC)) {
  console.error(`找不到 OpenAPI 规范: ${SPEC}(先在 gelu-research-flow 执行 export_openapi.py)`);
  process.exit(1);
}

const check = process.argv.includes("--check");
const target = check ? join(mkdtempSync(join(tmpdir(), "grt-")), "types.ts") : OUT;

const res = spawnSync(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["openapi-typescript", SPEC, "-o", target],
  { stdio: "inherit", cwd: ROOT },
);
if (res.status !== 0) process.exit(res.status ?? 1);

const body = BANNER + readFileSync(target, "utf8");

if (check) {
  const committed = readFileSync(OUT, "utf8");
  if (committed === body) {
    console.log("research types.ts OK(与 openapi.json 一致)");
    rmSync(dirname(target), { recursive: true, force: true });
  } else {
    console.error("research types.ts 漂移:openapi.json 已变但 types.ts 未重新生成。");
    console.error("执行:npm run gen:research-types 并提交。");
    rmSync(dirname(target), { recursive: true, force: true });
    process.exit(1);
  }
} else {
  writeFileSync(OUT, body);
  console.log(`生成 ${OUT}`);
}
