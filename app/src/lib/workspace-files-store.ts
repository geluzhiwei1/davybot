/**
 * Workspace files store — file tree, knowledge bases, file content preview.
 * Separate from workspace-store.ts which handles workspace/conversation selection.
 */
import { toastError } from "./api/client.js";
import { create } from "zustand";
import {
  fileApi,
  knowledgeApi,
  type BackendFileNode,
  type KnowledgeBase,
  type KnowledgeDomain,
} from "@/lib/api-client";
import { isLightShell, type SelectedFile } from "@/lib/platform/files";
import type { FileTreeItem } from "@/components/files/file-tree-node";

// ── Convert backend flat nodes to nested UI FileTreeItem[] ──
// Backend returns a flat list (path-sorted, each with `level` and empty `children`).
// We rebuild the hierarchy from path prefixes (see flatNodesToTree).

function flatNodesToTree(nodes: BackendFileNode[]): FileTreeItem[] {
  if (nodes.length === 0) return [];

  // If backend already provides nested children, use them directly
  const hasRealChildren = nodes.some((n) => n.children && n.children.length > 0);
  if (hasRealChildren) {
    return nodes.map(backendNodeToTreeItem);
  }

  // Build tree from path prefixes instead of relying on `level` + DFS ordering.
  // The backend returns nodes sorted by path (alphabetical), which is NOT DFS
  // order: a root-level file like "foo.zip" sorts between the directory "foo"
  // and its children ("foo/bar"). A stack/level algorithm pops the parent on
  // the sibling file and then silently drops every following descendant.
  // Path-prefix attachment is robust to any ordering where the parent path
  // appears before its children (guaranteed by prefix sort).
  const byPath = new Map<string, FileTreeItem>();
  const roots: FileTreeItem[] = [];
  for (const n of nodes) {
    const item: FileTreeItem = {
      name: n.name,
      path: n.path,
      type: n.type === "directory" ? ("folder" as const) : ("file" as const),
      children: [],
    };
    byPath.set(n.path, item);
    const sep = n.path.lastIndexOf("/");
    const parentPath = sep >= 0 ? n.path.slice(0, sep) : "";
    const parent = parentPath ? byPath.get(parentPath) : undefined;
    if (parent) {
      parent.children!.push(item);
    } else {
      roots.push(item);
    }
  }
  return roots;
}

