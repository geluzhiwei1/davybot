// Stub for @tauri-apps/api/event
 

export type Event<T = unknown> = {
  payload: T
}

export type UnlistenFn = () => void

export async function listen<T = unknown>(
  _event: string,
  _handler: (event: Event<T>) => void
): Promise<UnlistenFn> {
  return () => {}
}

export async function emit(_event: string, _payload?: unknown): Promise<void> {
  // No-op in web mode
}

export async function emitTo<T = unknown>(
  _target: string,
  _event: string,
  _payload?: T
): Promise<void> {
  // No-op in web mode
}

export default { listen, emit, emitTo }
