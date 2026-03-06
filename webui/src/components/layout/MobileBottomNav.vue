/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div v-if="isMobile" class="mobile-bottom-nav">
    <div class="nav-item" :class="{ active: activeTab === 'chat' }" @click="handleNavClick('chat')">
      <el-icon :size="24">
        <ChatDotRound />
      </el-icon>
      <span class="nav-label">{{ t('mobileBottomNav.chat') }}</span>
    </div>

    <div
      class="nav-item"
      :class="{ active: activeTab === 'conversations' }"
      @click="handleNavClick('conversations')"
    >
      <el-icon :size="24">
        <FolderOpened />
      </el-icon>
      <span class="nav-label">{{ t('mobileBottomNav.conversations') }}</span>
    </div>

    <div
      class="nav-item"
      :class="{ active: activeTab === 'files' }"
      @click="handleNavClick('files')"
    >
      <el-icon :size="24">
        <Folder />
      </el-icon>
      <span class="nav-label">{{ t('mobileBottomNav.files') }}</span>
      <el-badge v-if="openFilesCount > 0" :value="openFilesCount" class="nav-badge" />
    </div>

    <div class="nav-item" :class="{ active: activeTab === 'settings' }" @click="handleNavClick('settings')">
      <el-icon :size="24">
        <Setting />
      </el-icon>
      <span class="nav-label">{{ t('mobileBottomNav.settings') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChatDotRound, FolderOpened, Folder, Setting } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useMobile } from '@/composables/useMobile'

const { t } = useI18n()
const { isMobile } = useMobile()

interface Props {
  openFilesCount?: number
}

interface Emits {
  (e: 'navigate', tab: string): void
}

const props = withDefaults(defineProps<Props>(), {
  openFilesCount: 0
})

const emit = defineEmits<Emits>()

const activeTab = computed(() => {
  // 根据当前路由或状态确定活动标签
  // 这里可以通过路由或props传入
  return 'chat' // 默认聊天标签
})

const handleNavClick = (tab: string) => {
  emit('navigate', tab)
}
</script>

<script lang="ts">
export default {
  name: 'MobileBottomNav'
}
</script>

<style scoped>
.mobile-bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(56px + env(safe-area-inset-bottom, 0px));
  background-color: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color);
  display: flex;
  justify-content: space-around;
  align-items: center;
  padding-bottom: env(safe-area-inset-bottom, 0px);
  z-index: var(--z-mobile-bottom-nav, 999);
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
}

.nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  min-height: var(--touch-target-min, 44px);
}

.nav-item:active {
  background-color: var(--el-fill-color-light);
}

.nav-item.active {
  color: var(--el-color-primary);
}

.nav-label {
  font-size: 11px;
  margin-top: 2px;
  line-height: 1.2;
}

.nav-badge {
  position: absolute;
  top: 4px;
  right: 20%;
}

/* 桌面端隐藏 */
@media (min-width: 768px) {
  .mobile-bottom-nav {
    display: none;
  }
}
</style>
