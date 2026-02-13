/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="chat-controls-container">
    <el-button @click="handleNewChat" class="new-chat-button">
      New Dialogue
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

const handleNewChat = () => {
  chatStore.clearChat()
}
</script>

<style scoped>
.chat-controls-container {
  padding: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.new-chat-button {
  width: 100%;
}
</style>