/**
 * File selection abstraction — branches between native dialog (desktop) and
 * HTML input (web).
 *
 * Desktop (Tauri): Uses `@tauri-apps/plugin-dialog` to get an absolute disk
 *   path. The file is NOT loaded into browser memory; instead the path is
 *   sent to the sidecar, which reads the file directly from disk.
 *   When `wantFile: true`, falls back to `<input type="file">` (which works
 *   in the Tauri webview) to obtain a File object for APIs that need one.
 *
 * Web: Uses a hidden `<input type="file">`. The browser File object is
 *   uploaded via FormData to the remote server.
 */
import { toast } from "sonner";

import { IS_DESKTOP } from "../platform";

/** A file selected by the user — either a local path (desktop) or a File object (web). */
export interface SelectedFile {
  name: string;
  size: number;
  /** Desktop only: absolute path on disk. The sidecar reads from here directly. */
  localPath?: string;
  /** Web only (or desktop with wantFile): browser File object for FormData upload. */
  file?: File;
  /**
   * Relative path within a selected directory (e.g. "myfolder/sub/file.txt").
   * Populated by `selectFiles({ directory: true })` and folder drag-and-drop,
   * so the backend can recreate the directory structure.
   */
  relativePath?: string;
}

export interface SelectFilesOptions {
  multiple?: boolean;
  /** Comma-separated extensions, e.g. ".csv,.pdf" — same semantics as `<input accept>`. */
  accept?: string;
  /**
   * If true, guarantee that the returned SelectedFile has a `file` property
   * (File object) rather than just a `localPath`.
   *
   * On desktop this means using `<input type="file">` instead of the Tauri
   * dialog — the file IS loaded into browser memory.
   *
   * Use this for domain-specific APIs that accept File/FormData and don't
   * have a path-mode endpoint.
   */
  wantFile?: boolean;
  /**
   * If true, open a directory picker. Returns all files within the selected
   * directory (recursively).
   *
   * Web/desktop: uses `<input webkitdirectory>` — Tauri's
   * `open({ directory: true })` returns a single dir path, not individual
   * files, so it doesn't fit the "enumerate files" semantics.
   *
   * Light shell (davy-light-app): WebKitGTK ignores `webkitdirectory`, so the
   * picker falls back to the shell's native `pick_folder_files` command.
   */
  directory?: boolean;
}

/**
 * Open a file picker and return the selected files.
 *
 * Returns an empty array if the user cancels.
 */
export async function selectFiles(opts?: SelectFilesOptions): Promise<SelectedFile[]> {
  // Light shell: WebKitGTK can't do <input webkitdirectory> — route folder
  // picking through the shell's native command (path manifest only; upload
  // goes via upload-by-path since shell and backend share the same machine).
  if (opts?.directory && isLightShell()) {
    return selectViaLightFolder();
  }
  // Light shell: WebKitGTK's <input type="file" multiple> drops the FileList
  // on multi-select (change fires empty or never) → silent no-op. Route
  // multi-file picking through the native pick_files command instead.
  // wantFile callers still need real File objects → keep the <input> path.
  if (isLightShell() && opts?.multiple && !opts?.wantFile) {
    return selectViaLightFiles();
  }
  if (IS_DESKTOP && !opts?.wantFile && !opts?.directory) {
    return selectViaTauri(opts);
  }
  return selectViaInput(opts);
}

// ── Light shell (davy-light-app): native folder picking ───────────────

/**
 * True inside the NormNomos Light shell (davy-light-app): the shell injects
 * `window.__NORMNOMOS_LIGHT__` before the page loads (inject.js).
 *
 * The light shell serves the *web* build inside a native webview — plain file
 * inputs work, but on Linux (WebKitGTK) `<input webkitdirectory>` is ignored,
 * so directory picking must go through the shell's `pick_folder_files`
 * command (native dialog + path manifest; contents are copied server-side
 * via upload-by-path — shell and backend run on the same machine).
 */
export function isLightShell(): boolean {
  return typeof window !== "undefined" && "__NORMNOMOS_LIGHT__" in window;
}

/** pick_folder_files 命令返回的条目(壳侧 Rust 定义;仅路径清单,无内容)。 */
interface LightPickedFile {
  path: string;
  relative_path: string;
  size: number;
}

/** Minimal shape of the withGlobalTauri global the light shell provides. */
interface TauriGlobalLike {
  __TAURI__?: {
    core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> };
  };
}

/** Invoke a light-shell command; throws when the shell global is missing. */
export async function lightInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const invoke = (window as unknown as TauriGlobalLike).__TAURI__?.core?.invoke;
  if (typeof invoke !== "function") {
    throw new Error("light 壳不可用（缺少 __TAURI__.core）");
  }
  return invoke(cmd, args) as Promise<T>;
}

