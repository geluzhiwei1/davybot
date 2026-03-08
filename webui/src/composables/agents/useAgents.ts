import { ref, onMounted } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage } from 'element-plus';
import type { Agent } from '@/types/agents';

export function useAgents(workspaceId: string) {
  const modeList = ref<Agent[]>([]);
  const loadingAgents = ref(false);

  // 加载智能体列表
  const loadAgents = async (reload = false) => {
    if (!workspaceId) return;

    loadingAgents.value = true;
    try {
      const response = await apiManager.getWorkspacesApi().getModes(workspaceId, reload);
      modeList.value = response.modes || [];
    } catch (error: unknown) {
      ElMessage.error('加载智能体列表失败');
      console.error('Failed to load agents:', error);
    } finally {
      loadingAgents.value = false;
    }
  };

  // 显示创建智能体对话框
  const showCreateModeDialog = () => {
    ElMessage.info('创建智能体功能开发中...');
  };

  // 编辑智能体
  const editMode = (agent: Agent) => {
    ElMessage.info(`编辑智能体 "${agent.name}" 功能开发中...`);
  };

  // 编辑智能体规则
  const editModeRules = (agent: Agent) => {
    ElMessage.info(`编辑智能体 "${agent.name}" 规则功能开发中...`);
  };

  // 删除智能体
  const deleteMode = async (slug: string) => {
    ElMessage.info(`删除智能体 "${slug}" 功能开发中...`);
  };

  // 打开市场对话框
  const openMarketDialog = (type: 'agent' | 'skill' | 'plugin') => {
    ElMessage.info(`${type} 市场功能开发中...`);
  };

  return {
    modeList,
    loadingAgents,
    loadAgents,
    showCreateModeDialog,
    editMode,
    editModeRules,
    deleteMode,
    openMarketDialog
  };
}
