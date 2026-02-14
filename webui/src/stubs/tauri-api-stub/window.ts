// Stub for @tauri-apps/api/window
/* eslint-disable @typescript-eslint/no-unused-vars */

export class Window {
  label: string

  constructor(label: string = 'main') {
    this.label = label
  }

  close(): Promise<void> {
    console.warn('[Tauri Stub] Window.close called')
    return Promise.resolve()
  }

  minimize(): Promise<void> {
    return Promise.resolve()
  }

  maximize(): Promise<void> {
    return Promise.resolve()
  }

  unmaximize(): Promise<void> {
    return Promise.resolve()
  }

  isMaximized(): Promise<boolean> {
    return Promise.resolve(false)
  }

  setTitle(_title: string): Promise<void> {
    return Promise.resolve()
  }

  show(): Promise<void> {
    return Promise.resolve()
  }

  hide(): Promise<void> {
    return Promise.resolve()
  }

  setFocus(): Promise<void> {
    return Promise.resolve()
  }

  center(): Promise<void> {
    return Promise.resolve()
  }

  outerPosition(): Promise<{ x: number; y: number }> {
    return Promise.resolve({ x: 0, y: 0 })
  }

  outerSize(): Promise<{ width: number; height: number }> {
    return Promise.resolve({ width: 800, height: 600 })
  }

  innerSize(): Promise<{ width: number; height: number }> {
    return Promise.resolve({ width: 800, height: 600 })
  }

  isVisible(): Promise<boolean> {
    return Promise.resolve(true)
  }

  isFocused(): Promise<boolean> {
    return Promise.resolve(true)
  }

  isMinimized(): Promise<boolean> {
    return Promise.resolve(false)
  }

  isMaximized(): Promise<boolean> {
    return Promise.resolve(false)
  }

  isFullscreen(): Promise<boolean> {
    return Promise.resolve(false)
  }

  isDecorated(): Promise<boolean> {
    return Promise.resolve(true)
  }

  isAlwaysOnTop(): Promise<boolean> {
    return Promise.resolve(false)
  }

  setAlwaysOnTop(_alwaysOnTop: boolean): Promise<void> {
    return Promise.resolve()
  }

  setFullscreen(_fullscreen: boolean): Promise<void> {
    return Promise.resolve()
  }

  setSize(_size: { width: number; height: number }): Promise<void> {
    return Promise.resolve()
  }

  setMinSize(_size: { width: number; height: number }): Promise<void> {
    return Promise.resolve()
  }

  setMaxSize(_size: { width: number; height: number }): Promise<void> {
    return Promise.resolve()
  }

  setPosition(_position: { x: number; y: number }): Promise<void> {
    return Promise.resolve()
  }

  setResizable(_resizable: boolean): Promise<void> {
    return Promise.resolve()
  }

  setTitle(_title: string): Promise<void> {
    return Promise.resolve()
  }
}

export function getCurrentWindow(): Window {
  return new Window('main')
}

export function getAllWindows(): Window[] {
  return [new Window('main')]
}

export default { Window, getCurrentWindow, getAllWindows }
