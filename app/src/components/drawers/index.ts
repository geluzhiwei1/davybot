/**
 * Drawers barrel export.
 * All side-panel drawers are mounted in the root layout and
 * controlled via `activeDrawer` in the Zustand store.
 */
export { AppDrawer, type DrawerId } from "./app-drawer";
export { AgentsDrawer } from "./agents-drawer";
export { LLMProvidersDrawer } from "./llm-providers-drawer";
export { WorkspaceSettingsDrawer } from "./workspace-settings-drawer";
export { SubtaskThreadDrawer } from "./subtask-thread-drawer";

/**
 * AppDrawers — mount once in the root layout.
 * Renders all drawers; only the one matching `activeDrawer` is visible.
 */
export { AppDrawers } from "./app-drawers-host";
