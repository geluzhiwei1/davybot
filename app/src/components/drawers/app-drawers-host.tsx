/**
 * AppDrawers — Host component that mounts all drawer panels.
 * Place once in the root layout. Each drawer reads `activeDrawer`
 * from the store and opens/closes accordingly.
 */
import { AgentsDrawer } from "./agents-drawer";
import { LLMProvidersDrawer } from "./llm-providers-drawer";
import { WorkspaceSettingsDrawer } from "./workspace-settings-drawer";
import { SubtaskThreadDrawer } from "./subtask-thread-drawer";
import { ApprovalPrompt } from "@/components/security/approval-prompt";

export function AppDrawers() {
  return (
    <>
      <AgentsDrawer />
      <LLMProvidersDrawer />
      <WorkspaceSettingsDrawer />
      <SubtaskThreadDrawer />
      <ApprovalPrompt />
    </>
  );
}
