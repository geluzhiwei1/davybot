// Stub for @tauri-apps/api/core

export function invoke(cmd: string, args?: Record<string, unknown>): Promise<unknown> {
  console.warn('[Tauri Stub] invoke called:', cmd, args)
  return Promise.resolve(null)
}

export const InvokeError = class InvokeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'InvokeError'
  }
}

export default { invoke, InvokeError }
