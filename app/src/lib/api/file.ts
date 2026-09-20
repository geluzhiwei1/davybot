/**
 * File API — workspace file tree, upload, download, CRUD.
 */
import { STORAGE_KEYS, getApiBaseUrl } from "../env";
import { request } from "./client";
import { isLightShell, lightInvoke, type SelectedFile } from "../platform/files";

// ── Types ────────────────────────────────────────────────────────────

export interface BackendFileNode {
  id: string;
  name: string;
  path: string;
  type: "file" | "directory";
  level: number;
  size: number;
  children?: BackendFileNode[];
}

/** Decode base64 to a Blob (contents fetched from the light shell in-band). */
function base64ToBlob(b64: string): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes]);
}

// ── API ──────────────────────────────────────────────────────────────

export const fileApi = {
  getTree: (workspaceId: string) =>
    request<{ success: boolean; fileTree: BackendFileNode[] }>(
      `/api/workspaces/${workspaceId}/file-tree`,
    ),

  download: (workspaceId: string, filePath: string) =>
    `${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/download?path=${encodeURIComponent(filePath)}`,

  downloadContent: async (workspaceId: string, filePath: string): Promise<string> => {
    const url = `${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/download?path=${encodeURIComponent(filePath)}`;
    const headers: Record<string, string> = {};
    const token = localStorage.getItem(STORAGE_KEYS.authToken);
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    return res.text();
  },

  /** 后端 CreateFileRequest：{path, content="", is_directory}；写文件时父目录自动创建 */
  create: (
    workspaceId: string,
    path: string,
    type: "file" | "directory" = "file",
    content?: string,
  ) =>
    request<{ success: boolean }>(`/api/workspaces/${workspaceId}/files/create`, {
      method: "POST",
      body: JSON.stringify({ path, is_directory: type === "directory", content: content ?? "" }),
    }),

  rename: (workspaceId: string, oldPath: string, newPath: string) =>
    request<{ success: boolean }>(`/api/workspaces/${workspaceId}/files/rename`, {
      method: "PUT",
      body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
    }),

  delete: (workspaceId: string, path: string) =>
    request<{ success: boolean }>(`/api/workspaces/${workspaceId}/files/delete`, {
      method: "DELETE",
      body: JSON.stringify({ path }),
    }),

  move: (workspaceId: string, sourcePath: string, destPath: string) =>
    request<{ success: boolean }>(`/api/workspaces/${workspaceId}/files/move`, {
      method: "POST",
      body: JSON.stringify({ source_path: sourcePath, destination_path: destPath }),
    }),

  upload: (workspaceId: string, file: File, destPath?: string) => {
    const formData = new FormData();
    // Force filename to be just the base name — some browsers include the
    // relative path (e.g. "myfolder/sub/file.txt") in File.name when using
    // webkitdirectory, which would confuse the backend.
    formData.append("file", file, file.name);
    if (destPath) formData.append("parent_path", destPath);
    const token = localStorage.getItem(STORAGE_KEYS.authToken);
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return fetch(`${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/upload`, {
      method: "POST",
      headers,
      body: formData,
    });
  },

  /**
   * Upload by local path — desktop only.
   *
   * Sends the absolute disk path to the sidecar, which reads the file
   * directly via `shutil.copy2()`. Avoids the HTTP loopback overhead of
   * `upload()` for large files.
   */
  uploadByPath: (workspaceId: string, sourcePath: string, destPath?: string) =>
    request<{ success: boolean; path: string }>(
      `/api/workspaces/${workspaceId}/files/upload-by-path`,
      {
        method: "POST",
        body: JSON.stringify({
          source_path: sourcePath,
          parent_path: destPath,
        }),
      },
    ),

  /**
   * Smart upload — picks the right mechanism based on the SelectedFile shape.
   *
   * - Desktop (has `localPath`): uses `uploadByPath()` (zero-copy from disk)
   * - Light shell + `localPath`: the workspace backend is in the CLOUD and
   *   cannot read local paths — the shell reads the file (read_files_base64)
   *   and the content goes up via FormData. Single-file fallback; folder
   *   picks use `uploadFolderBatch()` instead.
   * - Web (has `file`): uses `upload()` (FormData over HTTP)
   */
  uploadSmart: async (workspaceId: string, file: SelectedFile, destPath?: string) => {
    if (file.localPath) {
      if (isLightShell()) {
        const chunks = await lightInvoke<{ path: string; data_base64: string }[]>(
          "read_files_base64",
          { paths: [file.localPath] },
        );
        if (!chunks[0]) throw new Error(`壳侧未返回 ${file.name} 的内容`);
        const res = await fileApi.upload(
          workspaceId,
          new File([base64ToBlob(chunks[0].data_base64)], file.name),
          destPath,
        );
        if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
        return res.json();
      }
      return fileApi.uploadByPath(workspaceId, file.localPath, destPath);
    }
    if (file.file) {
      const res = await fileApi.upload(workspaceId, file.file, destPath);
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json();
    }
    throw new Error("SelectedFile has neither localPath nor file");
  },

  /**
   * Batched folder upload for the light shell — the fast path for directory
   * picks (path manifest + cloud backend).
   *
   * Contents are fetched from the shell in bounded batches (≤150 files /
   * ≤64 MiB per invoke; the shell enforces its own 256 MiB hard cap) and
   * pushed to the existing `upload-folder` endpoint, which recreates the
   * directory tree from the relative-path filenames. Per-file results are
   * mapped back from the response (uploaded_files[].filename / errors).
   */
  uploadFolderBatch: async (
    workspaceId: string,
    files: SelectedFile[],
    opts?: { destPath?: string; onProgress?: (done: number, total: number) => void },
  ): Promise<{ uploaded: SelectedFile[]; failed: { file: SelectedFile; error: string }[] }> => {
    const withPath = files.filter((f) => f.localPath);
    const uploaded: SelectedFile[] = [];
    const failed: { file: SelectedFile; error: string }[] = [];
    if (withPath.length === 0) return { uploaded, failed };

    // Chunk by file count and cumulative bytes; an oversized single file
    // gets its own batch (the shell rejects >256 MiB with a clear error).
    const batches: SelectedFile[][] = [];
    let cur: SelectedFile[] = [];
    let curBytes = 0;
    for (const f of withPath) {
      if (cur.length > 0 && (cur.length >= 150 || curBytes + f.size > 64 * 1024 * 1024)) {
        batches.push(cur);
        cur = [];
        curBytes = 0;
      }
      cur.push(f);
      curBytes += f.size;
    }
    if (cur.length > 0) batches.push(cur);

    let done = 0;
    for (const batch of batches) {
      let chunks: { path: string; data_base64: string }[];
      try {
        chunks = await lightInvoke<{ path: string; data_base64: string }[]>("read_files_base64", {
          paths: batch.map((f) => f.localPath!),
        });
      } catch (e) {
        // Shell-side errors are user-readable (subtree guard / size caps).
        const msg = e instanceof Error ? e.message : String(e);
        for (const f of batch) failed.push({ file: f, error: msg });
        done += batch.length;
        opts?.onProgress?.(done, withPath.length);
        continue;
      }

      const byPath = new Map(chunks.map((c) => [c.path, c]));
      const fd = new FormData();
      for (const f of batch) {
        const c = byPath.get(f.localPath!);
        if (!c) {
          failed.push({ file: f, error: "壳侧未返回文件内容" });
          continue;
        }
        fd.append("files", base64ToBlob(c.data_base64), f.relativePath || f.name);
      }
      if (opts?.destPath) fd.append("parent_path", opts.destPath);

      try {
        const headers: Record<string, string> = {};
        const token = localStorage.getItem(STORAGE_KEYS.authToken);
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const res = await fetch(
          `${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/upload-folder`,
          { method: "POST", headers, body: fd },
        );
        if (!res.ok) {
          const text = (await res.text()).slice(0, 200);
          throw new Error(`HTTP ${res.status}: ${text}`);
        }
        const body = (await res.json()) as {
          uploaded_files?: { filename: string }[];
          errors?: string[];
        };
        const okNames = new Set(body.uploaded_files?.map((u) => u.filename) ?? []);
        for (const f of batch) {
          const name = f.relativePath || f.name;
          if (okNames.has(name)) {
            uploaded.push(f);
          } else {
            const errStr = (body.errors ?? []).find((s) => s.startsWith(`${name}:`));
            failed.push({ file: f, error: errStr ?? "上传失败" });
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        for (const f of batch) failed.push({ file: f, error: msg });
      }
      done += batch.length;
      opts?.onProgress?.(done, withPath.length);
    }
    return { uploaded, failed };
  },

  downloadBlob: async (workspaceId: string, filePath: string): Promise<Blob> => {
    const url = `${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/download?path=${encodeURIComponent(filePath)}`;
    const headers: Record<string, string> = {};
    const token = localStorage.getItem(STORAGE_KEYS.authToken);
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    return res.blob();
  },

  /** Convert legacy formats (.doc/.xls/etc) to OOXML via LibreOffice. Returns Blob. */
  downloadConverted: async (workspaceId: string, filePath: string): Promise<Blob> => {
    const url = `${getApiBaseUrl()}/api/workspaces/${workspaceId}/files/convert?path=${encodeURIComponent(filePath)}`;
    const headers: Record<string, string> = {};
    const token = localStorage.getItem(STORAGE_KEYS.authToken);
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`Conversion failed (${res.status}): ${detail}`);
    }
    return res.blob();
  },

  getInfo: (workspaceId: string, filePath: string) =>
    request<{
      success: boolean;
      info: {
        path: string;
        name: string;
        type: "file" | "directory";
        size: number;
        created_at: string;
        modified_at: string;
        permissions: { readable: boolean; writable: boolean; executable: boolean };
        mime_type?: string;
        language?: string;
      };
    }>(`/api/workspaces/${workspaceId}/files/info?path=${encodeURIComponent(filePath)}`),

  search: (workspaceId: string, query: string) =>
    request<{
      success: boolean;
      results: Array<{
        path: string;
        name: string;
        type: string;
        matches?: Array<{ line: number; text: string }>;
      }>;
      total: number;
    }>(`/api/workspaces/${workspaceId}/files/search?q=${encodeURIComponent(query)}`),
};