async function selectViaLightFolder(): Promise<SelectedFile[]> {
  let picked: LightPickedFile[];
  try {
    picked = await lightInvoke<LightPickedFile[]>("pick_folder_files");
  } catch (e) {
    // e.g. shell ACL rejection or file-count cap — must be VISIBLE to the
    // user (console-only swallowed real failures like the old size caps).
    const msg = e instanceof Error ? e.message : String(e);
    toast.error(`目录选择失败：${msg}`);
    return [];
  }
  return picked.map((p) => ({
    name: p.relative_path.split("/").pop() || p.path,
    size: p.size,
    // Path manifest only: contents are fetched in batches via
    // read_files_base64 and uploaded to the (cloud) backend through the
    // upload-folder endpoint — the light shell has NO local workspace
    // backend, so upload-by-path's local-disk semantics do not apply.
    localPath: p.path,
    relativePath: p.relative_path,
  }));
}

/**
 * Light shell multi-file pick: same manifest contract as folder picks —
 * pick_files returns { path, relative_path (= filename), size }; contents
 * are later fetched via read_files_base64 and pushed through upload-folder
 * by uploadFiles' lightPaths batch (workspace-files-store).
 */
async function selectViaLightFiles(): Promise<SelectedFile[]> {
  let picked: LightPickedFile[];
  try {
    picked = await lightInvoke<LightPickedFile[]>("pick_files");
  } catch (e) {
    // Shell ACL rejection / caps — surface visibly, never console-only.
    const msg = e instanceof Error ? e.message : String(e);
    toast.error(`文件选择失败：${msg}`);
    return [];
  }
  return picked.map((p) => ({
    name: p.relative_path.split("/").pop() || p.path,
    size: p.size,
    localPath: p.path,
    relativePath: p.relative_path,
  }));
}

/**
 * Convert a SelectedFile to a File object.
 *
 * - If `sf.file` exists (web, or desktop with wantFile), return it directly.
 * - If only `sf.localPath` exists (desktop path-mode), this throws — callers
 *   should use `selectFiles({ wantFile: true })` if they need a File object.
 */
export function selectedFileToFile(sf: SelectedFile): File {
  if (sf.file) return sf.file;
  throw new Error(
    `SelectedFile "${sf.name}" has no File object. Use selectFiles({ wantFile: true }) for APIs that need File/FormData.`,
  );
}

// ── Desktop: Tauri native dialog ──────────────────────────────────────

async function selectViaTauri(opts?: SelectFilesOptions): Promise<SelectedFile[]> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const result = await open({
    multiple: opts?.multiple ?? false,
    directory: false,
    filters: acceptToFilters(opts?.accept),
  });
  if (!result) return [];

  const paths = Array.isArray(result) ? result : [result];
  return paths.map((p) => ({
    name: basename(p),
    size: 0, // unknown until sidecar processes the file
    localPath: p,
  }));
}

// ── Web: hidden <input type="file"> ───────────────────────────────────

function selectViaInput(opts?: SelectFilesOptions): Promise<SelectedFile[]> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = opts?.multiple ?? false;
    if (opts?.accept) input.accept = opts.accept;
    if (opts?.directory) {
      // Boolean IDL attribute — MUST be `true`, not `""` (empty string coerces
      // to false and the attribute is silently dropped → plain file picker).
      input.webkitdirectory = true;
    }

    input.onchange = () => {
      const files = Array.from(input.files ?? []);
      resolve(
        files.map((f) => ({
          name: f.name,
          size: f.size,
          file: f,
          relativePath:
            (f as File & { webkitRelativePath?: string }).webkitRelativePath || undefined,
        })),
      );
    };

    // If the user cancels the dialog, onchange never fires. There's no
    // reliable cross-browser cancel event, so we leave the promise pending.
    // This matches <input type="file"> semantics throughout the app.
    input.click();
  });
}

// ── Helpers ───────────────────────────────────────────────────────────

/** Extract the file name from a path string (cross-platform). */
function basename(p: string): string {
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

/** Convert an `accept` string (".csv,.pdf") to Tauri dialog `filters`. */
function acceptToFilters(accept?: string): { name: string; extensions: string[] }[] | undefined {
  if (!accept) return undefined;
  const extensions = accept
    .split(",")
    .map((a) => a.trim().replace(/^\./, ""))
    .filter(Boolean);
  if (extensions.length === 0) return undefined;
  return [{ name: "Files", extensions }];
}
