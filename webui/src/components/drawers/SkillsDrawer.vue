<template>
  <div class="skills-drawer">
    <div class="drawer-content" v-loading="loadingSkills">
      <!-- Header -->
      <el-alert title="技能管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区技能。技能目录：
            <br>• 项目: <code>.dawei/skills/</code>
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
        <el-select v-model="skillsFilter.mode" placeholder="所有模式" clearable style="width: 150px;" @change="filterSkills">
          <el-option label="所有模式" value="" />
          <el-option label="Orchestrator" value="orchestrator" />
          <el-option label="Plan" value="plan" />
          <el-option label="Do" value="do" />
          <el-option label="Check" value="check" />
          <el-option label="Act" value="act" />
        </el-select>

        <el-select v-model="skillsFilter.scope" placeholder="所有范围" clearable style="width: 150px;" @change="filterSkills">
          <el-option label="所有范围" value="" />
          <el-option label="项目" value="workspace" />
          <el-option label="全局" value="user" />
          <el-option label="系统" value="system" />
        </el-select>

        <el-input v-model="skillsFilter.search" placeholder="搜索技能" style="width: 250px;" clearable @input="filterSkills">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <!-- Skills Table -->
      <el-table :data="filteredSkills" stripe style="width: 100%;" max-height="calc(100vh - 300px)">
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

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="openEditSkillDialog(scope.row)">
              编辑
            </el-button>
            <el-button link type="primary" size="small" @click="openSkillEditor(scope.row)">
              文件
            </el-button>
            <el-button link type="danger" size="small" @click="deleteSkill(scope.row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 编辑技能对话框 -->
      <el-dialog
        v-model="editSkillDialogVisible"
        title="编辑技能"
        width="800px"
        :close-on-click-modal="false"
      >
        <el-form :model="editSkillForm" label-width="100px">
          <el-form-item label="技能名称">
            <el-input v-model="editSkillForm.name" placeholder="技能名称" />
          </el-form-item>
          <el-form-item label="技能描述">
            <el-input v-model="editSkillForm.description" placeholder="技能描述" />
          </el-form-item>
          <el-form-item label="技能内容">
            <el-input
              v-model="editSkillForm.content"
              type="textarea"
              :rows="15"
              placeholder="技能内容 (Markdown格式)"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editSkillDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveSkill" :loading="savingSkill">
            保存
          </el-button>
        </template>
      </el-dialog>

      <!-- 创建技能对话框 -->
      <el-dialog
        v-model="createSkillDialogVisible"
        title="创建技能"
        width="800px"
        :close-on-click-modal="false"
      >
        <el-form :model="createSkillForm" label-width="100px">
          <el-form-item label="技能名称" required>
            <el-input v-model="createSkillForm.name" placeholder="技能名称 (英文，如: my-skill)" />
          </el-form-item>
          <el-form-item label="技能描述">
            <el-input v-model="createSkillForm.description" placeholder="技能描述" />
          </el-form-item>
          <el-form-item label="作用范围">
            <el-select v-model="createSkillForm.scope" style="width: 100%;">
              <el-option label="项目 (仅当前工作区)" value="workspace" />
              <el-option label="全局 (所有工作区)" value="user" />
            </el-select>
          </el-form-item>
          <el-form-item label="技能内容">
            <el-input
              v-model="createSkillForm.content"
              type="textarea"
              :rows="15"
              placeholder="技能内容 (Markdown格式，支持frontmatter)"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createSkillDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="createSkill" :loading="creatingSkill">
            创建
          </el-button>
        </template>
      </el-dialog>

      <!-- 技能文件编辑器对话框 -->
      <el-dialog
        v-model="showSkillEditorDialog"
        :title="`技能文件 - ${editingSkill?.name || ''}`"
        width="900px"
        :close-on-click-modal="false"
      >
        <div v-loading="skillFileTreeLoading">
          <el-container style="height: 500px;">
            <el-aside width="250px" style="border-right: 1px solid var(--el-border-color);">
              <div style="padding: 10px; font-weight: 600;">技能资源文件</div>
              <el-tree
                :data="skillFileTree"
                node-key="name"
                :props="{ label: 'name', children: 'children' }"
                @node-click="handleNodeClick"
              >
                <template #default="{ node, data }">
                  <span class="custom-tree-node">
                    <el-icon v-if="data.type === 'folder'"><Folder /></el-icon>
                    <el-icon v-else><Document /></el-icon>
                    <span style="margin-left: 8px;">{{ node.label }}</span>
                  </span>
                </template>
              </el-tree>
            </el-aside>
            <el-main>
              <div v-if="currentSkillFile" style="height: 100%;">
                <div style="margin-bottom: 10px; font-weight: 600;">
                  {{ currentSkillFile.name }}
                </div>
                <el-scrollbar height="420px">
                  <pre style="white-space: pre-wrap; word-wrap: break-word; margin: 0;">{{ currentSkillFile.content || currentSkillFile.raw_content }}</pre>
                </el-scrollbar>
              </div>
              <el-empty v-else description="请选择文件查看内容" />
            </el-main>
          </el-container>
        </div>
        <template #footer>
          <el-button @click="showSkillEditorDialog = false">关闭</el-button>
        </template>
      </el-dialog>

      <!-- 市场对话框 -->
      <MarketDialog
        v-if="workspaceId"
        v-model="showMarketDialog"
        :workspace-id="workspaceId"
        initial-type="skill"
        @installed="handleMarketInstalled"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh, Search, ShoppingCart, Folder, Document } from '@element-plus/icons-vue';
import { watch, onMounted } from 'vue';
import { useSkills } from '@/composables/skills/useSkills';
import type { SkillFileTreeItem } from '@/services/api/services/skills';
import MarketDialog from '@/components/market/MarketDialog.vue';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  skillsList,
  loadingSkills,
  skillsFilter,
  filteredSkills,
  loadSkills,
  filterSkills,
  openEditSkillDialog,
  saveSkill,
  deleteSkill,
  openCreateSkillDialog,
  createSkill,
  openSkillEditor,
  openMarketDialog,
  installFromMarket,
  // 编辑相关状态
  editSkillDialogVisible,
  editSkillForm,
  savingSkill,
  // 创建相关状态
  createSkillDialogVisible,
  createSkillForm,
  creatingSkill,
  // 文件编辑器相关状态
  showSkillEditorDialog,
  editingSkill,
  skillFileTree,
  skillFileTreeLoading,
  currentSkillFile,
  viewSkillFile,
  // 市场相关状态
  showMarketDialog,
  installingFromMarket
} = useSkills(props.workspaceId);

onMounted(() => {
  if (props.workspaceId) {
    loadSkills();
  }
});

// 处理树节点点击事件
const handleNodeClick = (data: SkillFileTreeItem) => {
  // 只在点击文件时加载内容，点击文件夹不做任何操作
  if (data.type === 'file') {
    viewSkillFile(data);
  }
};

// 处理市场安装成功事件
const handleMarketInstalled = async (type: string) => {
  if (type === 'skill') {
    // 重新加载技能列表
    await loadSkills(true);
  }
};

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

.custom-tree-node {
  display: flex;
  align-items: center;
  width: 100%;
}

:deep(.el-tree-node__content) {
  height: 32px;
}

:deep(.el-tree-node__content:hover) {
  background-color: var(--el-fill-color-light);
}

code {
  background-color: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.9em;
}
</style>
