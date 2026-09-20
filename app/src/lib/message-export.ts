/**
 * Message export utilities.
 * Provides extract/copy/download/print for chat message bubbles.
 * No external deps — uses Clipboard API, Blob download, and window.print().
 */
import type { ChatMessage, ContentBlock } from "@/lib/types";

// ── Markdown extraction ────────────────────────────────────────────

/**
 * Extract a plain markdown string from a ChatMessage.
 *  - user: raw content
 *  - assistant with blocks: concatenated `text` blocks (reasoning included if includeReasoning)
 *  - assistant fallback: content || reasoning
 */
export function extractMessageMarkdown(
  message: ChatMessage,
  opts: { includeReasoning?: boolean } = {},
): string {
  const { includeReasoning = false } = opts;

  if (message.role === "user") {
    return message.content ?? "";
  }

  const parts: string[] = [];
  const blocks = message.blocks ?? [];

  if (blocks.length > 0) {
    if (includeReasoning) {
      for (const b of blocks) {
        if (b.type === "reasoning" && b.reasoning?.trim()) {
          parts.push(`> **${"推理"}**\n\n${b.reasoning.trim()}`);
        }
      }
    }
    for (const b of blocks) {
      if (b.type === "text" && b.text?.trim()) {
        parts.push(b.text.trim());
      }
    }
  }

  if (parts.length === 0) {
    // Legacy / fallback path
    const text = message.content?.trim() || message.reasoning?.trim() || "";
    if (text) parts.push(text);
  }

  return parts.join("\n\n");
}

/** Whether a message has any extractable content worth showing actions for. */
export function hasExportableContent(message: ChatMessage): boolean {
  return extractMessageMarkdown(message).trim().length > 0;
}

// ── Copy ───────────────────────────────────────────────────────────

