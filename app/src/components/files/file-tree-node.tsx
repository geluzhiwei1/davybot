/**
 * FileTreeNode — Recursive tree node for file/folder display.
 * Renders expandable folders and clickable file items.
 */
import { useState, type ReactNode } from "react";
import {
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  Image,
  FileCode,
  FileSpreadsheet,
  File,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface FileTreeItem {
  name: string;
  path: string;
  type: "file" | "folder";
  children?: FileTreeItem[];
}

interface FileTreeNodeProps {
  item: FileTreeItem;
  level: number;
  selectedPath?: string | null;
  onClick?: (item: FileTreeItem) => void;
  renderActions?: (item: FileTreeItem) => ReactNode;
}

function getFileIcon(name: string): LucideIcon {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["png", "jpg", "jpeg", "gif", "svg", "webp", "bmp"].includes(ext)) return Image;
  if (
    [
      "js",
      "ts",
      "jsx",
      "tsx",
      "py",
      "json",
      "yaml",
      "yml",
      "xml",
      "html",
      "css",
      "sh",
      "rs",
      "go",
    ].includes(ext)
  )
    return FileCode;
  if (["csv", "xlsx", "xls", "tsv"].includes(ext)) return FileSpreadsheet;
  if (["md", "txt", "docx", "doc", "pdf", "rtf"].includes(ext)) return FileText;
  return File;
}

export function FileTreeNode({
  item,
  level,
  selectedPath,
  onClick,
  renderActions,
}: FileTreeNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const isFolder = item.type === "folder";
  const selected = !isFolder && selectedPath === item.path;

  const handleClick = () => {
    if (isFolder) {
      setExpanded((e) => !e);
    } else {
      onClick?.(item);
    }
  };

  const Icon = isFolder ? (expanded ? FolderOpen : Folder) : getFileIcon(item.name);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center w-full rounded-sm hover:bg-muted/60 transition",
          selected && "bg-brand/10 text-brand",
        )}
      >
        <button
          onClick={handleClick}
          className="flex items-center gap-1.5 flex-1 min-w-0 px-2 py-1 text-xs text-left"
          style={{ paddingLeft: `${level * 16 + 8}px` }}
        >
          <ChevronRight
            className={cn(
              "w-3 h-3 shrink-0 transition-transform",
              isFolder && expanded && "rotate-90",
              !isFolder && "invisible",
            )}
          />
          <Icon className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{item.name}</span>
        </button>
        {renderActions && (
          <div className="flex items-center gap-0.5 pr-1 opacity-0 group-hover:opacity-100 transition">
            {renderActions(item)}
          </div>
        )}
      </div>
      {isFolder && expanded && item.children && (
        <div>
          {item.children.map((child) => (
            <FileTreeNode
              key={child.path}
              item={child}
              level={level + 1}
              selectedPath={selectedPath}
              onClick={onClick}
              renderActions={renderActions}
            />
          ))}
        </div>
      )}
    </div>
  );
}
