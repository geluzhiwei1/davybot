// Stub for @tauri-apps/api in web mode
// Note: Subpath imports (@tauri-apps/api/core, @tauri-apps/api/event, @tauri-apps/api/window)
// are handled via vite.config.js aliases

// Base exports (for import from '@tauri-apps/api')
export const app = {
  getApp: () => null,
  getName: () => 'web',
  getVersion: () => '0.0.0',
}

export default {
  app,
}
