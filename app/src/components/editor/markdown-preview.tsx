/**
 * MarkdownPreview — Renders markdown content as styled HTML.
 * Resolves image src relative paths to workspace file API URLs.
 */
import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { STORAGE_KEYS, getApiBaseUrl } from "@/lib/env";

interface MarkdownPreviewProps {
  /** Raw markdown content */
  value: string;
  /** Workspace ID for resolving image URLs */
  workspaceId: string;
  /** Full path of the markdown file within the workspace (used to resolve relative image paths) */
  filePath: string;
  /** Optional className for the wrapper */
  className?: string;
}

/** Resolve a relative image path against the markdown file's directory */
function resolveRelativePath(src: string, mdFileDir: string): string {
  if (!src || src.startsWith("http://") || src.startsWith("https://") || src.startsWith("data:")) {
    return src;
  }

  // Absolute paths within workspace (start with /)
  if (src.startsWith("/")) {
    return src;
  }

  // Relative path — resolve against markdown file's directory
  // e.g., mdFileDir="/docs/sub", src="./img/photo.png" → "/docs/sub/img/photo.png"
  // e.g., mdFileDir="/docs/sub", src="../shared/logo.png" → "/docs/shared/logo.png"
  const segments = mdFileDir ? mdFileDir.split("/").filter(Boolean) : [];

  for (const part of src.split("/")) {
    if (part === "..") {
      segments.pop();
    } else if (part !== "." && part !== "") {
      segments.push(part);
    }
  }

  return "/" + segments.join("/");
}

/** Build the API URL to fetch a workspace image */
function buildImageUrl(imagePath: string, workspaceId: string, mdFilePath: string): string {
  if (
    !imagePath ||
    imagePath.startsWith("http://") ||
    imagePath.startsWith("https://") ||
    imagePath.startsWith("data:")
  ) {
    return imagePath;
  }

  const currentDir = mdFilePath.includes("/")
    ? mdFilePath.substring(0, mdFilePath.lastIndexOf("/"))
    : "";
  const resolvedPath = resolveRelativePath(imagePath, currentDir);

  const token = localStorage.getItem(STORAGE_KEYS.authToken);

  // Return an API URL that serves the image. Append token as query param for auth
  // since img tags can't set Authorization headers.
  const url = `${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/download?path=${encodeURIComponent(resolvedPath)}`;
  return token ? `${url}&token=${encodeURIComponent(token)}` : url;
}

export function MarkdownPreview({ value, workspaceId, filePath, className }: MarkdownPreviewProps) {
  const components = useMemo(
    () => ({
      img({ src, alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) {
        if (!src) return null;
        const resolvedSrc = buildImageUrl(src, workspaceId, filePath);
        return <img src={resolvedSrc} alt={alt ?? ""} loading="lazy" {...props} />;
      },
      a({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
        return (
          <a href={href} target="_blank" rel="noreferrer" {...props}>
            {children}
          </a>
        );
      },
    }),
    [workspaceId, filePath],
  );

  return (
    <div className={cn("markdown-preview h-full overflow-auto p-6", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {value}
      </ReactMarkdown>
    </div>
  );
}
