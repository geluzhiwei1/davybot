/**
 * Chat bubble markdown renderer — react-markdown + remark-gfm.
 * Supports GFM tables, headings, lists, code blocks, blockquotes, etc.
 */
import { type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const REMARK_PLUGINS = [remarkGfm];

// 流式渲染优化(方案 Phase 3.2):components/remarkPlugins 提升到模块级常量。
// 若每次调用内联创建,react-markdown 会把它们当作"新组件类型"而整树卸载重挂
// —— 流式场景下每次 chunk 刷新都重挂全部 markdown 子树,是长对话卡顿主因之一。
const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="font-bold text-xl mt-4 mb-2">{children}</h1>,
  h2: ({ children }) => <h2 className="font-semibold text-lg mt-4 mb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="font-semibold text-base mt-3 mb-1">{children}</h3>,
  p: ({ children }) => <p className="leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="ml-5 list-disc space-y-0.5 my-1">{children}</ul>,
  ol: ({ children }) => <ol className="ml-5 list-decimal space-y-0.5 my-1">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-brand/60 pl-3 my-2 text-muted-foreground italic">
      {children}
    </blockquote>
  ),
  pre: ({ children }) => (
    <pre className="bg-muted/80 rounded-md p-3 my-2 overflow-x-auto text-xs font-mono">
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock)
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    return (
      <code className="px-1.5 py-0.5 rounded bg-muted/80 text-xs font-mono text-brand" {...props}>
        {children}
      </code>
    );
  },
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full text-xs border-collapse border border-border rounded-md">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/60 font-semibold">{children}</thead>,
  th: ({ children }) => <th className="border border-border px-2 py-1.5 text-left">{children}</th>,
  td: ({ children }) => <td className="border border-border px-2 py-1.5">{children}</td>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-brand underline underline-offset-2"
    >
      {children}
    </a>
  ),
};

export function renderMarkdown(text: string): ReactNode {
  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>
      {text}
    </ReactMarkdown>
  );
}
