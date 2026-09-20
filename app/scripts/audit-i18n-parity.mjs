#!/usr/bin/env node
/**
 * i18n 键对齐审计(设计 §8 P5:i18n 审计门禁)。
 *
 * 对比 src/lib/locales/{zh-CN,en-US}/ 下同名 .ts 文件的键集合:
 *  - 文件只存在一侧 → 报错
 *  - 键缺失(含嵌套展平后的点路径)→ 报错
 * 用法:npm run audit:i18n     # 任一不对齐 exit 1(CI/预提交门禁)
 */
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const LOCALES = path.join(ROOT, "src", "lib", "locales");
const LANGS = ["zh-CN", "en-US"];

/**
 * 解析 locale .ts → 递归展平为点路径键集。
 * 兼容两种形态:`export default {…};` 与 `const zhCN = {…}; export default zhCN;`
 * 取首个顶层对象字面量做括号配平(字符串内的 {} / 注释 / as const 尾巴均不影响)。
 */
function extractObjLiteral(src, file) {
  const anchor = src.search(/export\s+default\s*\{|const\s+\w+\s*=\s*\{/);
  if (anchor < 0) throw new Error(`无法解析(找不到对象字面量): ${file}`);
  const start = src.indexOf("{", anchor);
  let depth = 0;
  let quote = null;
  let esc = false;
  for (let i = start; i < src.length; i++) {
    const c = src[i];
    if (quote) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") quote = c;
    else if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return src.slice(start, i + 1);
  }
  throw new Error(`无法解析(花括号不配平): ${file}`);
}

function extractKeys(file) {
  const src = readFileSync(file, "utf-8");
  const obj = new Function(`return (${extractObjLiteral(src, file)})`)();
  const keys = new Set();
  (function walk(node, prefix) {
    for (const [k, v] of Object.entries(node)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === "object") walk(v, key);
      else keys.add(key);
    }
  })(obj, "");
  return keys;
}

const files = Object.fromEntries(
  LANGS.map((l) => [l, readdirSync(path.join(LOCALES, l)).filter((f) => f.endsWith(".ts"))]),
);
const all = [...new Set(LANGS.flatMap((l) => files[l]))].sort();
let bad = 0;

for (const f of all) {
  const missing = LANGS.filter((l) => !files[l].includes(f));
  if (missing.length) {
    console.error(`✗ ${f}: 缺失于 ${missing.join(", ")}`);
    bad++;
    continue;
  }
  const [a, b] = LANGS.map((l) => extractKeys(path.join(LOCALES, l, f)));
  const diffs = [
    ...[...a].filter((k) => !b.has(k)).map((k) => `en-US 缺 «${k}»`),
    ...[...b].filter((k) => !a.has(k)).map((k) => `zh-CN 缺 «${k}»`),
  ];
  if (diffs.length) {
    console.error(`✗ ${f}: ${diffs.length} 处不对齐`);
    for (const d of diffs) console.error(`    ${d}`);
    bad++;
  }
}

if (bad) {
  console.error(`\ni18n 审计失败:${bad} 个文件不对齐(zh-CN/en-US)`);
  process.exit(1);
}
console.log(`i18n 审计通过:${all.length} 个文件 zh-CN/en-US 键完全对齐`);
