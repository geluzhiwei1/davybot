/**
 * Language detection from file path/extension.
 * Maps file extensions to CodeMirror language support modules.
 */

/** Supported language identifiers */
export type LanguageId =
  | "markdown"
  | "json"
  | "python"
  | "javascript"
  | "typescript"
  | "html"
  | "css"
  | "xml"
  | "yaml"
  | "sql"
  | "java"
  | "cpp"
  | "rust"
  | "go"
  | "php"
  | "csv"
  | "plaintext";

/** Map file extensions to language IDs */
const EXT_MAP: Record<string, LanguageId> = {
  ".md": "markdown",
  ".mdx": "markdown",
  ".json": "json",
  ".jsonc": "json",
  ".json5": "json",
  ".py": "python",
  ".pyw": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".jsx": "javascript",
  ".ts": "typescript",
  ".tsx": "typescript",
  ".mts": "typescript",
  ".html": "html",
  ".htm": "html",
  ".css": "css",
  ".scss": "css",
  ".less": "css",
  ".xml": "xml",
  ".svg": "xml",
  ".drawio": "xml",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sql": "sql",
  ".java": "java",
  ".c": "cpp",
  ".h": "cpp",
  ".cpp": "cpp",
  ".hpp": "cpp",
  ".cc": "cpp",
  ".rs": "rust",
  ".go": "go",
  ".php": "php",
  ".csv": "csv",
  ".tsv": "csv",
  ".sh": "plaintext",
  ".bash": "plaintext",
  ".zsh": "plaintext",
  ".toml": "plaintext",
  ".ini": "plaintext",
  ".cfg": "plaintext",
  ".txt": "plaintext",
  ".log": "plaintext",
  ".env": "plaintext",
  ".dockerfile": "plaintext",
  ".gitignore": "plaintext",
};

/** Detect language from a file path */
export function getLanguageFromPath(filePath: string): LanguageId {
  const lower = filePath.toLowerCase();
  // Check special filenames
  if (lower.endsWith("dockerfile") || lower.endsWith(".dockerfile")) return "plaintext";
  if (lower.endsWith("makefile")) return "plaintext";
  if (lower.endsWith(".gitignore")) return "plaintext";

  // Find last extension
  const dotIdx = lower.lastIndexOf(".");
  if (dotIdx < 0) return "plaintext";
  const ext = lower.slice(dotIdx);
  return EXT_MAP[ext] ?? "plaintext";
}

/** Get a human-readable label for a language */
export function getLanguageLabel(lang: LanguageId): string {
  const labels: Record<LanguageId, string> = {
    markdown: "Markdown",
    json: "JSON",
    python: "Python",
    javascript: "JavaScript",
    typescript: "TypeScript",
    html: "HTML",
    css: "CSS",
    xml: "XML",
    yaml: "YAML",
    sql: "SQL",
    java: "Java",
    cpp: "C/C++",
    rust: "Rust",
    go: "Go",
    php: "PHP",
    csv: "CSV",
    plaintext: "Plain Text",
  };
  return labels[lang];
}
