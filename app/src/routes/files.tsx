/**
 * Files Route — File browser and editor page.
 * Split layout: file tree sidebar + content area with tabs.
 */
import { useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { FolderOpen } from "lucide-react";
import { FileTreeNode, type FileTreeItem } from "@/components/files/file-tree-node";
import { FileContentArea, type OpenFile } from "@/components/files/file-content-area";
import { useStore } from "@/lib/store";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/files")({
  component: FilesPage,
});

/** Demo file tree for preview purposes */
const DEMO_TREE: FileTreeItem[] = [
  {
    name: "合同文件",
    path: "/contracts",
    type: "folder",
    children: [
      { name: "股东协议草案.pdf", path: "/contracts/shareholder.pdf", type: "file" },
      { name: "保密协议.md", path: "/contracts/nda.md", type: "file" },
      { name: "尽调备忘录.docx", path: "/contracts/due-diligence.docx", type: "file" },
    ],
  },
  {
    name: "财务资料",
    path: "/finance",
    type: "folder",
    children: [
      { name: "目标公司财务报表.csv", path: "/finance/financials.csv", type: "file" },
      { name: "估值模型.py", path: "/finance/valuation.py", type: "file" },
    ],
  },
  {
    name: "AI 产出",
    path: "/ai",
    type: "folder",
    children: [
      { name: "风险摘要.md", path: "/ai/risk-summary.md", type: "file" },
      { name: "合规要点.md", path: "/ai/compliance.md", type: "file" },
      { name: "分析报告.html", path: "/ai/report.html", type: "file" },
    ],
  },
];

/** Sample content for demo files */
const DEMO_CONTENT: Record<string, string> = {
  "/contracts/nda.md": `# 保密协议 (NDA)

## 甲方
**公司名称**: [待填写]

## 乙方
**公司名称**: [待填写]

## 保密信息范围
1. 技术数据和专有技术
2. 商业计划和财务信息
3. 客户名单和供应商信息
4. 任何一方明确标记为"保密"的信息

## 保密期限
本协议自签署之日起 **三年** 内有效。

## 违约责任
违反本协议的一方应赔偿因此造成的一切直接和间接损失。
`,
  "/finance/financials.csv": `年度,营业收入(万元),净利润(万元),总资产(万元),负债率
2021,15,000,2,300,45,000,32%
2022,18,500,3,100,52,000,28%
2023,22,000,4,800,61,000,25%
2024,26,500,6,200,73,000,22%`,
  "/finance/valuation.py": `"""
DCG Valuation Model — Discounted Cash Flow
"""
import numpy as np

def dcf_value(
    cash_flows: list[float],
    discount_rate: float = 0.10,
    terminal_growth: float = 0.03,
) -> float:
    """Calculate DCF enterprise value."""
    # PV of explicit cash flows
    pv_cf = sum(
        cf / (1 + discount_rate) ** i
        for i, cf in enumerate(cash_flows, 1)
    )
    # Terminal value
    terminal = cash_flows[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal / (1 + discount_rate) ** len(cash_flows)
    return pv_cf + pv_terminal

if __name__ == "__main__":
    projected = [4500, 5200, 6000, 7000, 8200]
    ev = dcf_value(projected)
    print(f"Enterprise Value: ¥{ev:,.0f} 万")
`,
  "/ai/risk-summary.md": `# 投资风险摘要

## 高风险项
| # | 风险 | 严重程度 | 建议 |
|---|------|---------|------|
| 1 | 目标公司存在关联交易 | 高 | 要求独立审计 |
| 2 | 知识产权归属不明确 | 高 | 补充IP尽调 |
| 3 | 核心团队竞业限制缺失 | 中 | 补签竞业协议 |

## 合规要点
- 跨境数据传输需符合《数据安全法》
- VIE 结构需审查实际控制人变更风险
- 目标公司 2023 年营收增长 19%，但毛利率下降 3%
`,
  "/ai/compliance.md": `# 合规检查清单

## 已通过项 ✅
- [x] 公司注册文件齐全
- [x] 营业执照有效期内
- [x] 税务登记正常
- [x] 社保缴纳合规

## 待补充项 ⚠️
- [ ] 环保审批文件
- [ ] 数据安全评估报告
- [ ] 反垄断申报（如适用）

## 高优先级
1. 完成网络安全等级保护备案
2. 更新隐私政策和用户协议
3. 跨境数据传输安全评估
`,
  "/ai/report.html": `<!DOCTYPE html>
<html>
<head><title>AI 分析报告</title></head>
<body>
<h1>AI 投资分析报告</h1>
<p>本报告由 AI 法律智能体自动生成。</p>
<h2>摘要</h2>
<p>基于对目标公司的财务、法律、运营等方面的综合分析，AI 智能体识别出 <strong>3 个高风险项</strong> 和 <strong>5 个中风险项</strong>。</p>
<h2>建议</h2>
<ul>
  <li>优先处理知识产权归属问题</li>
  <li>补充环保审批文件</li>
  <li>完成数据安全评估</li>
</ul>
</body>
</html>`,
};

function FilesPage() {
  const { t } = useTranslation("routesA");
  const workspaces = useStore((s) => s.workspaces);
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);

  const handleFileClick = useCallback(
    (item: FileTreeItem) => {
      // Check if already open
      const existing = openFiles.find((f) => f.path === item.path);
      if (existing) {
        setActiveFileId(existing.id);
        return;
      }
      // Open new file with demo content
      const id = `file-${Date.now()}`;
      const content = DEMO_CONTENT[item.path] ?? `// ${item.name}\n// 文件内容将在此处加载\n`;
      setOpenFiles((prev) => [
        ...prev,
        {
          id,
          path: item.path,
          name: item.name,
          content,
          isDirty: false,
          workspaceId: workspaces[0]?.id ?? "demo",
        },
      ]);
      setActiveFileId(id);
    },
    [openFiles],
  );

  const handleClose = useCallback(
    (id: string) => {
      setOpenFiles((prev) => {
        const next = prev.filter((f) => f.id !== id);
        if (activeFileId === id) {
          setActiveFileId(next.length > 0 ? next[next.length - 1].id : null);
        }
        return next;
      });
    },
    [activeFileId],
  );

  const handleContentChange = useCallback((id: string, content: string) => {
    setOpenFiles((prev) => prev.map((f) => (f.id === id ? { ...f, content, isDirty: true } : f)));
  }, []);

  return (
    <div className="flex h-full">
      {/* File tree sidebar */}
      <div className="w-60 border-r border-border/60 flex flex-col shrink-0">
        <div className="px-3 py-2 border-b border-border/60">
          <span className="text-xs font-medium">{t("files.browser")}</span>
        </div>

        {workspaces.length > 0 && (
          <div className="px-3 py-1.5">
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <FolderOpen className="w-3 h-3" />
              {t("files.currentWorkspace", { name: workspaces[0].name })}
            </div>
          </div>
        )}

        <div className="flex-1 overflow-auto py-1 scrollbar-thin">
          {DEMO_TREE.map((item) => (
            <FileTreeNode
              key={item.path}
              item={item}
              level={0}
              selectedPath={null}
              onClick={handleFileClick}
            />
          ))}
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 min-w-0">
        <FileContentArea
          files={openFiles}
          activeFileId={activeFileId}
          onActiveChange={setActiveFileId}
          onContentChange={handleContentChange}
          onClose={handleClose}
        />
      </div>
    </div>
  );
}
