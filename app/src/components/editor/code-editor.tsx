/**
 * CodeEditor — CodeMirror 6 wrapper for React.
 * Uses @uiw/react-codemirror for integration.
 * Language packs are loaded lazily per-language so the 14 @codemirror/lang-*
 * packages stay out of the main bundle.
 */
import { useEffect, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import type { Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { getLanguageFromPath, type LanguageId } from "./languages";
import { cn } from "@/lib/utils";

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  filePath?: string;
  language?: LanguageId;
  theme?: "light" | "dark";
  readOnly?: boolean;
  className?: string;
  height?: string;
}

/**
 * Lazy loaders — each dynamic import becomes its own rollup chunk,
 * fetched only when that language is first opened.
 */
const LANG_LOADERS: Partial<Record<LanguageId, () => Promise<Extension[]>>> = {
  markdown: () => import("@codemirror/lang-markdown").then((m) => [m.markdownLanguage]),
  json: () => import("@codemirror/lang-json").then((m) => [m.jsonLanguage]),
  python: () => import("@codemirror/lang-python").then((m) => [m.pythonLanguage]),
  javascript: () => import("@codemirror/lang-javascript").then((m) => [m.javascriptLanguage]),
  typescript: () => import("@codemirror/lang-javascript").then((m) => [m.javascriptLanguage]),
  html: () => import("@codemirror/lang-html").then((m) => [m.htmlLanguage]),
  css: () => import("@codemirror/lang-css").then((m) => [m.cssLanguage]),
  xml: () => import("@codemirror/lang-xml").then((m) => [m.xmlLanguage]),
  yaml: () => import("@codemirror/lang-yaml").then((m) => [m.yamlLanguage]),
  sql: () => import("@codemirror/lang-sql").then((m) => [m.sql()]),
  java: () => import("@codemirror/lang-java").then((m) => [m.javaLanguage]),
  cpp: () => import("@codemirror/lang-cpp").then((m) => [m.cppLanguage]),
  rust: () => import("@codemirror/lang-rust").then((m) => [m.rustLanguage]),
  go: () => import("@codemirror/lang-go").then((m) => [m.goLanguage]),
  php: () => import("@codemirror/lang-php").then((m) => [m.phpLanguage]),
};

export function CodeEditor({
  value,
  onChange,
  filePath,
  language,
  theme = "dark",
  readOnly = false,
  className,
  height = "100%",
}: CodeEditorProps) {
  const lang = language ?? (filePath ? getLanguageFromPath(filePath) : "plaintext");
  const loader = LANG_LOADERS[lang];
  const [extensions, setExtensions] = useState<Extension[]>([]);

  useEffect(() => {
    if (!loader) return; // csv/plaintext — no language pack
    let cancelled = false;
    loader().then((exts) => {
      if (!cancelled) setExtensions(exts);
    });
    return () => {
      cancelled = true;
    };
  }, [loader]);

  const finalExtensions = useMemo(() => extensions, [extensions]);

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      extensions={finalExtensions}
      theme={theme === "dark" ? oneDark : undefined}
      readOnly={readOnly}
      height={height}
      className={cn("text-sm", className)}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        bracketMatching: true,
        closeBrackets: true,
        autocompletion: true,
        searchKeymap: true,
        highlightActiveLine: !readOnly,
      }}
    />
  );
}
