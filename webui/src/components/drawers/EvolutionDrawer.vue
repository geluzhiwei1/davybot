<template>
  <div class="evolution-drawer">
    <div class="drawer-content" v-loading="loading">
      <!-- Header -->
      <el-alert
        :title="$t('evolution.title')"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      >
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            {{ $t('evolution.description') }}
          </p>
        </template>
      </el-alert>

      <!-- Enable/Disable Switch -->
      <div style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div style="font-weight: 500; margin-bottom: 4px;">
            {{ $t('evolution.enableEvolution') }}
          </div>
          <div style="font-size: 12px; color: var(--el-text-color-secondary);">
            {{ $t('evolution.enableDescription') }}
          </div>
        </div>
        <el-switch
          v-model="evolutionEnabled"
          :loading="savingConfig"
          @change="handleEnableChange"
          :disabled="isRunning"
        />
      </div>

      <!-- Evolution Control Panel (when enabled) -->
      <div v-if="evolutionEnabled">
        <!-- Current Cycle Status -->
        <el-card shadow="never" style="margin-bottom: 16px;" v-if="evolutionStatus?.current_cycle">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ $t('evolution.currentCycle') }}: {{ evolutionStatus.current_cycle.cycle_id }}</span>
              <el-tag :type="getStatusType(evolutionStatus.current_cycle.status)">
                {{ getStatusLabel(evolutionStatus.current_cycle.status) }}
              </el-tag>
            </div>
          </template>

          <!-- Phase Progress -->
          <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; margin-bottom: 8px;">{{ $t('evolution.phases') }}</div>
            <el-steps :active="getPhaseIndex(evolutionStatus.current_cycle.current_phase)" finish-status="success" align-center>
              <el-step title="PLAN" :description="getPhaseStatus('plan')" />
              <el-step title="DO" :description="getPhaseStatus('do')" />
              <el-step title="CHECK" :description="getPhaseStatus('check')" />
              <el-step title="ACT" :description="getPhaseStatus('act')" />
            </el-steps>
          </div>

          <!-- Action Buttons -->
          <div style="display: flex; gap: 8px;">
            <el-button
              v-if="isRunning && !isPaused"
              type="warning"
              size="small"
              @click="handlePause"
              :loading="actionLoading"
            >
              <el-icon><VideoPause /></el-icon>
              {{ $t('evolution.pause') }}
            </el-button>
            <el-button
              v-if="isPaused"
              type="success"
              size="small"
              @click="handleResume"
              :loading="actionLoading"
            >
              <el-icon><VideoPlay /></el-icon>
              {{ $t('evolution.resume') }}
            </el-button>
            <el-button
              v-if="isRunning || isPaused"
              type="danger"
              size="small"
              @click="handleAbort"
              :loading="actionLoading"
            >
              <el-icon><CloseBold /></el-icon>
              {{ $t('evolution.abort') }}
            </el-button>
            <el-button
              size="small"
              @click="handleViewCycle"
            >
              <el-icon><View /></el-icon>
              {{ $t('evolution.viewDetails') }}
            </el-button>
          </div>
        </el-card>

        <!-- Manual Trigger -->
        <el-card shadow="never" style="margin-bottom: 16px;" v-if="!isRunning">
          <template #header>
            <span>{{ $t('evolution.manualTrigger') }}</span>
          </template>
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <span style="font-size: 13px; color: var(--el-text-color-secondary);">
              {{ $t('evolution.manualTriggerDescription') }}
            </span>
            <el-input
              v-model="daoPathInput"
              :placeholder="$t('evolution.daoPathPlaceholder')"
              clearable
              size="small"
              @keyup.enter="handleTrigger"
            >
              <template #prepend>
                <span style="white-space: nowrap;">dao.md</span>
              </template>
            </el-input>
            <div style="display: flex; justify-content: flex-end;">
              <el-button
                type="primary"
                size="small"
                @click="handleTrigger"
                :loading="triggerLoading"
              >
                <el-icon><CaretRight /></el-icon>
                {{ $t('evolution.triggerNow') }}
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- Cycle History -->
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>{{ $t('evolution.cycleHistory') }}</span>
              <el-button
                size="small"
                @click="loadStatus"
                :loading="loading"
              >
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>

          <el-table :data="cycleHistory" stripe style="width: 100%;" max-height="400">
            <template #empty>
              <div style="padding: 24px 0; color: var(--el-text-color-secondary); text-align: center;">
                {{ $t('evolution.noCycles') }}
              </div>
            </template>
            <el-table-column prop="cycle_id" :label="$t('evolution.cycleId')" width="100" />
            <el-table-column prop="status" :label="$t('evolution.status')" width="120">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" size="small">
                  {{ getStatusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="current_phase" :label="$t('evolution.currentPhase')" width="100">
              <template #default="scope">
                {{ scope.row.current_phase?.toUpperCase() || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="started_at" :label="$t('evolution.startedAt')" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.started_at) }}
              </template>
            </el-table-column>
            <el-table-column :label="$t('evolution.actions')" width="150" align="right">
              <template #default="scope">
                <el-button
                  size="small"
                  @click="handleViewCycleDetail(scope.row.cycle_id)"
                >
                  {{ $t('evolution.view') }}
                </el-button>
                <el-popconfirm
                  :title="$t('evolution.deleteConfirm')"
                  :confirm-button-text="$t('common.confirm')"
                  :cancel-button-text="$t('common.cancel')"
                  @confirm="handleDeleteCycle(scope.row.cycle_id)"
                >
                  <template #reference>
                    <el-button
                      size="small"
                      type="danger"
                      :disabled="scope.row.status === 'running'"
                    >
                      {{ $t('common.delete') }}
                    </el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </div>

    <!-- Cycle Detail Dialog -->
    <el-dialog
      v-model="showCycleDetailDialog"
      :title="`${$t('evolution.cycleDetails')}: ${currentCycleId}`"
      width="80%"
      top="5vh"
    >
      <el-tabs v-model="activeTab" v-loading="loadingCycleDetail">
        <el-tab-pane :label="$t('evolution.overview')" name="overview">
          <div v-if="cycleDetail">
            <el-descriptions :column="2" border>
              <el-descriptions-item :label="$t('evolution.cycleId')">
                {{ cycleDetail.metadata.cycle_id }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.status')">
                <el-tag :type="getStatusType(cycleDetail.metadata.status)">
                  {{ getStatusLabel(cycleDetail.metadata.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.startedAt')">
                {{ formatDate(cycleDetail.metadata.started_at) }}
              </el-descriptions-item>
              <el-descriptions-item :label="$t('evolution.completedAt')">
                {{ cycleDetail.metadata.completed_at ? formatDate(cycleDetail.metadata.completed_at) : '-' }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-tab-pane>
        <el-tab-pane label="PLAN" name="plan">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.plan"
            readonly
          />
        </el-tab-pane>
        <el-tab-pane label="DO" name="do">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.do"
            readonly
          />
        </el-tab-pane>
        <el-tab-pane label="CHECK" name="check">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.check"
            readonly
          />
        </el-tab-pane>
        <el-tab-pane label="ACT" name="act">
          <el-input
            v-if="cycleDetail"
            type="textarea"
            :rows="20"
            :model-value="cycleDetail.phases.act"
            readonly
          />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import {
  VideoPause,
  VideoPlay,
  CloseBold,
  View,
  Refresh,
  CaretRight
} from '@element-plus/icons-vue';
import { evolutionService } from '@/services/api/evolution';
import type {
  EvolutionStatusResponse,
  CycleDetailResponse
} from '@/services/api/evolution';

const props = defineProps<{
  workspaceId: string;
}>();

const { t } = useI18n();

// State
const loading = ref(false);
const savingConfig = ref(false);
const actionLoading = ref(false);
const triggerLoading = ref(false);
const loadingCycleDetail = ref(false);

const evolutionEnabled = ref(false);
const evolutionStatus = ref<EvolutionStatusResponse | null>(null);

const showCycleDetailDialog = ref(false);
const activeTab = ref('overview');

const cycleHistory = computed(() => evolutionStatus.value?.all_cycles || []);
const currentCycleId = ref('');
const cycleDetail = ref<CycleDetailResponse | null>(null);

const isRunning = computed(() => evolutionStatus.value?.is_running || false);
const isPaused = computed(() => evolutionStatus.value?.is_paused || false);

const daoPathInput = ref('');

// Methods
const loadStatus = async () => {
  loading.value = true;
  try {
    const data = await evolutionService.getEvolutionStatus(props.workspaceId);
    evolutionStatus.value = data;
    evolutionEnabled.value = data.enabled;
  } catch (error) {
    console.error('Failed to load evolution status:', error);
    ElMessage.error(t('evolution.loadFailed'));
  } finally {
    loading.value = false;
  }
};

const handleEnableChange = async (enabled: boolean) => {
  savingConfig.value = true;
  try {
    if (enabled) {
      await evolutionService.enableEvolution(props.workspaceId, {
        enabled: true,
        schedule: '* * * * *',
        goals: []
      });
      ElMessage.success(t('evolution.enabled'));
    } else {
      await evolutionService.disableEvolution(props.workspaceId);
      ElMessage.success(t('evolution.disabled'));
    }
    await loadStatus();
  } catch (error) {
    console.error('Failed to toggle evolution:', error);
    ElMessage.error(t('evolution.toggleFailed'));
    evolutionEnabled.value = !enabled; // Revert
  } finally {
    savingConfig.value = false;
  }
};

const handleTrigger = async () => {
  triggerLoading.value = true;
  try {
    const daoPath = daoPathInput.value.trim() || undefined;
    const data = await evolutionService.triggerEvolution(props.workspaceId, daoPath);
    ElMessage.success(t('evolution.triggered', { cycleId: data.cycle_id }));
    daoPathInput.value = '';
    await loadStatus();
  } catch (error) {
    console.error('Failed to trigger evolution:', error);
    ElMessage.error(t('evolution.triggerFailed'));
  } finally {
    triggerLoading.value = false;
  }
};

const handlePause = async () => {
  if (!evolutionStatus.value?.current_cycle) return;

  actionLoading.value = true;
  try {
    await evolutionService.pauseCycle(props.workspaceId, evolutionStatus.value.current_cycle.cycle_id);
    ElMessage.success(t('evolution.paused'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to pause cycle:', error);
    ElMessage.error(t('evolution.pauseFailed'));
  } finally {
    actionLoading.value = false;
  }
};

const handleResume = async () => {
  if (!evolutionStatus.value?.current_cycle) return;

  actionLoading.value = true;
  try {
    await evolutionService.resumeCycle(props.workspaceId, evolutionStatus.value.current_cycle.cycle_id);
    ElMessage.success(t('evolution.resumed'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to resume cycle:', error);
    ElMessage.error(t('evolution.resumeFailed'));
  } finally {
    actionLoading.value = false;
  }
};

const handleAbort = async () => {
  if (!evolutionStatus.value?.current_cycle) return;

  actionLoading.value = true;
  try {
    await evolutionService.abortCycle(props.workspaceId, evolutionStatus.value.current_cycle.cycle_id);
    ElMessage.success(t('evolution.aborted'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to abort cycle:', error);
    ElMessage.error(t('evolution.abortFailed'));
  } finally {
    actionLoading.value = false;
  }
};

const handleViewCycle = () => {
  if (evolutionStatus.value?.current_cycle) {
    handleViewCycleDetail(evolutionStatus.value.current_cycle.cycle_id);
  }
};

const handleViewCycleDetail = async (cycleId: string) => {
  currentCycleId.value = cycleId;
  showCycleDetailDialog.value = true;
  activeTab.value = 'overview';

  loadingCycleDetail.value = true;
  try {
    const data = await evolutionService.getCycleDetail(props.workspaceId, cycleId);
    cycleDetail.value = data;
  } catch (error) {
    console.error('Failed to load cycle detail:', error);
    ElMessage.error(t('evolution.loadDetailFailed'));
  } finally {
    loadingCycleDetail.value = false;
  }
};

const handleDeleteCycle = async (cycleId: string) => {
  try {
    await evolutionService.deleteCycle(props.workspaceId, cycleId);
    ElMessage.success(t('evolution.cycleDeleted'));
    await loadStatus();
  } catch (error) {
    console.error('Failed to delete cycle:', error);
    ElMessage.error(t('evolution.deleteFailed'));
  }
};

// Helper functions
const getStatusType = (status: string) => {
  const typeMap: Record<string, any> = {
    pending: 'info',
    running: 'warning',
    paused: 'warning',
    completed: 'success',
    aborted: 'danger',
    failed: 'danger'
  };
  return typeMap[status] || 'info';
};

const getStatusLabel = (status: string) => {
  const labelMap: Record<string, string> = {
    pending: t('evolution.statusPending'),
    running: t('evolution.statusRunning'),
    paused: t('evolution.statusPaused'),
    completed: t('evolution.statusCompleted'),
    aborted: t('evolution.statusAborted'),
    failed: t('evolution.statusFailed')
  };
  return labelMap[status] || status;
};

const getPhaseIndex = (currentPhase: string | null) => {
  const phases = ['plan', 'do', 'check', 'act'];
  return currentPhase ? phases.indexOf(currentPhase) : -1;
};

const getPhaseStatus = (phase: string) => {
  const phaseData = evolutionStatus.value?.current_cycle?.phases[phase];
  if (!phaseData) return '-';

  const statusMap: Record<string, string> = {
    pending: t('evolution.phasePending'),
    in_progress: t('evolution.phaseInProgress'),
    completed: t('evolution.phaseCompleted'),
    failed: t('evolution.phaseFailed')
  };

  return statusMap[phaseData.status] || phaseData.status;
};


const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
};

// Lifecycle
onMounted(() => {
  loadStatus();
});
</script>

<style scoped>
.evolution-drawer {
  height: 100%;
  overflow-y: auto;
}

.drawer-content {
  padding: 16px;
}
</style>
