<template>
  <div class="skills-drawer">
    <div class="drawer-content" v-loading="loadingSkills">
      <!-- Header -->
      <el-alert title="技能管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区技能。技能目录：
            <br>• 工作区: <code>.dawei/skills/</code>
            <br>• 全局: <code>~/.dawei/skills/</code>
          </p>
        </template>
      </el-alert>

      <!-- Actions -->
      <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600;">
          可用技能 ({{ filteredSkills.length }})
        </span>
        <div>
          <el-button type="primary" size="small" @click="openCreateSkillDialog">
            <el-icon><Plus /></el-icon>
            创建技能
          </el-button>
          <el-button type="success" size="small" @click="openMarketDialog('skill')" style="margin-left: 8px;">
            <el-icon><ShoppingCart /></el-icon>
            市场安装
          </el-button>
          <el-button type="primary" size="small" @click="loadSkills" :loading="loadingSkills" style="margin-left: 8px;">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <!-- Filters -->
      <div style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-select v-model="skillsFilter.mode" placeholder="所有模式" clearable style="width: 150px;">
          <el-option label="所有模式" value="" />
          <el-option label="Code" value="code" />
          <el-option label="Ask" value="ask" />
          <el-option label="Architect" value="architect" />
          <el-option label="Debug" value="debug" />
        </el-select>

        <el-select v-model="skillsFilter.scope" placeholder="所有范围" clearable style="width: 150px;">
          <el-option label="所有范围" value="" />
          <el-option label="项目" value="workspace" />
          <el-option label="系统" value="system" />
          <el-option label="全局" value="user" />
        </el-select>

        <el-input v-model="skillsFilter.search" placeholder="搜索技能" style="width: 250px;" clearable>
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <!-- Skills Table -->
      <el-table :data="filteredSkills" stripe style="width: 100%;">
        <el-table-column prop="icon" label="图标" width="60">
          <template #default="scope">
            <span style="font-size: 20px;">{{ scope.row.icon || '📦' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="name" label="名称" width="200" show-overflow-tooltip />

        <el-table-column prop="description" label="描述" show-overflow-tooltip />

        <el-table-column prop="category" label="分类" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.category" size="small" type="info">
              {{ scope.row.category }}
            </el-tag>
            <span v-else style="color: var(--el-text-color-secondary);">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="mode" label="模式" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.mode" size="small" type="primary">
              {{ scope.row.mode }}
            </el-tag>
            <span v-else style="color: var(--el-text-color-secondary);">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="scope" label="范围" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.scope === 'workspace' ? 'success' : scope.row.scope === 'user' ? 'warning' : 'info'" size="small">
              {{ scope.row.scope === 'workspace' ? '项目' : scope.row.scope === 'user' ? '全局' : '系统' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="资源" width="80" align="center">
          <template #default="scope">
            <span :style="{ color: scope.row.has_resources ? 'var(--el-color-success)' : 'var(--el-text-color-secondary)' }">
              {{ scope.row.resource_count || 0 }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue';
import { onMounted, watch } from 'vue';
import { useSkills } from '@/composables/skills/useSkills';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  skillsList,
  loadingSkills,
  skillsFilter,
  filteredSkills,
  loadSkills,
  openCreateSkillDialog,
  openMarketDialog
} = useSkills(props.workspaceId || '');

onMounted(() => {
  if (props.workspaceId) {
    loadSkills();
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadSkills();
  }
});
</script>

<style scoped>
.skills-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
