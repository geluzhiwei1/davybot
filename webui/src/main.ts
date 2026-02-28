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

// import { errorHandler } from './services/errorHandler'

const app = createApp(App)

// 注册 Element Plus (required for @lljj/vue3-form-element)
app.use(ElementPlus)

// 显式注册 radio 组件以支持 @lljj/vue3-form-element
app.component('el-radio', ElRadio)
app.component('el-radio-group', ElRadioGroup)
app.component('el-radio-button', ElRadioButton)



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



// 挂载应用
app.mount('#app')



// ==================== 应用退出前清理 ====================
window.addEventListener('beforeunload', () => {
  // 可以在这里执行清理逻辑
})