export async function copyMessageMarkdown(message: ChatMessage): Promise<boolean> {
  const text = extractMessageMarkdown(message);
  if (!text) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for non-secure contexts
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

// ── Markdown file download ─────────────────────────────────────────

function downloadBlob(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke on next tick to ensure download starts in some browsers
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function safeFilename(name: string, fallback = "message"): string {
  const cleaned = name.replace(/[\\/:*?"<>|]+/g, "_").trim();
  return cleaned || fallback;
}

export function exportMarkdownFile(message: ChatMessage) {
  const text = extractMessageMarkdown(message);
  if (!text) return;
  const who = message.role === "user" ? "user" : message.agentName || "assistant";
  const ts = new Date(message.ts ?? Date.now());
  const stamp = `${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}`;
  const filename = `${safeFilename(who)}-${stamp}.md`;
  downloadBlob(filename, text, "text/markdown;charset=utf-8");
}

// ── PDF export via browser print ───────────────────────────────────

/**
 * Minimal markdown → HTML converter for print output.
 * Handles: headings, fenced code, blockquote, unordered/ordered lists,
 * bold, italic, inline code, horizontal rule, paragraphs.
 */
export function markdownToHtml(md: string): string {
  const lines = md.split("\n");
  const html: string[] = [];
  let inCode = false;
  let codeBuf: string[] = [];
  let listType: "ul" | "ol" | null = null;

  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const inline = (s: string) => {
    let out = escape(s);
    // inline code first to protect contents
    out = out.replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`);
    // bold
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // italic
    out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return out;
  };

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const raw of lines) {
    const line = raw;

    if (line.startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${escape(codeBuf.join("\n"))}</code></pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(line);
      continue;
    }

    // Horizontal rule
    if (/^---+\s*$/.test(line)) {
      closeList();
      html.push("<hr/>");
      continue;
    }
    // Headings
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      closeList();
      const level = Math.min(h[1].length, 6);
      html.push(`<h${level}>${inline(h[2])}</h${level}>`);
      continue;
    }
    // Blockquote
    if (line.startsWith("> ")) {
      closeList();
      html.push(`<blockquote>${inline(line.slice(2))}</blockquote>`);
      continue;
    }
    // Unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${inline(line.replace(/^\s*[-*+]\s+/, ""))}</li>`);
      continue;
    }
    // Ordered list
    const ol = /^\s*(\d+)\.\s+(.*)$/.exec(line);
    if (ol) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${inline(ol[2])}</li>`);
      continue;
    }
    // Empty line
    if (line.trim() === "") {
      closeList();
      continue;
    }
    // Paragraph
    closeList();
    html.push(`<p>${inline(line)}</p>`);
  }

  if (inCode && codeBuf.length > 0) {
    html.push(`<pre><code>${escape(codeBuf.join("\n"))}</code></pre>`);
  }
  closeList();

  return html.join("\n");
}

/** 手机尺寸视口:window.open 打印窗不可靠(弹窗拦截 / iOS 无打印对话框)。 */
function isMobileViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
}

/**
 * Build the standalone styled HTML document for a chat message.
 * `autoPrint` injects the print trigger — kept for the desktop print window,
 * disabled for the mobile HTML download (opens silently, no print dialog).
 */
function buildMessageDocument(
  title: string,
  who: string,
  tsLabel: string,
  body: string,
  autoPrint: boolean,
): string {
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(title)}</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", Helvetica, Arial, sans-serif;
    color: #111;
    background: #fff;
    margin: 0;
    padding: 40px 48px;
    line-height: 1.65;
    font-size: 14px;
  }
  header {
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 12px;
    margin-bottom: 20px;
  }
  .who { font-weight: 600; font-size: 15px; }
  .ts { color: #6b7280; font-size: 12px; margin-left: 8px; }
  h1, h2, h3, h4, h5, h6 { margin: 1.2em 0 0.4em; line-height: 1.3; }
  h1 { font-size: 22px; }
  h2 { font-size: 18px; }
  h3 { font-size: 16px; }
  p { margin: 0.5em 0; }
  ul, ol { margin: 0.5em 0; padding-left: 1.6em; }
  li { margin: 0.2em 0; }
  blockquote {
    margin: 0.6em 0;
    padding: 2px 12px;
    border-left: 3px solid #d1d5db;
    color: #4b5563;
    background: #f9fafb;
  }
  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9em;
    background: #f3f4f6;
    padding: 1px 5px;
    border-radius: 4px;
  }
  pre {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 12px 14px;
    overflow-x: auto;
    margin: 0.8em 0;
  }
  pre code { background: none; padding: 0; font-size: 12px; }
  hr { border: none; border-top: 1px solid #e5e7eb; margin: 1em 0; }
  table { border-collapse: collapse; margin: 0.6em 0; }
  th, td { border: 1px solid #d1d5db; padding: 6px 10px; }
  @media print {
    body { padding: 0; }
    @page { margin: 16mm; }
  }
</style>
</head>
<body>
  <header>
    <span class="who">${escapeHtml(who)}</span>
    <span class="ts">${escapeHtml(tsLabel)}</span>
  </header>
  <main>
    ${body}
  </main>${
    autoPrint
      ? `
  <script>
    // Trigger print once layout is ready
    window.addEventListener('load', function () {
      setTimeout(function () { window.print(); }, 120);
    });
  </script>
`
      : ""
  }</body>
</html>`;
}

/**
 * Open a print-friendly window with rendered message HTML.
 * The browser's print dialog lets the user "Save as PDF".
 * On mobile the print popup is unusable — download the styled HTML instead.
 */
export function printMessagePdf(message: ChatMessage) {
  const md = extractMessageMarkdown(message);
  if (!md) return;

  const who = message.role === "user" ? "我" : message.agentName || "智能体";
  const ts = message.ts ? new Date(message.ts) : new Date();
  const tsLabel = `${ts.getFullYear()}-${pad(ts.getMonth() + 1)}-${pad(ts.getDate())} ${pad(ts.getHours())}:${pad(ts.getMinutes())}`;
  const title = `${who} - ${tsLabel}`;
  const body = markdownToHtml(md);

  // 移动端:导出为带样式的 HTML 文件(可在手机浏览器/分享中打开,再另存 PDF)
  if (isMobileViewport()) {
    const stamp = `${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}`;
    downloadBlob(
      `${safeFilename(who === "我" ? "user" : who)}-${stamp}.html`,
      buildMessageDocument(title, who, tsLabel, body, false),
      "text/html;charset=utf-8",
    );
    return;
  }

  const win = window.open("", "_blank", "width=820,height=900");
  if (!win) return;

  const doc = win.document;
  doc.open();
  doc.write(buildMessageDocument(title, who, tsLabel, body, true));
  doc.close();
}

// ── helpers ────────────────────────────────────────────────────────

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Type guard helper to silence TS when iterating blocks above (kept for clarity)
export type { ContentBlock };
