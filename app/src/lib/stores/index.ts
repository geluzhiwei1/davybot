/**
 * Domain stores — re-exports from split store files.
 *
 * New code should import directly from the specific store:
 *   import { useWorkspaceStore } from "@/lib/stores/workspace-store"
 *   import { useCollectionStore } from "@/lib/stores/collection-store"
 *   import { useModelStore } from "@/lib/stores/model-store"
 *
 * For backward compatibility, `store.ts` still re-exports everything
 * via `useStore` (the legacy monolithic store).
 */
export {
  useWorkspaceStore,
  type Workspace,
  type FileKind,
  type WorkspaceFile,
} from "./workspace-store";
export { useCollectionStore, type WorkspaceCollection } from "./collection-store";
export { useModelStore, type LLMModel } from "./model-store";
