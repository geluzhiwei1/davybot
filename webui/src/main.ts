/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import { ElRadio, ElRadioGroup, ElRadioButton } from 'element-plus'
import './styles/element-plus.scss'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import './assets/main.css'
import './styles/design-compact.css'
import './styles/message-minimal.css'
import './styles/theme-variables.css'
import './styles/theme-application.css' // 主题CSS变量映射
import './styles/dark-mode-comprehensive.css' // 统一深色主题
import './styles/dark-mode-component-fixes.css' // 组件特定深色模式修复
import './styles/element-plus-popper-fix.css' // 修复 Element Plus Popper 被遮挡问题

// ==================== 全局错误处理 ====================
// import { errorHandler } from './services/errorHandler'

const app = createApp(App)

// 注册 Element Plus (required for @lljj/vue3-form-element)
app.use(ElementPlus)

// 显式注册 radio 组件以支持 @lljj/vue3-form-element
app.component('el-radio', ElRadio)
app.component('el-radio-group', ElRadioGroup)
app.component('el-radio-button', ElRadioButton)

// 1. 初始化全局错误捕获
// 暂时禁用errorHandler以避免循环错误
// console.log('[Main] Initializing global error handler...')
// errorHandler.init()

// 2. 设置 Vue 错误处理器
// errorHandler.setupVueErrorHandler(app)

// 3. 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(i18n)

// ==================== 主题系统初始化 ====================
import { useThemeStore } from './stores/themeStore'

// 初始化主题store
const themeStore = useThemeStore()
themeStore.initializeTheme()

// 注册WebSocket消息路由
// import { registerTodoWebSocketRoutes } from '@/stores/todoStore'
// registerTodoWebSocketRoutes()

// 开发环境：暴露store用于E2E测试
// 注释掉因为 e2e 目录不存在
// if (import.meta.env.DEV) {
//   import('./e2e/test-setup')
// }

// 挂载应用
app.mount('#app')

// ==================== 应用启动后检查 ====================
// 暂时禁用崩溃报告检查
// window.addEventListener('load', () => {
//   const crashReports = errorHandler.getCrashReports()
//   const unreported = errorHandler.getUnreportedCrashes()
//
//   if (crashReports.length > 0) {
//     console.warn(`[Main] Found ${crashReports.length} crash report(s) from previous session`)
//     console.log(`[Main] - Reported: ${crashReports.length - unreported.length}`)
//     console.log(`[Main] - Unreported: ${unreported.length}`)
//
//     // 将崩溃报告信息存储到 window 对象，供 App.vue 使用
//     (window as unknown).__CRASH_REPORTS__ = crashReports
//   }
// })

// ==================== 应用退出前清理 ====================
window.addEventListener('beforeunload', () => {
  // 可以在这里执行清理逻辑
})
