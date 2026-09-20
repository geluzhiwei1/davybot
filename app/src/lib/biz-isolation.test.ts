// F7b(拆库方案 §5.2):核心仓防漂移守卫 —— src/ 内禁止出现指向 biz/ 的引用。
// 核心/开源构建里 biz/ 不在场 = 代码不存在;任何残留 biz 引用都会让开源形态
// 直接编译失败。本测试把该失败提前到 CI(vitest),并给出精确定位。
// 例外:lib/biz-registry.ts —— 组装形态下 assemble 会把它重写为 manifest 聚合
// 注入(核心形态它本身无 biz 引用,豁免不弱化守卫)。除此以外的任何 src 文件
// 在两种形态下都不得指向 biz/。
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(process.cwd(), "src");
const EXEMPT = new Set(["biz-registry.ts"]);

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    return e.isDirectory() ? walk(p) : [p];
  });
}

// 匹配静态/动态导入说明符(说明符即引号内的模块路径)
const SPEC_RE = /(?:\bfrom\s*|\bimport\s*\(?\s*)["']([^"']+)["']/g;
// 指向 biz/ 的说明符:相对路径爬到 biz/、@/ 别名、或裸 biz/
const BIZ_SPEC_RE = /^(?:\.\.\/)+(?:biz\/)|^\.\/biz\/|^@\/biz\/|^biz\//;

describe("F7b 核心仓 biz 隔离守卫", () => {
  it("src/ 内不存在指向 biz/ 的引用(biz-registry.ts 豁免)", () => {
    const offenders: string[] = [];
    for (const file of walk(SRC)) {
      if (!/\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/.test(file)) continue;
      if (EXEMPT.has(file.split("/").pop() ?? "")) continue;
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(SPEC_RE)) {
        if (BIZ_SPEC_RE.test(m[1])) offenders.push(`${file.replace(SRC + "/", "")} → ${m[1]}`);
      }
    }
    expect(
      offenders,
      `核心 src/ 残留 biz 引用(拆库方案 F7b,biz 在开源形态不存在):\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});
