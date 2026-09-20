/**
 * File upload dialog with drag-and-drop support.
 * Used for uploading files to a workspace.
 */
import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Upload, X, FileText, Folder, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useWorkspaceFilesStore } from "@/lib/workspace-files-store";
import { fileApi } from "@/lib/api-client";
import { isLightShell, selectFiles, type SelectedFile } from "@/lib/platform/files";

// ── Types ─────────────────────────────────────────────────────────

interface UploadingFile {
  selectedFile: SelectedFile;
  progress: number; // 0-100
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId?: string;
  workspaceName?: string;
  onUploadComplete?: (files: string[]) => void;
}

// ── Component ─────────────────────────────────────────────────────

export function FileUploadDialog({
  open,
  onOpenChange,
  workspaceId,
  workspaceName,
  onUploadComplete,
}: Props) {
  const { t } = useTranslation("chatUi");
  const [files, setFiles] = useState<UploadingFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Actually upload files via the workspace files store API.
  // `batch` overrides the state-derived selection (used by auto-start, where
  // the just-added files are not yet visible in the `files` closure).
  const startUpload = useCallback(
    async (batch?: UploadingFile[]) => {
      if (!workspaceId) {
        setFiles((prev) =>
          prev.map((f) => ({ ...f, status: "error" as const, error: "No workspace selected" })),
        );
        return;
      }

      // Retry includes errored files; button path uses current state
      const pendingFiles =
        batch ?? files.filter((f) => f.status === "pending" || f.status === "error");
      if (pendingFiles.length === 0) return;
      const batchSet = new Set(pendingFiles.map((f) => f.selectedFile));
      setFiles((prev) =>
        prev.map((f) =>
          batchSet.has(f.selectedFile)
            ? { ...f, status: "uploading" as const, error: undefined }
            : f,
        ),
      );

      // Light shell + folder picks (localPath): per-file FormData through the
      // read-fallback is too slow for real directories — upload the whole set
      // in batches via uploadFolderBatch (shell reads contents, one
      // upload-folder POST per ~150 files recreates the tree).
      const lightShell = isLightShell();
      const lightBatch = lightShell ? pendingFiles.filter((uf) => uf.selectedFile.localPath) : [];
      const rest = pendingFiles.filter((uf) => !(lightShell && uf.selectedFile.localPath));

      let okCount = 0;
      if (lightBatch.length > 0) {
        const inLight = new Set(lightBatch.map((uf) => uf.selectedFile));
        setFiles((prev) =>
          prev.map((pf) =>
            inLight.has(pf.selectedFile)
              ? { ...pf, progress: 30, status: "uploading" as const, error: undefined }
              : pf,
          ),
        );
        const res = await fileApi.uploadFolderBatch(
          workspaceId,
          lightBatch.map((uf) => uf.selectedFile),
          {
            onProgress: (done, total) => {
              const pct = total > 0 ? Math.min(Math.round((done / total) * 100), 95) : 100;
              setFiles((prev) =>
                prev.map((pf) => (inLight.has(pf.selectedFile) ? { ...pf, progress: pct } : pf)),
              );
            },
          },
        );
        okCount += res.uploaded.length;
        const failedError = new Map(res.failed.map((x) => [x.file, x.error]));
        setFiles((prev) =>
          prev.map((pf) => {
            if (!inLight.has(pf.selectedFile)) return pf;
            if (failedError.has(pf.selectedFile)) {
              return { ...pf, status: "error" as const, error: failedError.get(pf.selectedFile) };
            }
            return { ...pf, progress: 100, status: "done" as const };
          }),
        );
      }

      // Upload each remaining file sequentially
      for (const uf of rest) {
        try {
          setFiles((prev) =>
            prev.map((pf) => (pf.selectedFile === uf.selectedFile ? { ...pf, progress: 30 } : pf)),
          );
          // Folder uploads: keep directory structure — parent_path is the dir
          // part of relativePath (backend appends the file name itself),
          // mirroring workspace-files-store.uploadFiles.
          let uploadDest: string | undefined;
          const rel = uf.selectedFile.relativePath;
          if (rel && rel.includes("/")) {
            uploadDest = rel.substring(0, rel.lastIndexOf("/"));
          }
          // uploadSmart picks FormData (web) or path-mode (desktop) automatically
          await fileApi.uploadSmart(workspaceId, uf.selectedFile, uploadDest);
          okCount++;
          setFiles((prev) =>
            prev.map((pf) =>
              pf.selectedFile === uf.selectedFile
                ? { ...pf, progress: 100, status: "done" as const }
                : pf,
            ),
          );
        } catch (e) {
          setFiles((prev) =>
            prev.map((pf) =>
              pf.selectedFile === uf.selectedFile
                ? { ...pf, status: "error" as const, error: (e as Error).message }
                : pf,
            ),
          );
        }
      }

      // Refresh the file tree in the store after uploads complete
      if (okCount > 0) {
        toast.success(t("upload.uploaded", { n: okCount }));
        try {
          const fetchTree = useWorkspaceFilesStore.getState().fetchFileTree;
          if (workspaceId) await fetchTree(workspaceId);
        } catch {
          // Non-critical: file tree refresh can fail silently
        }
      }
    },
    [files, workspaceId, t],
  );

  // Add files from selection and upload them immediately (single-step UX).
  // Multi-file selection/folder/drag-drop all funnel through here.
  const addFiles = useCallback(
    (selected: SelectedFile[]) => {
      if (selected.length === 0) return;
      const newFiles: UploadingFile[] = selected.map((sf) => ({
        selectedFile: sf,
        progress: 0,
        status: "pending" as const,
      }));
      setFiles((prev) => [...prev, ...newFiles]);
      void startUpload(newFiles);
    },
    [startUpload],
  );

  // Drag handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      if (e.dataTransfer.files.length > 0) {
        const dropped: SelectedFile[] = Array.from(e.dataTransfer.files).map((f) => ({
          name: f.name,
          size: f.size,
          file: f,
        }));
        addFiles(dropped);
      }
    },
    [addFiles],
  );

  // Remove file from list
  const removeFile = (sf: SelectedFile) => {
    setFiles((prev) => prev.filter((f) => f.selectedFile !== sf));
  };

  // Check if all uploads done
  const allDone = files.length > 0 && files.every((f) => f.status === "done");
  const isUploading = files.some((f) => f.status === "uploading");
  const uploadedNames = files.filter((f) => f.status === "done").map((f) => f.selectedFile.name);

  const handleClose = () => {
    // Notify parent and refresh file tree on completion
    if (allDone) {
      if (onUploadComplete) onUploadComplete(uploadedNames);
      // Refresh file tree in the store so the Files tab picks up new files
      if (workspaceId) {
        useWorkspaceFilesStore
          .getState()
          .fetchFileTree(workspaceId)
          .catch((e) => toast.error(t("upload.refreshFailed"), { description: String(e) }));
      }
    }
    setFiles([]);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="w-4 h-4 text-brand" />
            {t("upload.title")}
            {workspaceName && (
              <span className="text-sm text-muted-foreground font-normal">→ {workspaceName}</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Drop zone */}
          <div
            ref={dropRef}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer",
              isDragging
                ? "border-brand bg-brand/5"
                : "border-border hover:border-brand/40 hover:bg-muted/30",
            )}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
            <p className="text-sm font-medium">{t("upload.dropzone")}</p>
            <p className="text-xs text-muted-foreground mt-1">{t("upload.dropzoneHint")}</p>
          </div>

          {/* Folder upload button */}
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-2"
            onClick={() => {
              // selectFiles({directory}) splits platforms: web/desktop use
              // <input webkitdirectory>; the light shell (WebKitGTK, where
              // webkitdirectory is ignored) uses the native pick_folder_files.
              void selectFiles({ directory: true, multiple: true }).then(addFiles);
            }}
          >
            <Folder className="w-3.5 h-3.5" />
            {t("upload.selectFolder")}
          </Button>

          {/* Hidden file input (plain multi-file; drop zone click target) */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (!e.target.files) return;
              const selected: SelectedFile[] = Array.from(e.target.files).map((f) => ({
                name: f.name,
                size: f.size,
                file: f,
              }));
              addFiles(selected);
            }}
          />

          {/* File list */}
          {files.length > 0 && (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {files.map((f, i) => (
                <div
                  key={`${f.selectedFile.name}-${i}`}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg bg-muted/30 border border-border/50"
                >
                  <FileText className="w-4 h-4 text-brand shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm truncate">{f.selectedFile.name}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {formatFileSize(f.selectedFile.size)}
                    </div>
                    {f.status === "error" && f.error && (
                      <div className="text-[10px] text-red-500 truncate" title={f.error}>
                        {f.error}
                      </div>
                    )}
                    {f.status === "uploading" && (
                      <Progress value={f.progress} className="h-1 mt-1" />
                    )}
                  </div>
                  {(f.status === "done" || f.status === "error") && (
                    <div className="flex items-center gap-1 shrink-0">
                      {f.status === "error" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2 text-[10px] text-red-500 hover:text-red-600"
                          onClick={() => void startUpload([f])}
                        >
                          {t("upload.retry")}
                        </Button>
                      )}
                      {f.status === "done" ? (
                        <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                      )}
                    </div>
                  )}
                  {f.status === "uploading" && (
                    <Loader2 className="w-4 h-4 animate-spin text-brand shrink-0" />
                  )}
                  {f.status === "pending" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFile(f.selectedFile);
                      }}
                    >
                      <X className="w-3 h-3" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleClose}>
              {allDone ? t("upload.done") : t("upload.cancel")}
            </Button>
            {!allDone && files.length > 0 && (
              <Button
                onClick={() => void startUpload()}
                disabled={
                  isUploading || files.every((f) => f.status !== "pending" && f.status !== "error")
                }
                className="gap-2"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    {t("upload.uploading")}
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    {t("upload.uploadCount", {
                      count: files.filter((f) => f.status === "pending" || f.status === "error")
                        .length,
                    })}
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Helper ────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