function backendNodeToTreeItem(node: BackendFileNode): FileTreeItem {
  return {
    name: node.name,
    path: node.path,
    type: node.type === "directory" ? "folder" : "file",
    children: node.children?.map(backendNodeToTreeItem),
  };
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

/** Extensions that should be fetched as Blob (binary), not decoded as text. */
const BINARY_EXTENSIONS = new Set([
  "pdf",
  "png",
  "jpg",
  "jpeg",
  "gif",
  "svg",
  "webp",
  "bmp",
  "ico",
  "mp4",
  "webm",
  "mp3",
  "wav",
  "ogg",
  "avi",
  "mov",
  "docx",
  "doc",
  "xlsx",
  "xls",
  "pptx",
  "ppt",
  "odt",
  "ods",
  "rtf",
  "zip",
  "rar",
  "7z",
  "gz",
  "tar",
  "exe",
  "dll",
  "so",
  "bin",
  "drawio",
]);

/** Legacy formats that need LibreOffice conversion before preview. */
const LEGACY_EXTENSIONS = new Set(["doc", "xls", "ppt", "odt", "ods", "rtf"]);

function isBinaryFile(fileName: string): boolean {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  return BINARY_EXTENSIONS.has(ext);
}

function isLegacyFormat(fileName: string): boolean {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  return LEGACY_EXTENSIONS.has(ext);
}

/**
 * Map file extension → MIME type.
 * Backend returns application/octet-stream for all downloads; blob URLs
 * inherit that type, causing browsers to download instead of inline-preview.
 * We re-wrap the blob with the correct MIME type before createObjectURL.
 * Legacy formats (.doc/.xls/etc) are converted to OOXML by the backend,
 * so their MIME reflects the converted format.
 */
function getMimeType(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  const M: Record<string, string> = {
    pdf: "application/pdf",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    // Legacy formats → converted to OOXML by backend
    doc: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xls: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ppt: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    odt: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ods: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    rtf: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    // Images
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    gif: "image/gif",
    svg: "image/svg+xml",
    webp: "image/webp",
    bmp: "image/bmp",
    // Media
    mp4: "video/mp4",
    webm: "video/webm",
    mp3: "audio/mpeg",
    wav: "audio/wav",
    ogg: "audio/ogg",
  };
  return M[ext] ?? "application/octet-stream";
}

/** Fetch blob from API and re-wrap with correct MIME type for blob URL. */
async function fetchBlobWithMime(fetcher: () => Promise<Blob>, fileName: string): Promise<string> {
  const raw = await fetcher();
  const mime = getMimeType(fileName);
  const typed = new Blob([raw], { type: mime });
  return URL.createObjectURL(typed);
}

export interface FileInfo {
  path: string;
  name: string;
  type: "file" | "directory";
  size: number;
  created_at: string;
  modified_at: string;
  permissions: { readable: boolean; writable: boolean; executable: boolean };
  mime_type?: string;
  language?: string;
}

export interface SearchResult {
  path: string;
  name: string;
  type: string;
  matches?: Array<{ line: number; text: string }>;
}

interface WorkspaceFilesState {
  // File tree
  fileTree: FileTreeItem[];
  fileTreeLoading: boolean;
  fileTreeError: string | null;
  currentWorkspaceId: string | null;

  // File content preview
  openFiles: OpenFile[];
  activeFileId: string | null;
  fileContentLoading: boolean;

  // Knowledge bases
  knowledgeBases: KnowledgeBase[];
  knowledgeDomains: KnowledgeDomain[];
  kbLoading: boolean;

  // Search
  searchResults: SearchResult[];
  searchLoading: boolean;

  // File info
  selectedFileInfo: FileInfo | null;
  fileInfoLoading: boolean;

  // Upload
  uploading: boolean;
  uploadProgress: number;

  // Actions
  fetchFileTree: (workspaceId: string) => Promise<void>;
  fetchKnowledgeBases: () => Promise<void>;
  openFile: (workspaceId: string, path: string) => Promise<void>;
  setActiveFile: (id: string) => void;
  closeFile: (id: string) => void;
  closeAllFiles: () => void;
  createFile: (workspaceId: string, path: string, type?: "file" | "directory") => Promise<void>;
  deleteFile: (workspaceId: string, path: string) => Promise<void>;
  renameFile: (workspaceId: string, oldPath: string, newPath: string) => Promise<void>;
  uploadFiles: (workspaceId: string, files: SelectedFile[], destPath?: string) => Promise<void>;
  downloadFile: (workspaceId: string, path: string) => Promise<void>;
  searchFiles: (workspaceId: string, query: string) => Promise<void>;
  clearSearch: () => void;
  fetchFileInfo: (workspaceId: string, path: string) => Promise<void>;
  clearFileInfo: () => void;
}

export const useWorkspaceFilesStore = create<WorkspaceFilesState>()((set, get) => ({
  fileTree: [],
  fileTreeLoading: false,
  fileTreeError: null,
  currentWorkspaceId: null,
  openFiles: [],
  activeFileId: null,
  fileContentLoading: false,
  knowledgeBases: [],
  knowledgeDomains: [],
  kbLoading: false,
  searchResults: [],
  searchLoading: false,
  selectedFileInfo: null,
  fileInfoLoading: false,
  uploading: false,
  uploadProgress: 0,

  fetchFileTree: async (workspaceId: string) => {
    const prevWsId = get().currentWorkspaceId;
    set({ fileTreeLoading: true, fileTreeError: null, currentWorkspaceId: workspaceId });

    // Workspace changed → revoke blob URLs and clear stale open files
    if (prevWsId && prevWsId !== workspaceId) {
      const { openFiles } = get();
      for (const f of openFiles) {
        if (f.blobUrl) URL.revokeObjectURL(f.blobUrl);
      }
      set({ openFiles: [], activeFileId: null });
    }

    try {
      const data = await fileApi.getTree(workspaceId);
      const tree = flatNodesToTree(data.fileTree ?? []);
      set({ fileTree: tree, fileTreeLoading: false });
    } catch (e) {
      set({ fileTreeError: String(e), fileTreeLoading: false });
    }
  },

  fetchKnowledgeBases: async () => {
    set({ kbLoading: true });
    try {
      const [basesData, domainsData] = await Promise.all([
        knowledgeApi.listBases(),
        knowledgeApi.listDomains(),
      ]);
      set({
        knowledgeBases: basesData.items ?? [],
        knowledgeDomains: domainsData.domains ?? [],
        kbLoading: false,
      });
    } catch (e) {
      console.error("[WorkspaceFilesStore] fetchKnowledgeBases failed:", e);
      set({ kbLoading: false });
      toastError("加载知识库失败", e);
    }
  },

  openFile: async (workspaceId: string, path: string) => {
    const { openFiles } = get();
    const fileName = path.split("/").pop() || path;
    const existing = openFiles.find((f) => f.path === path);
    if (existing) {
      set({ activeFileId: existing.id });
      return;
    }

    set({ fileContentLoading: true });
    try {
      const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      let newFile: OpenFile;

      if (isLegacyFormat(fileName)) {
        // Legacy formats (.doc/.xls/etc): convert via LibreOffice → OOXML blob
        const blobUrl = await fetchBlobWithMime(
          () => fileApi.downloadConverted(workspaceId, path),
          fileName,
        );
        newFile = { id, name: fileName, path, content: "", blobUrl, workspaceId };
      } else if (isBinaryFile(fileName)) {
        // Binary files: fetch as Blob, re-wrap with correct MIME type for blob URL
        const blobUrl = await fetchBlobWithMime(
          () => fileApi.downloadBlob(workspaceId, path),
          fileName,
        );
        newFile = { id, name: fileName, path, content: "", blobUrl, workspaceId };
      } else {
        // Text files: fetch as string for editing
        const content = await fileApi.downloadContent(workspaceId, path);
        newFile = { id, name: fileName, path, content, workspaceId };
      }

      set({
        openFiles: [...openFiles, newFile],
        activeFileId: id,
        fileContentLoading: false,
      });
    } catch (e) {
      console.error("[WorkspaceFilesStore] openFile failed:", e);
      set({ fileContentLoading: false });
      toastError("打开文件失败", e);
    }
  },

  setActiveFile: (id: string) => set({ activeFileId: id }),
  closeFile: (id: string) => {
    const { openFiles, activeFileId } = get();
    const closing = openFiles.find((f) => f.id === id);
    // Revoke blob URL to prevent memory leak
    if (closing?.blobUrl) URL.revokeObjectURL(closing.blobUrl);
    const remaining = openFiles.filter((f) => f.id !== id);
    set({
      openFiles: remaining,
      activeFileId: activeFileId === id ? (remaining[0]?.id ?? null) : activeFileId,
    });
  },
  closeAllFiles: () => {
    const { openFiles } = get();
    // Revoke all blob URLs
    for (const f of openFiles) {
      if (f.blobUrl) URL.revokeObjectURL(f.blobUrl);
    }
    set({ openFiles: [], activeFileId: null });
  },

  createFile: async (workspaceId, path, type = "file") => {
    try {
      await fileApi.create(workspaceId, path, type);
      await get().fetchFileTree(workspaceId);
    } catch (e) {
      console.error("[WorkspaceFilesStore] createFile failed:", e);
      toastError("创建文件失败", e);
    }
  },

  deleteFile: async (workspaceId, path) => {
    try {
      await fileApi.delete(workspaceId, path);
      const { openFiles } = get();
      const openFile = openFiles.find((f) => f.path === path);
      if (openFile) get().closeFile(openFile.id);
      await get().fetchFileTree(workspaceId);
    } catch (e) {
      console.error("[WorkspaceFilesStore] deleteFile failed:", e);
      toastError("删除文件失败", e);
    }
  },

  renameFile: async (workspaceId, oldPath, newPath) => {
    try {
      await fileApi.rename(workspaceId, oldPath, newPath);
      await get().fetchFileTree(workspaceId);
    } catch (e) {
      console.error("[WorkspaceFilesStore] renameFile failed:", e);
      toastError("重命名文件失败", e);
    }
  },

  uploadFiles: async (workspaceId, files, destPath) => {
    set({ uploading: true, uploadProgress: 0 });
    const total = files.length;
    let completed = 0;
    let anyOk = false;
    try {
      // Light shell + folder picks (localPath): batch upload via
      // uploadFolderBatch — one upload-folder POST per ~150 files, instead
      // of a per-file FormData round trip through the read fallback.
      const lightShell = isLightShell();
      const lightPaths = lightShell ? files.filter((f) => f.localPath) : [];
      const rest = files.filter((f) => !(lightShell && f.localPath));
      if (lightPaths.length > 0) {
        const res = await fileApi.uploadFolderBatch(workspaceId, lightPaths, {
          destPath,
          onProgress: (done) =>
            set({ uploadProgress: Math.round(((completed + done) / total) * 100) }),
        });
        completed += lightPaths.length;
        if (res.uploaded.length > 0) anyOk = true;
        if (res.failed.length > 0) {
          toastError(`目录上传有 ${res.failed.length} 个文件失败`, new Error(res.failed[0].error));
        }
      }
      for (const file of rest) {
        // For folder uploads: extract directory part from relativePath.
        // Backend expects parent_path = directory (it appends file.filename itself).
        // e.g. relativePath "myfolder/sub/file.txt" → destPath "myfolder/sub"
        let uploadDest = destPath;
        if (file.relativePath && file.relativePath.includes("/")) {
          uploadDest = file.relativePath.substring(0, file.relativePath.lastIndexOf("/"));
        }
        await fileApi.uploadSmart(workspaceId, file, uploadDest);
        completed++;
        anyOk = true;
        set({ uploadProgress: Math.round((completed / total) * 100) });
      }
      if (anyOk) {
        await get().fetchFileTree(workspaceId);
      }
    } catch (e) {
      console.error("[WorkspaceFilesStore] uploadFiles failed:", e);
      toastError("上传文件失败", e);
    } finally {
      set({ uploading: false, uploadProgress: 0 });
    }
  },

  downloadFile: async (workspaceId, path) => {
    try {
      const blob = await fileApi.downloadBlob(workspaceId, path);
      let fileName = path.split("/").pop() || "download";
      // Directory downloads come back as zip (backend zips folders)
      if (blob.type === "application/zip" && !fileName.toLowerCase().endsWith(".zip")) {
        fileName += ".zip";
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("[WorkspaceFilesStore] downloadFile failed:", e);
      toastError("下载文件失败", e);
    }
  },

  searchFiles: async (workspaceId, query) => {
    if (!query.trim()) {
      set({ searchResults: [], searchLoading: false });
      return;
    }
    set({ searchLoading: true });
    try {
      const data = await fileApi.search(workspaceId, query);
      set({ searchResults: data.results ?? [], searchLoading: false });
    } catch (e) {
      console.error("[WorkspaceFilesStore] searchFiles failed:", e);
      set({ searchResults: [], searchLoading: false });
    }
  },

  clearSearch: () => set({ searchResults: [], searchLoading: false }),

  fetchFileInfo: async (workspaceId, path) => {
    set({ fileInfoLoading: true });
    try {
      const data = await fileApi.getInfo(workspaceId, path);
      set({ selectedFileInfo: data.info, fileInfoLoading: false });
    } catch (e) {
      console.error("[WorkspaceFilesStore] fetchFileInfo failed:", e);
      set({ selectedFileInfo: null, fileInfoLoading: false });
    }
  },

  clearFileInfo: () => set({ selectedFileInfo: null }),
}));
