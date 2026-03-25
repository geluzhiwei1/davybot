<!--
  Knowledge View - 知识库视图
  占位符组件 - 知识库功能正在开发中
-->
<template>
  <div class="knowledge-view">
    <el-result
      icon="info"
      title="知识库功能"
      sub-title="知识库功能正在开发中，敬请期待"
    >
      <template #extra>
        <el-button type="primary" @click="$router.push('/workspaces')">
          返回工作区
        </el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.knowledge-view {
  padding: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}
</style>
