/**
 * In-memory pending auto-start prompts, keyed by task/conversation id.
 *
 * Used by the compliance 对话引导 launcher: when a compliance workspace is
 * created in chat-collection mode, launchChat stages an opening prompt here;
 * ChatView consumes it once (WS connected + empty conversation) and sends it,
 * kicking off the dialogue-collection agent without any user interaction.
 *
 * Intentionally in-memory (not persisted): auto-start only matters on the
 * fresh navigation right after workspace creation; on reload there is no
 * pending entry, so it won't re-fire for an existing chat.
 */
const pending = new Map<string, string>();

export function setPendingAutoStart(taskId: string, prompt: string): void {
  pending.set(taskId, prompt);
}

/** Non-destructive read — lets consumers wait for preconditions (e.g. task.model)
 *  without losing the prompt. Consume only when actually sending. */
export function peekPendingAutoStart(taskId: string): string | undefined {
  return pending.get(taskId);
}

export function consumePendingAutoStart(taskId: string): string | undefined {
  const prompt = pending.get(taskId);
  if (prompt) pending.delete(taskId);
  return prompt;
}
