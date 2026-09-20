/**
 * FileContentArea — Tab-based file viewer/editor.
 * Manages open files, active tab, and routes to the correct editor.
 */
import { lazy, Suspense, useCallback } from "react";
import type { ReactNode } from "react";
import { X, FileText, Download, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { HTMLViewer } from "@/components/editor/html-viewer";
import { MarkdownPreview } from "@/components/editor/markdown-preview";
import { PDFViewer } from "@/components/editor/pdf-viewer";

// 重编辑器按需加载:xlsx/codemirror/docx-preview 等重依赖只在打开对应类型
// 文件时才拉取 chunk,聊天首开与文件树浏览零负担(桌面/移动同受益)。
const CodeEditor = lazy(() =>
  import("@/components/editor/code-editor").then((m) => ({ default: m.CodeEditor })),
);
const CSVEditor = lazy(() =>
  import("@/components/editor/csv-editor").then((m) => ({ default: m.CSVEditor })),
);
const DocxPreview = lazy(() =>
  import("@/components/editor/docx-preview").then((m) => ({ default: m.DocxPreview })),
);
const XlsxPreview = lazy(() =>
  import("@/components/editor/xlsx-preview").then((m) => ({ default: m.XlsxPreview })),
);

/** 重编辑器 chunk 加载期间的占位(居中小 spinner) */
function EditorSuspense({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

export interface OpenFile {
  id: string;
  name: string;
  path: string;
  content: string;
  /** Object URL for binary files (pdf, image, media). Undefined for text files. */
  blobUrl?: string;
  isDirty?: boolean;
  workspaceId: string;
}

interface FileContentAreaProps {
  files: OpenFile[];
  activeFileId: string | null;
  onActiveChange: (id: string) => void;
  onContentChange?: (id: string, content: string) => void;
  onClose: (id: string) => void;
}

/** Get file category from name for editor routing */
function getFileCategory(
  name: string,
):
  | "code"
  | "markdown"
  | "csv"
  | "html"
  | "pdf"
  | "image"
  | "media"
  | "docx"
  | "xlsx"
  | "office"
  | "drawio" {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["md", "mdx", "markdown"].includes(ext)) return "markdown";
  if (["csv", "tsv"].includes(ext)) return "csv";
  if (["html", "htm"].includes(ext)) return "html";
  if (["pdf"].includes(ext)) return "pdf";
  if (["png", "jpg", "jpeg", "gif", "svg", "webp", "bmp"].includes(ext)) return "image";
  if (["mp4", "webm", "mp3", "wav", "ogg"].includes(ext)) return "media";
  if (["docx", "doc", "odt", "rtf"].includes(ext)) return "docx";
  if (["xlsx", "xls", "ods"].includes(ext)) return "xlsx";
  if (["pptx", "ppt"].includes(ext)) return "office";
  if (["drawio"].includes(ext)) return "drawio";
  return "code";
}

export function FileContentArea({
  files,
  activeFileId,
  onActiveChange,
  onContentChange,
  onClose,
}: FileContentAreaProps) {
  const { t } = useTranslation("miscUi");
  const activeFile = files.find((f) => f.id === activeFileId);

  const handleChange = useCallback(
    (content: string) => {
      if (activeFile && onContentChange) {
        onContentChange(activeFile.id, content);
      }
    },
    [activeFile, onContentChange],
  );

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      {files.length > 0 && (
        <div className="flex items-center border-b border-border/60 overflow-x-auto shrink-0 scrollbar-thin">
          {files.map((f) => (
            <button
              key={f.id}
              onClick={() => onActiveChange(f.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs border-r border-border/40 whitespace-nowrap transition-colors",
                f.id === activeFileId
                  ? "bg-background text-foreground border-b-2 border-b-brand"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/40",
              )}
            >
              <FileText className="w-3 h-3 shrink-0" />
              <span className="truncate max-w-[120px]">{f.name}</span>
              {f.isDirty && <span className="w-1.5 h-1.5 rounded-full bg-brand shrink-0" />}
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  onClose(f.id);
                }}
                className="ml-1 p-0.5 rounded hover:bg-muted/60 shrink-0"
              >
                <X className="w-3 h-3" />
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-h-0">
        {!activeFile ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            {t("files.selectFile")}
          </div>
        ) : (
          <FileRenderer file={activeFile} onChange={handleChange} />
        )}
      </div>
    </div>
  );
}

/** Renders the correct editor/viewer based on file type */
function FileRenderer({
  file,
  onChange,
}: {
  file: OpenFile;
  onChange?: (content: string) => void;
}) {
  const { t } = useTranslation("miscUi");
  const category = getFileCategory(file.name);

  switch (category) {
    case "csv":
      return (
        <EditorSuspense>
          <CSVEditor value={file.content} onChange={onChange} />
        </EditorSuspense>
      );

    case "html":
      return <HTMLViewer value={file.content} filename={file.name} />;

    case "pdf":
      return (
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-end gap-2 px-3 py-1.5 border-b border-border/60 shrink-0">
            <a
              href={file.blobUrl}
              download={file.name}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-brand/40"
            >
              <Download className="w-3 h-3" />
              {t("files.download")}
            </a>
          </div>
          <div className="flex-1 min-h-0">
            <PDFViewer url={file.blobUrl} filename={file.name} />
          </div>
        </div>
      );

    case "image":
      return (
        <div className="flex items-center justify-center h-full p-4 bg-muted/20">
          <img
            src={file.blobUrl || file.content}
            alt={file.name}
            className="max-w-full max-h-full object-contain"
          />
        </div>
      );

    case "media":
      return (
        <div className="flex items-center justify-center h-full p-4">
          {file.name.match(/\.(mp4|webm)$/i) ? (
            <video src={file.blobUrl || file.content} controls className="max-w-full max-h-full" />
          ) : (
            <audio src={file.blobUrl || file.content} controls className="w-full max-w-md" />
          )}
        </div>
      );

    case "docx":
      return (
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-end gap-2 px-3 py-1.5 border-b border-border/60 shrink-0">
            {file.name.match(/\.(doc|odt|rtf)$/i) && (
              <span className="text-xs text-muted-foreground/60">
                {t("files.convertedFromOld")}
              </span>
            )}
            <a
              href={file.blobUrl}
              download={file.name}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-brand/40"
            >
              <Download className="w-3 h-3" />
              {t("files.download")}
            </a>
          </div>
          <div className="flex-1 min-h-0">
            <EditorSuspense>
              <DocxPreview blobUrl={file.blobUrl} filename={file.name} />
            </EditorSuspense>
          </div>
        </div>
      );

    case "xlsx":
      return (
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-end gap-2 px-3 py-1.5 border-b border-border/60 shrink-0">
            {file.name.match(/\.(xls|ods)$/i) && (
              <span className="text-xs text-muted-foreground/60">
                {t("files.convertedFromOld")}
              </span>
            )}
            <a
              href={file.blobUrl}
              download={file.name}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-brand/40"
            >
              <Download className="w-3 h-3" />
              {t("files.download")}
            </a>
          </div>
          <div className="flex-1 min-h-0">
            <EditorSuspense>
              <XlsxPreview blobUrl={file.blobUrl} filename={file.name} />
            </EditorSuspense>
          </div>
        </div>
      );

    case "office":
      return (
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          <div className="text-center space-y-2">
            <FileText className="w-8 h-8 mx-auto text-muted-foreground/40" />
            <p>{t("files.pptNotSupported")}</p>
            <a
              href={file.blobUrl}
              download={file.name}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-brand/40"
            >
              <Download className="w-3 h-3" />
              {t("files.downloadFile")}
            </a>
          </div>
        </div>
      );

    case "markdown":
      return (
        <MarkdownPreview value={file.content} workspaceId={file.workspaceId} filePath={file.path} />
      );

    case "code":
    default:
      return (
        <EditorSuspense>
          <CodeEditor value={file.content} filePath={file.name} onChange={onChange} height="100%" />
        </EditorSuspense>
      );
  }
}
