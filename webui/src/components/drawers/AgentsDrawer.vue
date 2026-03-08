<template>
  <div class="agents-drawer">
    <div class="drawer-content" v-loading="loadingAgents">
      <!-- Header -->
      <el-alert title="智能体管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区智能体（Agent/Mode）。智能体是具有特定角色和行为的AI代理。
          </p>
        </template>
      </el-alert>

      <!-- Actions -->
      <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600;">当前智能体 ({{ modeList.length }})</span>
        <div>
          <el-button type="success" size="small" @click="openMarketDialog('agent')">
            <el-icon><ShoppingCart /></el-icon>
            市场安装
          </el-button>
          <el-button type="primary" size="small" @click="showCreateModeDialog" style="margin-left: 8px;">
            <el-icon><Plus /></el-icon>
            添加智能体
          </el-button>
        </div>
      </div>

      <!-- Agents Table -->
      <el-table :data="modeList" stripe style="width: 100%;" max-height="calc(100vh - 300px)">
        <el-table-column prop="name" label="名称" width="200">
          <template #default="scope">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>{{ scope.row.name }}</span>
              <el-tag v-if="scope.row.is_default" type="success" size="small">默认</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="slug" label="标识符" width="180" />

        <el-table-column prop="source" label="来源" width="100">
          <template #default="scope">
            <el-tag
              :type="scope.row.source === 'system' ? 'info' : scope.row.source === 'user' ? 'warning' : 'success'"
              size="small">
              {{ scope.row.source === 'system' ? '系统' : scope.row.source === 'user' ? '用户' : '工作区' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="描述" show-overflow-tooltip />

        <el-table-column label="操作" width="300" fixed="right">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="editMode(scope.row)"
              :disabled="scope.row.source === 'system'">
              编辑
            </el-button>
            <el-button link type="warning" size="small" @click="editModeRules(scope.row)">
              <el-icon><Document /></el-icon>
              规则
            </el-button>
            <el-button link type="info" size="small" @click="viewMode(scope.row)">
              详情
            </el-button>
            <el-button link type="danger" size="small" @click="deleteMode(scope.row.slug)"
              :disabled="scope.row.source === 'system'">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 编辑/创建智能体对话框 -->
      <el-dialog
        v-model="showModeDialog"
        :title="editingMode ? '编辑智能体' : '添加智能体'"
        width="800px"
        :close-on-click-modal="false"
      >
        <!-- 创建模式：只显示基本字段 -->
        <el-form :model="modeForm" label-width="120px" v-if="!editingMode">
          <el-form-item label="标识符" required>
            <el-input
              v-model="modeForm.slug"
              placeholder="英文标识符，如: code-reviewer"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              模式的唯一标识符
            </div>
          </el-form-item>

          <el-form-item label="名称" required>
            <el-input v-model="modeForm.name" placeholder="例如: 🎨 代码审查员" />
          </el-form-item>

          <el-form-item label="描述" required>
            <el-input v-model="modeForm.description" type="textarea" :rows="2" placeholder="简要描述这个模式的用途" />
          </el-form-item>
        </el-form>

        <!-- 编辑模式：显示YAML编辑器 -->
        <div v-else>
          <el-alert title="模式配置 (YAML)" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
            <template #default>
              <p style="margin: 0; font-size: 13px;">
                编辑智能体的YAML配置文件。包含角色定义、使用场景、自定义指令等。
              </p>
            </template>
          </el-alert>
          <el-input
            v-model="modeYamlContent"
            type="textarea"
            :rows="20"
            placeholder="YAML配置内容"
            style="font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;"
          />
        </div>

        <template #footer>
          <el-button @click="showModeDialog = false">取消</el-button>
          <el-button type="primary" @click="saveMode" :loading="savingMode">
            {{ editingMode ? '更新' : '创建' }}
          </el-button>
        </template>
      </el-dialog>

      <!-- 查看智能体详情对话框 -->
      <el-dialog
        v-model="showViewModeDialog"
        title="智能体详情"
        width="700px"
      >
        <div v-if="viewingMode">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="名称">
              {{ viewingMode.name }}
              <el-tag v-if="viewingMode.is_default" type="success" size="small" style="margin-left: 8px;">默认</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="标识符">
              {{ viewingMode.slug }}
            </el-descriptions-item>
            <el-descriptions-item label="来源">
              <el-tag :type="viewingMode.source === 'system' ? 'info' : 'success'" size="small">
                {{ viewingMode.source === 'system' ? '系统' : '自定义' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="描述">
              {{ viewingMode.description || '无' }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <template #footer>
          <el-button @click="showViewModeDialog = false">关闭</el-button>
        </template>
      </el-dialog>

      <!-- 编辑智能体规则对话框 -->
      <el-dialog
        v-model="showModeRulesDialog"
        :title="`编辑规则 - ${editingModeRules?.name || ''}`"
        width="900px"
        :close-on-click-modal="false"
      >
        <div v-loading="modeRuleFilesLoading">
          <el-container style="height: 500px;" v-if="modeRuleFiles.length > 0">
            <el-aside width="250px" style="border-right: 1px solid var(--el-border-color);">
              <div style="padding: 10px; font-weight: 600;">规则文件</div>
              <el-menu
                :default-active="currentRuleFile?.name || ''"
                @select="handleSelectRuleFile"
              >
                <el-menu-item
                  v-for="file in modeRuleFiles"
                  :key="file.name"
                  :index="file.name"
                >
                  <el-icon><Document /></el-icon>
                  <span style="margin-left: 8px;">{{ file.name }}</span>
                </el-menu-item>
              </el-menu>
            </el-aside>
            <el-main>
              <div style="margin-bottom: 10px; font-weight: 600;">
                {{ currentRuleFile?.name || '主规则' }}
              </div>
              <el-input
                v-model="modeRulesContent"
                type="textarea"
                :rows="18"
                placeholder="规则内容（YAML格式）"
              />
            </el-main>
          </el-container>
          <el-empty
            v-else
            description="该智能体暂无规则文件"
            :image-size="120"
          >
            <template #description>
              <p>该智能体还没有配置规则文件</p>
              <p style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 8px;">
                规则文件位于：<code>.dawei/rules-{{ editingModeRules?.slug }}/</code>
              </p>
            </template>
          </el-empty>
        </div>
        <template #footer>
          <el-button @click="showModeRulesDialog = false">取消</el-button>
          <el-button type="primary" @click="saveModeRules">保存</el-button>
        </template>
      </el-dialog>

      <!-- 市场对话框 -->
      <MarketDialog
        v-if="workspaceId"
        v-model="showMarketDialog"
        :workspace-id="workspaceId"
        initial-type="agent"
        @installed="handleMarketInstalled"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, ShoppingCart, Document } from '@element-plus/icons-vue';
import { watch, onMounted } from 'vue';
import { useAgents } from '@/composables/agents/useAgents';
import MarketDialog from '@/components/market/MarketDialog.vue';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  modeList,
  loadingAgents,
  loadAgents,
  showCreateModeDialog,
  editMode,
  saveMode,
  deleteMode,
  viewMode,
  editModeRules,
  saveModeRules,
  selectRuleFile,
  openMarketDialog,
  installFromMarket,
  // 对话框状态
  showModeDialog,
  showViewModeDialog,
  showModeRulesDialog,
  editingMode,
  viewingMode,
  editingModeRules,
  modeForm,
  savingMode,
  modeRulesContent,
  modeRuleFiles,
  currentRuleFile,
  modeRuleFilesLoading,
  // 市场相关状态
  showMarketDialog,
  installingFromMarket
} = useAgents(props.workspaceId);

// 处理规则文件选择
const handleSelectRuleFile = (fileName: string) => {
  const selectedFile = modeRuleFiles.value.find(f => f.name === fileName);
  if (selectedFile) {
    selectRuleFile(selectedFile);
  }
};

// 处理市场安装成功事件
const handleMarketInstalled = async (type: string) => {
  if (type === 'agent') {
    // 重新加载智能体列表
    await loadAgents(true);
  }
};

onMounted(() => {
  if (props.workspaceId) {
    loadAgents();
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadAgents();
  }
});
</script>

<style scoped>
.agents-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
