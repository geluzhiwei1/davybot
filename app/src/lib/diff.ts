/**
 * 行级 diff（LCS 动态规划）— GATE-0 dao.md 版本对比（PRD §10 #5 产物 diff 视图）。
 *
 * 零依赖实现：dao.md 量级（数百行）下 O(n·m) 完全可接受。
 */

export type DiffLineType = "same" | "add" | "del";

export interface DiffLine {
  type: DiffLineType;
  /** 旧版行号（add 行为 null） */
  oldNo: number | null;
  /** 新版行号（del 行为 null） */
  newNo: number | null;
  text: string;
}

/** 计算两段文本的行级 diff（旧 → 新）。 */
export function diffLines(oldText: string, newText: string): DiffLine[] {
  const a = (oldText ?? "").split("\n");
  const b = (newText ?? "").split("\n");
  const n = a.length;
  const m = b.length;

  // LCS 长度表（从后往前填）
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  // 回溯输出
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  let oldNo = 0;
  let newNo = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      oldNo += 1;
      newNo += 1;
      out.push({ type: "same", oldNo, newNo, text: a[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      oldNo += 1;
      out.push({ type: "del", oldNo, newNo: null, text: a[i] });
      i += 1;
    } else {
      newNo += 1;
      out.push({ type: "add", oldNo: null, newNo, text: b[j] });
      j += 1;
    }
  }
  while (i < n) {
    oldNo += 1;
    out.push({ type: "del", oldNo, newNo: null, text: a[i] });
    i += 1;
  }
  while (j < m) {
    newNo += 1;
    out.push({ type: "add", oldNo: null, newNo, text: b[j] });
    j += 1;
  }
  return out;
}

/** 变更统计（+x / -y）。 */
export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const l of lines) {
    if (l.type === "add") added += 1;
    else if (l.type === "del") removed += 1;
  }
  return { added, removed };
}
