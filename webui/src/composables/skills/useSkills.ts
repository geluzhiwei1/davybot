import { ref, computed, onMounted } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage } from 'element-plus';
import type { Skill } from '@/types/skills';

export function useSkills(workspaceId: string) {
  const skillsList = ref<Skill[]>([]);
  const loadingSkills = ref(false);
  const skillsFilter = ref({
    mode: '',
    scope: '',
    search: ''
  });

  // 过滤后的技能列表
  const filteredSkills = computed(() => {
    let filtered = skillsList.value;

    // 按mode过滤
    if (skillsFilter.value.mode) {
      filtered = filtered.filter(skill => skill.mode === skillsFilter.value.mode);
    }

    // 按scope过滤
    if (skillsFilter.value.scope) {
      filtered = filtered.filter(skill => skill.scope === skillsFilter.value.scope);
    }

    // 按搜索关键词过滤
    if (skillsFilter.value.search) {
      const searchLower = skillsFilter.value.search.toLowerCase();
      filtered = filtered.filter(skill =>
        skill.name.toLowerCase().includes(searchLower) ||
        skill.description.toLowerCase().includes(searchLower)
      );
    }

    return filtered;
  });

  // 加载技能列表
  const loadSkills = async () => {
    if (!workspaceId) return;

    loadingSkills.value = true;
    try {
      const response = await apiManager.getSkillsApi().listSkills(workspaceId);
      skillsList.value = (response.skills || []) as Skill[];
    } catch (error: unknown) {
      ElMessage.error('加载技能列表失败');
      console.error('Failed to load skills:', error);
    } finally {
      loadingSkills.value = false;
    }
  };

  // 过滤技能
  const filterSkills = () => {
    // Computed会自动更新
  };

  // 打开创建技能对话框
  const openCreateSkillDialog = () => {
    ElMessage.info('创建技能功能开发中...');
  };

  // 打开市场对话框
  const openMarketDialog = (type: 'skill' | 'plugin' | 'agent') => {
    ElMessage.info(`${type} 市场功能开发中...`);
  };

  // 获取技能统计
  const skillsStats = computed(() => ({
    total: skillsList.value.length,
    workspace: skillsList.value.filter(s => s.scope === 'workspace').length,
    user: skillsList.value.filter(s => s.scope === 'user').length,
    system: skillsList.value.filter(s => s.scope === 'system').length
  }));

  return {
    skillsList,
    loadingSkills,
    skillsFilter,
    filteredSkills,
    skillsStats,
    loadSkills,
    filterSkills,
    openCreateSkillDialog,
    openMarketDialog
  };
}
